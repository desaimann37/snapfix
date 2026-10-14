"""Small shared helpers for tickets: short codes and the audit trail."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Counter, Ticket, TicketEvent

TICKET_SEQ = "ticket_seq"
TICKET_SEQ_START = 600


def next_ticket_seq(db: Session) -> int:
    """Allocate the next ticket number. Row lock on Postgres keeps concurrent submissions unique."""
    counter = db.execute(select(Counter).where(Counter.name == TICKET_SEQ).with_for_update()).scalar_one_or_none()
    if counter is None:
        counter = Counter(name=TICKET_SEQ, value=TICKET_SEQ_START - 1)
        db.add(counter)
        db.flush()
    counter.value += 1
    db.flush()
    return counter.value


def short_code_for(seq: int) -> str:
    return f"SF-{seq:04d}"


def add_event(
    db: Session,
    ticket: Ticket,
    type_: str,
    *,
    actor: str = "ai",
    rationale: str | None = None,
    payload: dict[str, Any] | None = None,
    created_at=None,
) -> TicketEvent:
    event = TicketEvent(ticket_id=ticket.id, type=type_, actor=actor, rationale=rationale, payload=payload or {})
    if created_at is not None:
        event.created_at = created_at
        event.updated_at = created_at
    db.add(event)
    return event
