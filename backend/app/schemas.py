"""Pydantic request/response models and the AI structured-output schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app import taxonomy

CategoryKey = Literal[tuple(taxonomy.CATEGORY_KEYS)]  # type: ignore[valid-type]
TradeName = Literal[tuple(taxonomy.TRADES)]  # type: ignore[valid-type]
HazardType = Literal[tuple(taxonomy.HAZARD_TYPES)]  # type: ignore[valid-type]


# --------------------------------------------------------------------------------------------------
# AI schemas (structured outputs). Every field is required; optional values are nullable instead.
# --------------------------------------------------------------------------------------------------
class TicketDraft(BaseModel):
    """Photo + text -> structured ticket draft (spec 7.1)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="<= 70 chars, specific, e.g. 'Ceiling leak above lab bench'")
    summary: str = Field(description="1-3 sentences, factual: what / where / impact. No personal info.")
    category: CategoryKey
    trade: TradeName
    severity: Literal[1, 2, 3, 4]
    severity_reason: str
    is_hazard: bool
    hazard_type: Optional[HazardType]
    asset_type: Optional[str] = Field(description="sink, light fixture, door closer, ... or null")
    location_text_from_image: Optional[str] = Field(description="room numbers / signage readable in the photo")
    location_text_from_user: Optional[str] = Field(description="location words the reporter used")
    visible_evidence: list[str] = Field(description="short strings describing what is visible in the photo")
    needs_clarification: bool
    clarifying_question: Optional[str] = Field(description="ONE question, only if truly needed")
    confidence: float = Field(description="0-1")
    image_relevant: bool = Field(description="false if the photo is not of a facilities issue")


# --------------------------------------------------------------------------------------------------
# API output models
# --------------------------------------------------------------------------------------------------
class BuildingOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    floors: int
    lat: float
    lng: float


class LocationOut(BaseModel):
    id: uuid.UUID
    building_id: uuid.UUID
    building_code: str
    building_name: str
    floor: int
    room: str
    label: str
    room_type: str
    qr_code: str
    x: float
    y: float
    w: float
    h: float


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    trade: str


class AssetOut(BaseModel):
    id: uuid.UUID
    tag: str
    name: str
    type: str
    make: Optional[str] = None
    model: Optional[str] = None


class TicketOut(BaseModel):
    id: uuid.UUID
    short_code: str
    title: str
    summary: str
    category: str
    category_label: str
    trade: str
    severity: int
    priority: str
    is_hazard: bool
    hazard_type: Optional[str]
    status: str
    needs_review: bool
    report_count: int
    created_at: datetime
    updated_at: datetime
    sla_due_at: Optional[datetime]
    resolved_at: Optional[datetime]
    assignee: Optional[str]
    source: str
    team: Optional[TeamOut]
    location: Optional[LocationOut]
    location_text: Optional[str]
    asset: Optional[AssetOut]
    cluster_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    thumbnail_url: Optional[str]


class ReportOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    text: Optional[str]
    transcript: Optional[str]
    photo_url: Optional[str]
    status: str
    llm_mode: Optional[str]
    extraction_confidence: Optional[float]
    latency_ms: Optional[int]
    prompt_version: Optional[str]


class EventOut(BaseModel):
    id: uuid.UUID
    type: str
    actor: str
    rationale: Optional[str]
    payload: Optional[dict[str, Any]]
    created_at: datetime


class TicketDetail(TicketOut):
    reports: list[ReportOut]
    events: list[EventOut]
    brief: Optional[dict[str, Any]]
    brief_generated_at: Optional[datetime]
    children: list[TicketOut] = []


class TicketList(BaseModel):
    items: list[TicketOut]
    total: int


class TicketPatch(BaseModel):
    status: Optional[Literal["new", "triaged", "assigned", "in_progress", "resolved", "closed"]] = None
    assignee: Optional[str] = None
    actor: str = "dispatcher"
    note: Optional[str] = None
