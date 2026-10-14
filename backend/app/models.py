"""SQLAlchemy models. Portable between PostgreSQL+pgvector (app) and SQLite (tests)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIM = 384


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Always hands back timezone-aware UTC datetimes, even on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


JSONType = JSON().with_variant(JSONB(), "postgresql")
# pgvector on Postgres; a JSON list on SQLite (similarity is then computed in Python).
VectorType = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)


class Building(Entity):
    __tablename__ = "buildings"

    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    floors: Mapped[int] = mapped_column(Integer)

    locations: Mapped[list[Location]] = relationship(back_populates="building")


class Location(Entity):
    __tablename__ = "locations"

    building_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("buildings.id"), index=True)
    floor: Mapped[int] = mapped_column(Integer)
    room: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(160))
    room_type: Mapped[str] = mapped_column(String(32), default="office")
    qr_code: Mapped[str] = mapped_column(String(64), unique=True)
    # Rectangle on the floor-plan SVG (viewBox 0 0 1000 400).
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    w: Mapped[float] = mapped_column(Float, default=100)
    h: Mapped[float] = mapped_column(Float, default=80)

    building: Mapped[Building] = relationship(back_populates="locations")
    assets: Mapped[list[Asset]] = relationship(back_populates="location")


class Asset(Entity):
    __tablename__ = "assets"

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    type: Mapped[str] = mapped_column(String(48))
    tag: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    make: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    location: Mapped[Location] = relationship(back_populates="assets")


class Team(Entity):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str] = mapped_column(String(48), unique=True)
    on_call_contact: Mapped[str] = mapped_column(String(160))


class Ticket(Entity):
    __tablename__ = "tickets"

    seq: Mapped[int] = mapped_column(Integer, unique=True)
    short_code: Mapped[str] = mapped_column(String(16), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(48), index=True)
    trade: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(4), index=True)
    is_hazard: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hazard_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # "snapfix" = created by the live intake pipeline; "seed" = synthetic history. AI-performance KPIs
    # (latency, time-to-triage) only count real pipeline tickets.
    source: Mapped[str] = mapped_column(String(16), default="snapfix")

    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"), nullable=True, index=True)
    location_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clusters.id"), nullable=True)

    sla_due_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    triaged_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, default=1)

    embedding: Mapped[Any | None] = mapped_column(VectorType, nullable=True)
    brief_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    brief_generated_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    building: Mapped[Building | None] = relationship()
    location: Mapped[Location | None] = relationship()
    asset: Mapped[Asset | None] = relationship()
    team: Mapped[Team | None] = relationship()
    reports: Mapped[list[Report]] = relationship(back_populates="ticket", order_by="Report.created_at")
    events: Mapped[list[TicketEvent]] = relationship(back_populates="ticket", order_by="TicketEvent.created_at")


Index("ix_tickets_building_status_created", Ticket.building_id, Ticket.status, Ticket.created_at)


class Report(Entity):
    __tablename__ = "reports"

    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporter_contact: Mapped[str | None] = mapped_column(String(160), nullable=True)
    location_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | confirmed | hazard_fast_path
    extracted_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # live | mock | fallback
    hazard_rule_hits: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    stage_timings: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # photo -> ticket, server side
    client_elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # page open -> submit
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    ticket: Mapped[Ticket | None] = relationship(back_populates="reports")


class TicketEvent(Entity):
    __tablename__ = "ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(64), default="ai")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class Cluster(Entity):
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(160))
    hypothesis: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    ticket_ids: Mapped[list] = mapped_column(JSONType, default=list)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | dismissed | confirmed
    parent_ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    llm_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)

    building: Mapped[Building | None] = relationship()


class SOP(Entity):
    __tablename__ = "sops"

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    trade: Mapped[str] = mapped_column(String(48))
    asset_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    body_md: Mapped[str] = mapped_column(Text)

    chunks: Mapped[list[SOPChunk]] = relationship(back_populates="sop", order_by="SOPChunk.section_no")


class SOPChunk(Entity):
    __tablename__ = "sop_chunks"

    sop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sops.id"), index=True)
    section_no: Mapped[int] = mapped_column(Integer)
    section_title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any | None] = mapped_column(VectorType, nullable=True)

    sop: Mapped[SOP] = relationship(back_populates="chunks")


class TimingRun(Entity):
    """Time-to-report measurements: legacy form (/baseline) vs SnapFix (/report)."""

    __tablename__ = "timing_runs"

    flow: Mapped[str] = mapped_column(String(16))  # baseline | snapfix
    seconds: Mapped[float] = mapped_column(Float)
    participant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Counter(Base):
    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
