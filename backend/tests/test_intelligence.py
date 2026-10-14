from types import SimpleNamespace

import pytest

from app.ai import agent as agent_mod
from app.ai.brief import CitedLine, TechnicianBriefOut, validate_citations
from app.ai.llm import LLMUsage, llm

PLANTED_TITLES = {
    "Water dripping from ceiling above lab bench",
    "Brown water stain spreading on corridor ceiling",
    "Wet ceiling tiles and drip near east stairwell",
    "Water leaking under window after rain",
    "Damp carpet and musty smell along exterior wall",
}


def open_clusters(client):
    return client.get("/api/clusters").json()


def test_planted_water_cluster_is_found(reseed, client):
    clusters = open_clusters(client)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["building"]["code"] == "ENGR" and "water intrusion" in c["name"].lower()
    titles = {t["title"] for t in c["tickets"]}
    assert len(titles & PLANTED_TITLES) >= 4 and titles <= PLANTED_TITLES
    assert "floors 3" in c["hypothesis"] and "inspection" in c["hypothesis"].lower()
    assert 0 < c["confidence"] <= 1


def test_clustering_is_idempotent_and_respects_dismissal(reseed, client):
    first = open_clusters(client)
    again = client.post("/api/clusters/run").json()
    assert [c["id"] for c in again] == [c["id"] for c in first]
    r = client.post(f"/api/clusters/{first[0]['id']}/dismiss")
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert client.post("/api/clusters/run").json() == []
    assert client.post(f"/api/clusters/{first[0]['id']}/dismiss").status_code == 409


def test_confirm_creates_parent_inspection(reseed, client):
    c = open_clusters(client)[0]
    out = client.post(f"/api/clusters/{c['id']}/confirm").json()
    parent = out["parent_ticket"]
    assert out["status"] == "confirmed" and parent["title"].startswith("Inspection:")
    for t in c["tickets"]:
        detail = client.get(f"/api/tickets/{t['short_code']}").json()
        assert detail["parent_id"] == parent["id"]
        assert any(e["type"] == "linked" for e in detail["events"])
    parent_detail = client.get(f"/api/tickets/{parent['short_code']}").json()
    assert len(parent_detail["children"]) == len(c["tickets"])
    assert client.post("/api/clusters/run").json() == []


def _repeat_sink_code(client):
    return client.get("/api/tickets", params={"q": "Faucet leaking again"}).json()["items"][0]["short_code"]


def test_brief_for_repeat_failure_sink(reseed, client):
    code = _repeat_sink_code(client)
    brief = client.get(f"/api/tickets/{code}/brief").json()
    assert brief["sop_coverage"] == "matched"
    assert brief["history_note"] and "repeat" in brief["history_note"].lower()
    earlier = [h["short_code"] for h in brief["history"]]
    assert len(earlier) == 2 and earlier[0] in brief["history_note"]
    assert brief["history"][0]["days_ago"] in (20, 21, 22)
    step_cites = {s["citation"] for s in brief["steps"]}
    assert "SOP: Faucet Cartridge Replacement §4" in step_cites
    assert all(s["citation"].startswith("SOP: Faucet Cartridge Replacement") for s in brief["safety"])
    assert brief["tools_parts"] and brief["likely_causes"][0]["cause"].startswith("Repeat failure")

    cached = client.get(f"/api/tickets/{code}/brief").json()
    assert cached["generated_at"] == brief["generated_at"]
    detail = client.get(f"/api/tickets/{code}").json()
    assert [e["type"] for e in detail["events"]].count("brief_generated") == 1


def test_brief_without_matching_sop_says_so(reseed, client):
    found = client.get("/api/tickets", params={"q": "Wi-Fi dead zone", "status": "open"}).json()
    code = found["items"][0]["short_code"]
    brief = client.get(f"/api/tickets/{code}/brief").json()
    assert brief["sop_coverage"] == "none" and brief["sources"] == []
    assert all(s["citation"] is None for s in brief["steps"] + brief["safety"])


def test_invented_citations_are_removed():
    brief = TechnicianBriefOut(
        summary="s", likely_causes=[], tools_parts=[], history_note=None, sop_coverage="matched",
        safety=[CitedLine(text="a", citation="[SOP: Faucet Cartridge Replacement §2]")],
        steps=[CitedLine(text="b", citation="SOP: Made Up Procedure §9"), CitedLine(text="c", citation=None)])
    fixed, removed = validate_citations(brief, {"SOP: Faucet Cartridge Replacement §2"})
    assert removed == 1
    assert fixed.safety[0].citation == "SOP: Faucet Cartridge Replacement §2" and fixed.steps[0].citation is None


