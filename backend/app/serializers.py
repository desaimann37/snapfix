"""ORM -> API model conversion."""

from __future__ import annotations

from app import taxonomy
from app.models import Asset, Building, Location, Report, Team, Ticket, TicketEvent
from app.schemas import (
    AssetOut,
    BuildingOut,
    EventOut,
    LocationOut,
    ReportOut,
    TeamOut,
    TicketDetail,
    TicketOut,
)


def media_url(path: str | None) -> str | None:
    return f"/media/{path}" if path else None


def building_out(b: Building) -> BuildingOut:
    return BuildingOut(id=b.id, code=b.code, name=b.name, floors=b.floors, lat=b.lat, lng=b.lng)


def location_out(loc: Location | None) -> LocationOut | None:
    if loc is None:
        return None
    return LocationOut(
        id=loc.id, building_id=loc.building_id, building_code=loc.building.code, building_name=loc.building.name,
        floor=loc.floor, room=loc.room, label=loc.label, room_type=loc.room_type, qr_code=loc.qr_code,
        x=loc.x, y=loc.y, w=loc.w, h=loc.h,
    )


def team_out(team: Team | None) -> TeamOut | None:
    return TeamOut(id=team.id, name=team.name, trade=team.trade) if team else None


def asset_out(asset: Asset | None) -> AssetOut | None:
    if asset is None:
        return None
    return AssetOut(id=asset.id, tag=asset.tag, name=asset.name, type=asset.type, make=asset.make, model=asset.model)


def _thumbnail(t: Ticket) -> str | None:
    for r in t.reports:
        if r.photo_path:
            return media_url(r.photo_path)
    return None


def ticket_out(t: Ticket) -> TicketOut:
    cat = taxonomy.CATEGORY_BY_KEY.get(t.category)
    return TicketOut(
        id=t.id, short_code=t.short_code, title=t.title, summary=t.summary, category=t.category,
        category_label=cat.label if cat else t.category, trade=t.trade, severity=t.severity, priority=t.priority,
        is_hazard=t.is_hazard, hazard_type=t.hazard_type, status=t.status, needs_review=t.needs_review,
        report_count=t.report_count, created_at=t.created_at, updated_at=t.updated_at, sla_due_at=t.sla_due_at,
        resolved_at=t.resolved_at, assignee=t.assignee, source=t.source, team=team_out(t.team),
        location=location_out(t.location), location_text=t.location_text, asset=asset_out(t.asset),
        cluster_id=t.cluster_id, parent_id=t.parent_id, thumbnail_url=_thumbnail(t),
    )


def report_out(r: Report) -> ReportOut:
    return ReportOut(
        id=r.id, created_at=r.created_at, text=r.text, transcript=r.transcript, photo_url=media_url(r.photo_path),
        status=r.status, llm_mode=r.llm_mode, extraction_confidence=r.extraction_confidence,
        latency_ms=r.latency_ms, prompt_version=r.prompt_version,
    )


def event_out(e: TicketEvent) -> EventOut:
    return EventOut(id=e.id, type=e.type, actor=e.actor, rationale=e.rationale, payload=e.payload,
                    created_at=e.created_at)


def ticket_detail(t: Ticket, children: list[Ticket] | None = None) -> TicketDetail:
    base = ticket_out(t).model_dump()
    return TicketDetail(
        **base,
        reports=[report_out(r) for r in t.reports],
        events=[event_out(e) for e in t.events],
        brief=t.brief_json,
        brief_generated_at=t.brief_generated_at,
        children=[ticket_out(c) for c in (children or [])],
    )
