import uuid

import pytest

from app import notify
from app.ai.routing import route_ticket
from app.config import get_settings
from app.models import utcnow


@pytest.mark.parametrize("category,room_type,severity,hazard,team,priority,hours", [
    ("leak_water", "office", 2, False, "Plumbing Shop", "P3", 72),
    ("leak_water", "lab", 2, False, "Plumbing Shop", "P2", 8),
    ("light_out", "corridor", 1, False, "Electrical Shop", "P4", 336),
    ("too_hot", "classroom", 2, False, "HVAC Shop", "P3", 72),
    ("elevator_out", "lobby", 3, False, "Elevator Service (contractor)", "P1", 1),
    ("gas_smell", "lab", 4, True, "Environmental Health & Safety", "P1", 1),
    ("broken_furniture", "restroom", 1, True, "Carpentry & Locksmith", "P1", 1),
    ("other", None, 2, False, "Work Control Center", "P3", 72),
])
def test_routing_table(seeded, db, category, room_type, severity, hazard, team, priority, hours):
    now = utcnow()
    d = route_ticket(db, category=category, severity=severity, is_hazard=hazard, room_type=room_type, now=now)
    assert d.team_name == team and d.priority == priority
    assert round((d.sla_due_at - now).total_seconds() / 3600) == hours
    assert d.rationale


def test_trade_always_follows_category(seeded, db):
    d = route_ticket(db, category="leak_water", severity=2, is_hazard=False, room_type="office", trade="Electrical")
    assert d.trade == "Plumbing"


def _alert():
    return notify.Alert(ticket_id=uuid.uuid4(), short_code="SF-9999", title="Gas odor", hazard_type="gas",
                        hazard_label="Gas", location="Engineering Hall, Room 210", priority="P1",
                        safety_text="Leave the area.", url_path="/tickets/SF-9999")


def test_slack_payload(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None, **_):
        sent.update(url=url, json=json)
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    ok, detail = notify.SlackWebhookNotifier("https://hooks.example/abc").alert(_alert())
    assert ok and sent["url"] == "https://hooks.example/abc"
    assert "SF-9999" in sent["json"]["text"] and sent["json"]["blocks"][0]["type"] == "header"


def test_twilio_payload(monkeypatch):
    sent = {}

    def fake_post(url, data=None, auth=None, timeout=None, **_):
        sent.update(url=url, data=data, auth=auth)
        return type("R", (), {"status_code": 201})()

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    ok, _ = notify.TwilioSmsNotifier("AC1", "tok", "+15550001", "+15550002").alert(_alert())
    assert ok and sent["url"].endswith("/Accounts/AC1/Messages.json")
    assert sent["data"]["To"] == "+15550002" and sent["auth"] == ("AC1", "tok")


def test_misconfigured_notifier_falls_back_to_console(monkeypatch):
    monkeypatch.setattr(get_settings(), "notifier", "slack")
    monkeypatch.setattr(get_settings(), "slack_webhook_url", "")
    assert isinstance(notify.build_notifier(), notify.ConsoleNotifier)


def test_failed_delivery_still_logs_to_console(monkeypatch, caplog):
    class Broken:
        channel = "slack"

        def alert(self, alert):
            raise RuntimeError("webhook down")

    notify._deliver(_alert(), Broken())
    assert notify.recent_alerts[0]["ok"] is False and "webhook down" in notify.recent_alerts[0]["detail"]
