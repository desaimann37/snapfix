import time

import pytest

from app.ai.llm import LLMError, llm
from app.events import broker
from app.notify import recent_alerts


@pytest.fixture
def published(monkeypatch):
    events = []
    monkeypatch.setattr(broker, "publish", lambda name, data: events.append((name, data)))
    return events


@pytest.fixture
def llm_down(monkeypatch):
    def boom(**_):
        raise LLMError("simulated outage")

    monkeypatch.setattr(llm, "structured", boom)


def test_gas_report_is_instant_p1_without_the_llm(reseed, client, published, llm_down):
    started = time.perf_counter()
    r = client.post("/api/reports", data={"text": "I smell gas near room 210"})
    elapsed = time.perf_counter() - started
    assert r.status_code == 200, r.text
    body = r.json()
    assert elapsed < 2.0
    t = body["ticket"]
    assert t is not None and t["is_hazard"] and t["hazard_type"] == "gas" and t["priority"] == "P1"
    assert t["location"]["room"] == "210" and t["category"] == "gas_smell"
    assert body["hazard"]["sources"] == ["rules"] and "911" in body["hazard"]["safety_text"]
    assert body["llm_mode"] == "rules" and "On-call has been alerted" in body["message"]

    names = [n for n, _ in published]
    assert "ticket.created" in names and "hazard.alert" in names
    assert recent_alerts[0]["ticket"] == t["short_code"]

    detail = client.get(f"/api/tickets/{t['short_code']}").json()
    types = [e["type"] for e in detail["events"]]
    assert {"created", "escalated", "assigned", "notified"} <= set(types)
    assert detail["is_hazard"]  # enrichment failed (LLM down) but the hazard stands


def test_enrichment_adds_detail_but_keeps_hazard(reseed, client, published):
    data = {"text": "wires sparking behind the projector", "location_code": "engr-204"}
    body = client.post("/api/reports", data=data).json()
    detail = client.get(f"/api/tickets/{body['ticket']['short_code']}").json()
    assert detail["is_hazard"] and detail["hazard_type"] == "electrical" and detail["priority"] == "P1"
    assert any(e["type"] == "enriched" for e in detail["events"])
    assert "ticket.updated" in [n for n, _ in published]


def test_second_gas_report_merges_without_a_second_alert(reseed, client, published):
    first = client.post("/api/reports", data={"text": "I smell gas near room 210"}).json()
    alerts_before = len([n for n, _ in published if n == "hazard.alert"])
    second = client.post("/api/reports", data={"text": "strong gas smell in room 210"}).json()
    assert second["merged"] is True and second["ticket"]["short_code"] == first["ticket"]["short_code"]
    assert second["ticket"]["report_count"] == 2
    assert len([n for n, _ in published if n == "hazard.alert"]) == alerts_before
    assert "ticket.merged" in [n for n, _ in published]


def test_hazard_without_location_then_reporter_adds_it(reseed, client, published):
    body = client.post("/api/reports", data={"text": "smoke coming out of a vent"}).json()
    t = body["ticket"]
    assert t["is_hazard"] and t["location"] is None and t["location_text"]
    loc = client.get("/api/locations/stuc-247").json()
    r = client.post(f"/api/reports/{body['report_id']}/confirm", json={"location_id": loc["id"]}).json()
    assert r["ticket"]["location"]["room"] == "247"
    detail = client.get(f"/api/tickets/{t['short_code']}").json()
    assert any(e["type"] == "location_set" for e in detail["events"])


def test_non_hazard_report_goes_through_review(reseed, client, published):
    body = client.post("/api/reports", data={"text": "projector won't turn on", "location_code": "engr-305"}).json()
    assert body["ticket"] is None and body["hazard"]["is_hazard"] is False
    assert not [n for n, _ in published if n == "hazard.alert"]
