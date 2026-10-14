"""Deterministic routing: trade -> team, severity x location criticality x hazard -> priority + SLA.

The LLM never picks teams or priorities directly; this keeps routing explainable and testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import taxonomy
from app.models import Team, utcnow


@dataclass
class RoutingDecision:
    trade: str
    team_id: uuid.UUID | None
    team_name: str | None
    priority: str
    sla_due_at: datetime
    criticality: str
    rationale: str

    def as_payload(self) -> dict:
        return {
            "trade": self.trade,
            "team": self.team_name,
            "priority": self.priority,
            "sla_due_at": self.sla_due_at.isoformat(),
            "criticality": self.criticality,
        }


def route_ticket(
    db: Session,
    *,
    category: str,
    severity: int,
    is_hazard: bool,
    room_type: str | None,
    trade: str | None = None,
    now: datetime | None = None,
    teams: dict[str, Team] | None = None,
) -> RoutingDecision:
    now = now or utcnow()
    # The trade always follows the category (a fixed mapping), so the model can't route to the wrong shop.
    resolved_trade = taxonomy.trade_for_category(category) if category in taxonomy.CATEGORY_BY_KEY else (
        trade if trade in taxonomy.TRADES else "General")
    team = teams.get(resolved_trade) if teams is not None else db.scalar(
        select(Team).where(Team.trade == resolved_trade))
    criticality = taxonomy.location_criticality(room_type, category)
    priority, why = taxonomy.compute_priority(severity, criticality, is_hazard)
    sla_hours = taxonomy.SLA_HOURS[priority]
    rationale = (
        f"Category '{category}' maps to trade {resolved_trade}"
        f"{f' -> team {team.name}' if team else ''}. Location criticality: {criticality}. {why} "
        f"SLA for {priority} is {sla_hours} h."
    )
    return RoutingDecision(
        trade=resolved_trade,
        team_id=team.id if team else None,
        team_name=team.name if team else None,
        priority=priority,
        sla_due_at=now + timedelta(hours=sla_hours),
        criticality=criticality,
        rationale=rationale,
    )