def test_kpis_activity_trend(reseed, client):
    k = client.get("/api/dashboard/kpis").json()
    assert set(k["open_by_priority"]) == {"P1", "P2", "P3", "P4"} and k["hazards_open"] == 1
    assert k["open_clusters"] == 1 and k["duplicates_prevented_30d"] > 0
    before = k["photo_to_ticket_ms"]["count"]
    body = client.post("/api/reports", data={"text": "projector won't turn on", "location_code": "engr-305"}).json()
    client.post(f"/api/reports/{body['report_id']}/confirm", json={})
    after = client.get("/api/dashboard/kpis").json()
    assert after["photo_to_ticket_ms"]["count"] == before + 1 and after["median_time_to_triage_s"] is not None

    feed = client.get("/api/dashboard/activity", params={"limit": 5}).json()
    assert feed[0]["ticket"]["short_code"] and len(feed) == 5
    trend = client.get("/api/dashboard/trend").json()
    assert len(trend["days"]) == 14 and trend["trades"]
    b = client.get("/api/dashboard/buildings").json()
    assert {x["code"] for x in b} == {"ENGR", "LIB", "STUC"}


@pytest.mark.parametrize("question,expect", [
    ("What's open in Engineering Hall over P2?", "Engineering Hall"),
    ("any hazards right now?", "HAZARD"),
    ("show root-cause clusters", "water intrusion"),
    ("how are we doing today?", "open tickets"),
])
def test_mock_agent(module_seed, client, question, expect):
    out = client.post("/api/agent/chat", json={"message": question}).json()
    assert out["mode"] == "mock" and expect.lower() in out["answer"].lower()
    assert out["tool_calls"]


def test_mock_agent_priority_filter_and_email(module_seed, client):
    out = client.post("/api/agent/chat", json={"message": "what's open in engineering over P2"}).json()
    assert " P3" not in out["answer"] and " P4" not in out["answer"]
    code = client.get("/api/tickets", params={"q": "Faucet leaking again"}).json()["items"][0]["short_code"]
    email = client.post("/api/agent/chat", json={"message": f"draft a status update email for {code}"}).json()
    assert "Subject:" in email["answer"] and code in email["answer"]


class _Block(SimpleNamespace):
    pass


def _usage():
    return LLMUsage(input_tokens=100, output_tokens=20, cost_usd=0.0004)


def test_live_agent_tool_loop(module_seed, db, monkeypatch):
    calls = []

    def fake_create(stage, role, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            block = _Block(type="tool_use", id="tu_1", name="search_tickets",
                           input={"status": "open", "building": "ENGR", "trade": None, "min_priority": "P2",
                                  "hazard_only": False, "query": None, "limit": 5})
            return SimpleNamespace(stop_reason="tool_use", content=[block]), _usage(), 5
        done = [_Block(type="text", text="Two P2 tickets.")]
        return SimpleNamespace(stop_reason="end_turn", content=done), _usage(), 5

    monkeypatch.setattr(agent_mod, "effective_llm_mode", lambda: "live")
    monkeypatch.setattr(llm, "create", fake_create)
    reply = agent_mod.chat(db, "what's open in ENGR over P2?")
    assert reply.mode == "live" and reply.answer == "Two P2 tickets."
    assert reply.tool_calls[0]["name"] == "search_tickets" and "ticket" in reply.tool_calls[0]["summary"]
    tool_result = calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"
    assert calls[0]["tools"][0]["name"] == "search_tickets" and "tool_choice" not in calls[0]


def test_live_agent_caps_tool_calls(module_seed, db, monkeypatch):
    n = {"i": 0}

    def forever(stage, role, **kwargs):
        n["i"] += 1
        if n["i"] > 10:
            return SimpleNamespace(stop_reason="end_turn", content=[_Block(type="text", text="done")]), _usage(), 1
        block = _Block(type="tool_use", id=f"tu_{n['i']}", name="get_kpis", input={})
        return SimpleNamespace(stop_reason="tool_use", content=[block]), _usage(), 1

    monkeypatch.setattr(agent_mod, "effective_llm_mode", lambda: "live")
    monkeypatch.setattr(llm, "create", forever)
    reply = agent_mod.chat(db, "loop please")
    assert len(reply.tool_calls) == agent_mod.MAX_TOOL_CALLS


def test_eval_api_and_timing(module_seed, client, tmp_path, monkeypatch):
    import json

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "eval_results_dir", str(tmp_path))
    assert client.get("/api/eval/latest").json()["result"] is None
    (tmp_path / "20260101-000000.json").write_text(json.dumps({
        "run_id": "20260101-000000", "mode": "mock", "timestamp": "2026-01-01T00:00:00Z", "n_items": 1,
        "metrics": {"category_accuracy": 1.0, "hazard_recall": 1.0}}))
    body = client.get("/api/eval/latest").json()
    assert body["result"]["run_id"] == "20260101-000000" and body["runs"] == 1
    client.post("/api/eval/timing", json={"flow": "baseline", "seconds": 180, "participant": "v1"})
    t = client.post("/api/eval/timing", json={"flow": "snapfix", "seconds": 15}).json()["timing"]
    assert t["baseline"]["median_s"] == 180 and t["snapfix"]["n"] >= 1 and t["speedup"]
    assert client.post("/api/eval/timing", json={"flow": "other", "seconds": 1}).status_code == 422
