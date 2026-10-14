"""The intake pipeline, run as a deterministic sequence (reliable for a live demo).

intake():  photo/text/audio -> image prep -> speech-to-text -> hazard rules -> extraction -> location
confirm(): edited draft + location -> hazards -> route -> ticket + audit events
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.ai import images, stt
from app.ai.embeddings import embed_one, ticket_embedding_text
from app.ai.extract import Extraction, extract_draft
from app.ai.hazards import HazardDecision, decide, rule_hazards, safety_text
from app.ai.location import LocationResolution, resolve_location
from app.ai.routing import RoutingDecision, route_ticket
from app.config import get_settings
from app.models import Asset, Location, Report, Ticket, TimingRun, utcnow
from app.schemas import ConfirmIn, TicketDraft
from app.services import add_event, next_ticket_seq, short_code_for

log = logging.getLogger("snapfix.pipeline")


class PipelineError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def report_text(report: Report) -> str:
    return " ".join(x for x in (report.text, report.transcript) if x).strip()


# --------------------------------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------------------------------
@dataclass
class IntakeResult:
    report: Report
    draft: TicketDraft
    extraction: Extraction
    resolution: LocationResolution
    hazard: HazardDecision
    needs_confirmation: bool
    reasons: list[str]
    timings: dict[str, int]
    analysis_ms: int
    stt_error: str | None = None
    ticket: Ticket | None = None
    merged: bool = False
    message: str | None = None


def intake(
    db: Session,
    *,
    image: bytes | None = None,
    text: str = "",
    transcript: str = "",
    audio: bytes | None = None,
    audio_name: str = "audio.webm",
    location_code: str | None = None,
    gps: tuple[float, float] | None = None,
    location_hint: str | None = None,
    reporter_name: str | None = None,
    reporter_contact: str | None = None,
) -> IntakeResult:
    settings = get_settings()
    started = time.perf_counter()
    timings: dict[str, int] = {}
    report = Report(id=uuid.uuid4(), text=text.strip() or None, transcript=transcript.strip() or None,
                    reporter_name=reporter_name or None, reporter_contact=reporter_contact or None,
                    location_hint=location_hint or None, location_code=(location_code or "").lower() or None)

    processed = None
    if image:
        t = time.perf_counter()
        processed = images.preprocess(image)
        timings["image_ms"] = _ms(t)
        if processed.gps and gps is None:
            gps = processed.gps
        filename = f"{report.id}.jpg"
        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
        (Path(settings.upload_dir) / filename).write_bytes(processed.jpeg)
        report.photo_path = filename
    if gps:
        report.gps_lat, report.gps_lng = gps

    stt_error = None
    if audio and not report.transcript:
        t = time.perf_counter()
        spoken, stt_error = stt.transcribe(audio, audio_name)
        timings["stt_ms"] = _ms(t)
        report.transcript = spoken

    combined = report_text(report)
    if not combined and processed is None:
        raise PipelineError(422, stt_error or "Add a photo or a short description.")

    # Deterministic hazard rules run before (and independently of) the model.
    t = time.perf_counter()
    rule_hits = rule_hazards(combined, location_hint)
    timings["hazard_rules_ms"] = _ms(t)

    qr_loc = None
    if report.location_code:
        qr_loc = db.scalar(select(Location).options(selectinload(Location.building))
                           .where(Location.qr_code == report.location_code))
    context = f"{qr_loc.building.name}, {qr_loc.label} (room {qr_loc.room})" if qr_loc else None

    t = time.perf_counter()
    extraction = extract_draft(image_jpeg=processed.jpeg if processed else None, text=combined,
                               location_context=context)
    timings["extract_ms"] = _ms(t)
    draft = extraction.draft

    t = time.perf_counter()
    resolution = resolve_location(db, qr_code=report.location_code, user_text=f"{combined} {location_hint or ''}",
                                  image_text=draft.location_text_from_image, gps=gps)
    timings["location_ms"] = _ms(t)

    hazard = decide(rule_hits, draft.is_hazard, draft.hazard_type)
    reasons: list[str] = []
    if extraction.mode == "fallback":
        reasons.append("Automatic analysis is unavailable right now. Please check the details.")
    if not draft.image_relevant:
        reasons.append("The photo doesn't seem to show a facilities problem.")
    if draft.confidence < 0.5 and extraction.mode != "fallback":
        reasons.append("We're not sure we got this right. Please check the details.")
    if draft.needs_clarification and draft.clarifying_question:
        reasons.append(draft.clarifying_question)
    if resolution.location is None:
        reasons.append("Please choose where this is.")

    report.extracted_json = draft.model_dump()
    report.extraction_confidence = draft.confidence
    report.prompt_version = extraction.prompt_version
    report.llm_mode = extraction.mode
    report.hazard_rule_hits = [h.as_dict() for h in rule_hits]
    report.location_id = resolution.location.id if resolution.location else None
    usage = extraction.usage
    report.input_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    report.output_tokens = extraction.usage.output_tokens
    report.cost_usd = extraction.usage.cost_usd
    analysis_ms = _ms(started)
    report.stage_timings = {**timings, "analysis_ms": analysis_ms}
    db.add(report)
    db.commit()
    log.info("intake", extra={"report_id": str(report.id), "llm_mode": extraction.mode, "category": draft.category,
                              "confidence": draft.confidence, "hazard": hazard.is_hazard, **report.stage_timings})
    return IntakeResult(report=report, draft=draft, extraction=extraction, resolution=resolution, hazard=hazard,
                        needs_confirmation=bool(reasons), reasons=reasons, timings=timings, analysis_ms=analysis_ms,
                        stt_error=stt_error)


# --------------------------------------------------------------------------------------------------
# Confirm
# --------------------------------------------------------------------------------------------------
@dataclass
class ConfirmResult:
    ticket: Ticket
    merged: bool
    message: str
    hazard: HazardDecision
    photo_to_ticket_ms: int
    client_elapsed_ms: int | None
    dedupe: dict | None = field(default=None)


def pick_asset(db: Session, location: Location, asset_type: str | None) -> Asset | None:
    canonical = taxonomy.canonical_asset_type(asset_type)
    if not canonical:
        return None
    assets = list(db.scalars(select(Asset).where(Asset.location_id == location.id, Asset.type == canonical)
                             .order_by(Asset.tag)))
    if len(assets) <= 1:
        return assets[0] if assets else None
    # Several of the same kind (e.g. two sinks): prefer the one with the most recent ticket history.
    last = dict(db.execute(select(Ticket.asset_id, func.max(Ticket.created_at))
                           .where(Ticket.asset_id.in_([a.id for a in assets])).group_by(Ticket.asset_id)).all())
    with_history = [a for a in assets if a.id in last]
    return max(with_history, key=lambda a: last[a.id]) if with_history else assets[0]


def apply_edits(draft: TicketDraft, body: ConfirmIn) -> tuple[TicketDraft, list[str]]:
    data = draft.model_dump()
    edited = []
    for name in ("title", "summary", "category", "severity"):
        value = getattr(body.edits, name)
        if value is not None and value != data[name]:
            data[name] = value
            edited.append(name)
    data["trade"] = taxonomy.trade_for_category(data["category"])
    return TicketDraft(**data), edited


def create_ticket(
    db: Session,
    *,
    draft: TicketDraft,
    location: Location | None,
    hazard: HazardDecision,
    report: Report,
    location_text: str | None = None,
    needs_review: bool = False,
    actor_note: str = "",
) -> tuple[Ticket, RoutingDecision]:
    severity = 4 if hazard.is_hazard else draft.severity
    category = draft.category
    asset = pick_asset(db, location, draft.asset_type) if location else None
    decision = route_ticket(db, category=category, severity=severity, is_hazard=hazard.is_hazard,
                            room_type=location.room_type if location else None)
    seq = next_ticket_seq(db)
    now = utcnow()
    ticket = Ticket(
        id=uuid.uuid4(), seq=seq, short_code=short_code_for(seq), title=draft.title, summary=draft.summary,
        category=category, trade=decision.trade, severity=severity, priority=decision.priority,
        is_hazard=hazard.is_hazard, hazard_type=hazard.hazard_type,
        status="new" if needs_review else "triaged", needs_review=needs_review, source="snapfix",
        building_id=location.building_id if location else None, location_id=location.id if location else None,
        location_text=location_text, asset_id=asset.id if asset else None, team_id=decision.team_id,
        sla_due_at=decision.sla_due_at, triaged_at=now, report_count=1,
        embedding=embed_one(ticket_embedding_text(draft.title, draft.summary, category, draft.asset_type)),
    )
    db.add(ticket)
    db.flush()
    report.ticket_id = ticket.id

    evidence = "; ".join(draft.visible_evidence) if draft.visible_evidence else "no photo evidence"
    add_event(db, ticket, "created", actor="ai", rationale=(
        f"Classified as '{category}' ({decision.trade}), severity {severity}. {draft.severity_reason} "
        f"Evidence: {evidence}. Confidence {draft.confidence:.2f}.{actor_note}").strip(),
        payload={"category": category, "trade": decision.trade, "severity": severity,
                 "confidence": draft.confidence, "llm_mode": report.llm_mode,
                 "prompt_version": report.prompt_version, "asset": asset.tag if asset else None})
    if hazard.is_hazard:
        add_event(db, ticket, "escalated", actor="ai", rationale=f"{hazard.rationale} Forced P1.",
                  payload=hazard.as_payload())
    add_event(db, ticket, "assigned", actor="ai", rationale=decision.rationale, payload=decision.as_payload())
    return ticket, decision


def confirm(db: Session, report_id: uuid.UUID, body: ConfirmIn) -> ConfirmResult:
    started = time.perf_counter()
    report = db.get(Report, report_id)
    if report is None:
        raise PipelineError(404, "Report not found")
    if report.ticket_id is not None:  # idempotent: a double tap returns the same ticket
        ticket = db.get(Ticket, report.ticket_id)
        hazard = decide(rule_hazards(report_text(report)), ticket.is_hazard, ticket.hazard_type)
        return ConfirmResult(ticket, report.status == "merged", f"Already submitted as {ticket.short_code}.",
                             hazard, report.latency_ms or 0, report.client_elapsed_ms)

    draft, edited = apply_edits(TicketDraft(**report.extracted_json), body)
    location = db.get(Location, body.location_id) if body.location_id else (
        db.get(Location, report.location_id) if report.location_id else None)
    if location is None:
        raise PipelineError(422, "Please choose where this is before submitting.")

    text = report_text(report)
    hazard = decide(rule_hazards(text, report.location_hint), draft.is_hazard, draft.hazard_type)
    note = f" Reporter edited: {', '.join(edited)}." if edited else ""
    ticket, decision = create_ticket(db, draft=draft, location=location, hazard=hazard, report=report,
                                     needs_review=report.llm_mode == "fallback", actor_note=note)

    confirm_ms = _ms(started)
    report.status = "confirmed"
    report.location_id = location.id
    report.extracted_json = draft.model_dump()
    report.client_elapsed_ms = body.client_elapsed_ms
    report.latency_ms = int((report.stage_timings or {}).get("analysis_ms", 0)) + confirm_ms
    report.stage_timings = {**(report.stage_timings or {}), "confirm_ms": confirm_ms}
    if body.client_elapsed_ms:
        db.add(TimingRun(flow="snapfix", seconds=round(body.client_elapsed_ms / 1000, 2),
                         notes=f"{ticket.short_code} via /report"))
    db.commit()
    log.info("confirm", extra={"ticket": ticket.short_code, "priority": ticket.priority, "hazard": hazard.is_hazard,
                               "photo_to_ticket_ms": report.latency_ms, "confirm_ms": confirm_ms})
    team = decision.team_name or decision.trade
    return ConfirmResult(ticket=ticket, merged=False,
                         message=f"Ticket {ticket.short_code} created and sent to {team} ({ticket.priority}).",
                         hazard=hazard, photo_to_ticket_ms=report.latency_ms,
                         client_elapsed_ms=body.client_elapsed_ms)


def hazard_out(hazard: HazardDecision) -> dict:
    return {
        "is_hazard": hazard.is_hazard,
        "hazard_type": hazard.hazard_type,
        "label": taxonomy.HAZARD_LABELS.get(hazard.hazard_type or ""),
        "rule_hits": [h.match for h in hazard.rule_hits],
        "sources": hazard.sources,
        "rationale": hazard.rationale,
        "safety_text": safety_text(hazard.hazard_type, get_settings().emergency_text) if hazard.is_hazard else None,
    }
