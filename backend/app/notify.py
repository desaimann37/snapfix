"""Pluggable hazard notifications: console (default), Slack webhook, Twilio SMS.

Alerts are sent on a background thread so a slow webhook can never delay the P1 path. The outcome is written
back to the ticket's decision log as a `notified` event.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger("snapfix.notify")


@dataclass
class Alert:
    ticket_id: uuid.UUID
    short_code: str
    title: str
    hazard_type: str | None
    hazard_label: str
    location: str
    priority: str
    safety_text: str
    url_path: str

    def text(self) -> str:
        return (f"P1 HAZARD ({self.hazard_label}) {self.short_code}: {self.title} @ {self.location}. "
                f"Safety: {self.safety_text}")


class Notifier(Protocol):
    channel: str

    def alert(self, alert: Alert) -> tuple[bool, str]: ...


class ConsoleNotifier:
    channel = "console"

    def alert(self, alert: Alert) -> tuple[bool, str]:
        log.warning("HAZARD ALERT %s", alert.text(), extra={"ticket": alert.short_code, "hazard": alert.hazard_type})
        return True, "logged to console"


class SlackWebhookNotifier:
    channel = "slack"

    def __init__(self, url: str):
        self.url = url

    def alert(self, alert: Alert) -> tuple[bool, str]:
        payload = {
            "text": alert.text(),
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"P1 hazard: {alert.hazard_label}"}},
                {"type": "section", "text": {"type": "mrkdwn",
                                             "text": f"*{alert.short_code}* {alert.title}\n*Where:* {alert.location}"}},
                {"type": "context", "elements": [{"type": "mrkdwn", "text": alert.safety_text}]},
            ],
        }
        r = httpx.post(self.url, json=payload, timeout=4.0)
        return r.status_code < 300, f"slack HTTP {r.status_code}"


class TwilioSmsNotifier:
    channel = "sms"

    def __init__(self, sid: str, token: str, sender: str, to: str):
        self.sid, self.token, self.sender, self.to = sid, token, sender, to

    def alert(self, alert: Alert) -> tuple[bool, str]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        r = httpx.post(url, data={"From": self.sender, "To": self.to, "Body": alert.text()[:1500]},
                       auth=(self.sid, self.token), timeout=6.0)
        return r.status_code < 300, f"twilio HTTP {r.status_code}"


def build_notifier() -> Notifier:
    s = get_settings()
    if s.notifier == "slack" and s.slack_webhook_url:
        return SlackWebhookNotifier(s.slack_webhook_url)
    if s.notifier == "twilio" and s.twilio_account_sid and s.twilio_auth_token and s.twilio_from and s.alert_to:
        return TwilioSmsNotifier(s.twilio_account_sid, s.twilio_auth_token, s.twilio_from, s.alert_to)
    if s.notifier not in ("console", ""):
        log.warning("NOTIFIER=%s is not fully configured; using console", s.notifier)
    return ConsoleNotifier()


# Recent alerts, for the dashboard and tests.
recent_alerts: deque[dict] = deque(maxlen=50)


def _deliver(alert: Alert, notifier: Notifier) -> None:
    from app.db import session_scope
    from app.models import Ticket
    from app.services import add_event

    try:
        ok, detail = notifier.alert(alert)
    except Exception as exc:  # never let a notification failure break anything
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    if not ok and notifier.channel != "console":
        ConsoleNotifier().alert(alert)  # fallback so the alert is never silently lost
    recent_alerts.appendleft({"ticket": alert.short_code, "channel": notifier.channel, "ok": ok, "detail": detail,
                              "text": alert.text()})
    try:
        with session_scope() as db:
            ticket = db.get(Ticket, alert.ticket_id)
            if ticket is not None:
                status = "delivered" if ok else "FAILED"
                add_event(db, ticket, "notified", actor="system",
                          rationale=f"On-call alert via {notifier.channel}: {status} ({detail}).",
                          payload={"channel": notifier.channel, "ok": ok, "detail": detail})
    except Exception:
        log.exception("notify: could not record notified event")


def send_alert(alert: Alert, *, background: bool = True) -> None:
    notifier = build_notifier()
    if background:
        threading.Thread(target=_deliver, args=(alert, notifier), daemon=True, name="notify").start()
    else:
        _deliver(alert, notifier)
