"""Ticket queue, detail and status updates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.events import broker
from app.models import Building, Location, Ticket, utcnow
from app.schemas import TicketDetail, TicketList, TicketPatch
from app.serializers import ticket_detail, ticket_out
from app.services import add_event

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

OPEN_STATUSES = ("new", "triaged", "assigned", "in_progress")


def ticket_query():
    return select(Ticket).options(
        selectinload(Ticket.location).selectinload(Location.building),
        selectinload(Ticket.team),
        selectinload(Ticket.asset),
        selectinload(Ticket.reports),
    )


def load_ticket(db: Session, ref: str, *, full: bool = False) -> Ticket:
    # populate_existing: sessions don't expire on commit, so refresh collections (events/reports) explicitly.
    stmt = ticket_query().execution_options(populate_existing=True)
    if full:
        stmt = stmt.options(selectinload(Ticket.events))
    try:
        stmt = stmt.where(Ticket.id == uuid.UUID(ref))
    except ValueError:
        stmt = stmt.where(Ticket.short_code == ref.upper())
    ticket = db.scalar(stmt)
    if ticket is None:
        raise HTTPException(404, f"Ticket {ref} not found")
    return ticket


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


@router.get("", response_model=TicketList)
def list_tickets(
    status: str | None = Query(None, description="'open', or comma list of statuses"),
    trade: str | None = None,
    priority: str | None = None,
    building: str | None = Query(None, description="building code, e.g. ENGR"),
    hazard: bool | None = None,
    q: str | None = None,
    asset_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    sort: str = Query("queue", pattern="^(queue|newest|sla|reports)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TicketList:
    filters = []
    if status == "open":
        filters.append(Ticket.status.in_(OPEN_STATUSES))
    elif status:
        filters.append(Ticket.status.in_(_csv(status)))
    if trade:
        filters.append(Ticket.trade.in_(_csv(trade)))
    if priority:
        filters.append(Ticket.priority.in_([p.upper() for p in _csv(priority)]))
    if building:
        filters.append(Ticket.building_id == select(Building.id).where(Building.code == building.upper())
                       .scalar_subquery())
    if hazard is not None:
        filters.append(Ticket.is_hazard.is_(hazard))
    if asset_id:
        filters.append(Ticket.asset_id == asset_id)
    if location_id:
        filters.append(Ticket.location_id == location_id)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Ticket.title.ilike(like), Ticket.summary.ilike(like), Ticket.short_code.ilike(like),
                           Ticket.category.ilike(like), Ticket.trade.ilike(like)))

    total = db.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
    order = {
        "queue": (Ticket.is_hazard.desc(), Ticket.priority.asc(), Ticket.created_at.desc()),
        "newest": (Ticket.created_at.desc(),),
        "sla": (Ticket.sla_due_at.asc(),),
        "reports": (Ticket.report_count.desc(), Ticket.created_at.desc()),
    }[sort]
    rows = db.scalars(ticket_query().where(*filters).order_by(*order).limit(limit).offset(offset)).all()
    return TicketList(items=[ticket_out(t) for t in rows], total=total)


@router.get("/{ref}", response_model=TicketDetail)
def get_ticket(ref: str, db: Session = Depends(get_db)) -> TicketDetail:
    ticket = load_ticket(db, ref, full=True)
    children = db.scalars(ticket_query().where(Ticket.parent_id == ticket.id)).all()
    return ticket_detail(ticket, list(children))


@router.patch("/{ref}", response_model=TicketDetail)
def patch_ticket(ref: str, body: TicketPatch, db: Session = Depends(get_db)) -> TicketDetail:
    ticket = load_ticket(db, ref, full=True)
    actor = f"user:{body.actor}"
    if body.assignee is not None and body.assignee != ticket.assignee:
        add_event(db, ticket, "assigned", actor=actor, rationale=body.note,
                  payload={"from": ticket.assignee, "to": body.assignee})
        ticket.assignee = body.assignee or None
        if ticket.status in ("new", "triaged") and ticket.assignee and body.status is None:
            body.status = "assigned"
    if body.status is not None and body.status != ticket.status:
        add_event(db, ticket, "status_changed", actor=actor, rationale=body.note,
                  payload={"from": ticket.status, "to": body.status, "note": body.note})
        ticket.status = body.status
        if body.status in ("resolved", "closed") and ticket.resolved_at is None:
            ticket.resolved_at = utcnow()
        if body.status not in ("resolved", "closed"):
            ticket.resolved_at = None
        if body.status != "new":
            ticket.needs_review = False
    db.commit()
    ticket = load_ticket(db, str(ticket.id), full=True)
    broker.publish("ticket.updated", ticket_out(ticket).model_dump(mode="json"))
    children = db.scalars(ticket_query().where(Ticket.parent_id == ticket.id)).all()
    return ticket_detail(ticket, list(children))
