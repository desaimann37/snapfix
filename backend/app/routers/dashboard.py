"""Manager dashboard data: KPIs, live activity, trend, building hotspot summary."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.db import get_db
from app.models import Building, Cluster, Location, Report, Ticket, TicketEvent, utcnow
from app.runtime import effective_llm_mode

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

OPEN = ("new", "triaged", "assigned", "in_progress")
LIVE_MODES = ("live", "mock", "fallback", "rules")  # reports that went through the real pipeline (not seed)


def compute_kpis(db: Session) -> dict:
    now = utcnow()
    open_filter = Ticket.status.in_(OPEN)
    by_priority = {p: 0 for p in taxonomy.PRIORITIES}
    by_priority.update(dict(db.execute(select(Ticket.priority, func.count()).where(open_filter)
                                       .group_by(Ticket.priority)).all()))
    count = lambda *f: db.scalar(select(func.count()).select_from(Ticket).where(*f)) or 0  # noqa: E731

    week = now - timedelta(days=7)
    live_reports = db.scalars(select(Report).where(Report.llm_mode.in_(LIVE_MODES), Report.latency_ms.is_not(None),
                                                   Report.created_at >= week)).all()
    lat = np.array([r.latency_ms for r in live_reports], dtype=float)
    live_cost = [r.cost_usd for r in live_reports if r.llm_mode == "live"]

    triage = []
    for t in db.scalars(select(Ticket).options(selectinload(Ticket.reports))
                        .where(Ticket.source == "snapfix", Ticket.created_at >= week, Ticket.triaged_at.is_not(None))):
        first = min((r.created_at for r in t.reports), default=t.created_at)
        triage.append(max(0.0, (t.triaged_at - first).total_seconds()))

    month = now - timedelta(days=30)
    dup_prevented = db.scalar(select(func.coalesce(func.sum(Ticket.report_count - 1), 0))
                              .where(Ticket.created_at >= month)) or 0
    reports_14d = db.scalar(select(func.count()).select_from(Report)
                            .where(Report.created_at >= now - timedelta(days=14)))
    return {
        "open_total": sum(by_priority.values()),
        "open_by_priority": by_priority,
        "hazards_open": count(open_filter, Ticket.is_hazard.is_(True)),
        "hazards_24h": count(Ticket.is_hazard.is_(True), Ticket.created_at >= now - timedelta(hours=24)),
        "sla_breaches": count(open_filter, Ticket.sla_due_at < now),
        "duplicates_prevented_30d": int(dup_prevented),
        "duplicates_merged_live": db.scalar(select(func.count()).select_from(Report)
                                            .where(Report.status == "merged")) or 0,
        "reports_24h": db.scalar(select(func.count()).select_from(Report)
                                 .where(Report.created_at >= now - timedelta(hours=24))) or 0,
        "reports_per_day_14d": round((reports_14d or 0) / 14, 1),
        "photo_to_ticket_ms": {
            "count": int(lat.size),
            "avg": float(lat.mean()) if lat.size else None,
            "p50": float(np.percentile(lat, 50)) if lat.size else None,
            "p95": float(np.percentile(lat, 95)) if lat.size else None,
        },
        "median_time_to_triage_s": float(median(triage)) if triage else None,
        "open_clusters": db.scalar(select(func.count()).select_from(Cluster).where(Cluster.status == "open")) or 0,
        "avg_cost_per_report_usd": round(sum(live_cost) / len(live_cost), 5) if live_cost else None,
        "llm_mode": effective_llm_mode(),
        "generated_at": now.isoformat(),
    }


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)) -> dict:
    return compute_kpis(db)


FEED_TYPES = ("created", "merged", "escalated", "notified", "enriched", "brief_generated", "linked", "location_set")


@router.get("/activity")
def activity(limit: int = Query(30, ge=1, le=100), all_events: bool = False,
             db: Session = Depends(get_db)) -> list[dict]:
    """Live feed: the meaningful AI/dispatch events (routine status churn only with all_events=true)."""
    filters = [TicketEvent.created_at <= utcnow()]
    if not all_events:
        filters.append(TicketEvent.type.in_(FEED_TYPES))
    rows = db.execute(select(TicketEvent, Ticket).join(Ticket, TicketEvent.ticket_id == Ticket.id)
                      .where(*filters)
                      .order_by(TicketEvent.created_at.desc()).limit(limit)).all()
    return [{"id": str(e.id), "type": e.type, "actor": e.actor, "rationale": e.rationale,
             "created_at": e.created_at.isoformat(), "ticket": {"id": str(t.id), "short_code": t.short_code,
                                                                "title": t.title, "priority": t.priority,
                                                                "is_hazard": t.is_hazard}}
            for e, t in rows]


@router.get("/trend")
def trend(days: int = Query(14, ge=3, le=60), db: Session = Depends(get_db)) -> dict:
    """Reports per day by trade (for the stacked bar chart)."""
    now = utcnow()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(Report.created_at, Ticket.trade).join(Ticket, Report.ticket_id == Ticket.id)
                      .where(Report.created_at >= start)).all()
    series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for created, trade in rows:
        series[created.date().isoformat()][trade] += 1
    dates = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    totals = defaultdict(int)
    for d in dates:
        for trade, n in series[d].items():
            totals[trade] += n
    trades = [t for t, _ in sorted(totals.items(), key=lambda kv: -kv[1])]
    return {"trades": trades, "days": [{"date": d, **{t: series[d].get(t, 0) for t in trades}} for d in dates]}


@router.get("/buildings")
def buildings(db: Session = Depends(get_db)) -> list[dict]:
    """Open tickets per building and floor (to pick the hotspot floor)."""
    counts = db.execute(select(Location.building_id, Location.floor, func.count()).join(
        Ticket, Ticket.location_id == Location.id).where(Ticket.status.in_(OPEN))
        .group_by(Location.building_id, Location.floor)).all()
    per = defaultdict(dict)
    for bid, floor, n in counts:
        per[bid][floor] = n
    hazards = dict(db.execute(select(Ticket.building_id, func.count()).where(
        Ticket.status.in_(OPEN), Ticket.is_hazard.is_(True)).group_by(Ticket.building_id)).all())
    out = []
    for b in db.scalars(select(Building).order_by(Building.code)):
        floors = {f: per[b.id].get(f, 0) for f in range(1, b.floors + 1)}
        busiest = max(floors, key=lambda f: floors[f]) if any(floors.values()) else 1
        out.append({"code": b.code, "name": b.name, "floors": b.floors, "open_by_floor": floors,
                    "open_total": sum(floors.values()), "hazards": hazards.get(b.id, 0), "busiest_floor": busiest})
    return out
