"""The intake pipeline, run as a deterministic sequence (reliable for a live demo).

intake():  photo/text/audio -> image prep -> speech-to-text -> HAZARD RULES -> extraction -> location
           If a hazard rule fires, a P1 ticket is created/merged and on-call is alerted immediately, before
           (and independently of) the LLM; AI enrichment of that ticket happens afterwards.
confirm(): edited draft + location -> hazards -> duplicate check -> merge or create -> route -> alerts + SSE
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.ai import images, stt
from app.ai.dedupe import ASK_LLM, DedupeResult, decide_duplicate, find_candidates
from app.ai.embeddings import embed_one, ticket_embedding_text
from app.ai.extract import Extraction, extract_draft, mock_extract, normalize
from app.ai.hazards import HazardDecision, decide, rule_hazards, safety_text
from app.ai.location import LocationResolution, resolve_location
from app.ai.routing import RoutingDecision, route_ticket
from app.config import get_settings
from app.db import is_postgres, session_scope
from app.events import broker
from app.models import Asset, Location, Report, Ticket, TimingRun, utcnow
from app.notify import Alert, send_alert
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
# Concurrency: two people reporting the same leak at the same moment must not create two tickets.
# --------------------------------------------------------------------------------------------------
_local_locks: dict[uuid.UUID | None, threading.Lock] = defaultdict(threading.Lock)


@contextmanager
def building_lock(db: Session, building_id: uuid.UUID | None):
    """Serialize dedupe + create per building. Postgres advisory lock (held until commit); a thread lock on SQLite."""
    if building_id is not None and is_postgres(db):
        key = int.from_bytes(building_id.bytes[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        yield
        return
    with _local_locks[building_id]:
        yield


def _run(target, *args) -> None:
    """Run side effects (alerts, AI enrichment) in the background in the app, inline in tests."""
    if get_settings().background_jobs:
        threading.Thread(target=target, args=args, daemon=True).start()
    else:
        target(*args)


def _load(db: Session, ticket_id: uuid.UUID) -> Ticket:
    return db.scalar(select(Ticket).options(
        selectinload(Ticket.location).selectinload(Location.building), selectinload(Ticket.team),
        selectinload(Ticket.asset), selectinload(Ticket.reports)).where(Ticket.id == ticket_id)
        .execution_options(populate_existing=True))


def publish(db: Session, event: str, ticket_id: uuid.UUID, **extra) -> None:
    from app.serializers import ticket_out  # local import: serializers imports schemas, not pipeline

    data = ticket_out(_load(db, ticket_id)).model_dump(mode="json")
    broker.publish(event, {**data, **extra} if extra else data)


def alert_on_call(db: Session, ticket_id: uuid.UUID) -> None:
    ticket = _load(db, ticket_id)
    label = taxonomy.HAZARD_LABELS.get(ticket.hazard_type or "", "Hazard")
    where = (f"{ticket.location.building.name}, {ticket.location.label}" if ticket.location
             else (ticket.location_text or "location unconfirmed"))
    s = safety_text(ticket.hazard_type, get_settings().emergency_text)
    broker.publish("hazard.alert", {"id": str(ticket.id), "short_code": ticket.short_code, "title": ticket.title,
                                    "hazard_type": ticket.hazard_type, "label": label, "location": where,
                                    "safety_text": s, "priority": ticket.priority})
    alert = Alert(ticket_id=ticket.id, short_code=ticket.short_code, title=ticket.title,
                  hazard_type=ticket.hazard_type, hazard_label=label, location=where, priority=ticket.priority,
                  safety_text=s, url_path=f"/tickets/{ticket.short_code}")
    if get_settings().background_jobs:
        send_alert(alert, background=True)
    else:
        send_alert(alert, background=False)


# --------------------------------------------------------------------------------------------------
# Ticket creation / merging
# --------------------------------------------------------------------------------------------------
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


def create_ticket(
    db: Session,
    *,
    draft: TicketDraft,
    location: Location | None,
    hazard: HazardDecision,
    report: Report,
    embedding: list[float] | None = None,
    dedupe: DedupeResult | None = None,
    location_text: str | None = None,
    building_id: uuid.UUID | None = None,
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
    if embedding is None:
        embedding = embed_one(ticket_embedding_text(draft.title, draft.summary, category, draft.asset_type))
    ticket = Ticket(
        id=uuid.uuid4(), seq=seq, short_code=short_code_for(seq), title=draft.title, summary=draft.summary,
        category=category, trade=decision.trade, severity=severity, priority=decision.priority,
        is_hazard=hazard.is_hazard, hazard_type=hazard.hazard_type,
        status="new" if needs_review else "triaged", needs_review=needs_review, source="snapfix",
        building_id=location.building_id if location else building_id, location_id=location.id if location else None,
        location_text=location_text, asset_id=asset.id if asset else None, team_id=decision.team_id,
        sla_due_at=decision.sla_due_at, triaged_at=now, report_count=1, embedding=embedding,
    )
    db.add(ticket)
    db.flush()
    report.ticket_id = ticket.id

    evidence = "; ".join(draft.visible_evidence) if draft.visible_evidence else "no photo evidence"
    dup_note = f" Duplicate check: {dedupe.rationale}" if dedupe is not None else ""
    add_event(db, ticket, "created", actor="ai", rationale=(
        f"Classified as '{category}' ({decision.trade}), severity {severity}. {draft.severity_reason} "
        f"Evidence: {evidence}. Confidence {draft.confidence:.2f}.{actor_note}{dup_note}").strip(),
        payload={"category": category, "trade": decision.trade, "severity": severity,
                 "confidence": draft.confidence, "llm_mode": report.llm_mode,
                 "prompt_version": report.prompt_version, "asset": asset.tag if asset else None,
                 "dedupe": dedupe.payload() if dedupe is not None else None})
    if hazard.is_hazard:
        add_event(db, ticket, "escalated", actor="ai", rationale=f"{hazard.rationale} Forced P1 and alerted on-call.",
                  payload=hazard.as_payload())
    add_event(db, ticket, "assigned", actor="ai", rationale=decision.rationale, payload=decision.as_payload())
    return ticket, decision


def merge_into_ticket(
    db: Session, ticket: Ticket, report: Report, *, draft: TicketDraft, hazard: HazardDecision, dedupe: DedupeResult,
) -> bool:
    """Attach the report to an existing ticket; severity/priority can only go UP. Returns True if newly a hazard."""
    report.ticket_id = ticket.id
    report.status = "merged"
    ticket.report_count += 1
    old_sev, old_pri = ticket.severity, ticket.priority
    newly_hazard = hazard.is_hazard and not ticket.is_hazard
    new_sev = 4 if hazard.is_hazard else draft.severity
    ticket.severity = max(ticket.severity, new_sev)
    if newly_hazard:
        ticket.is_hazard, ticket.hazard_type = True, hazard.hazard_type
    if ticket.severity > old_sev or newly_hazard:  # only re-route when something got worse
        decision = route_ticket(db, category=ticket.category, severity=ticket.severity, is_hazard=ticket.is_hazard,
                                room_type=ticket.location.room_type if ticket.location else None)
        if taxonomy.PRIORITIES.index(decision.priority) < taxonomy.PRIORITIES.index(ticket.priority):
            ticket.priority = decision.priority
            if ticket.sla_due_at is None or decision.sla_due_at < ticket.sla_due_at:
                ticket.sla_due_at = decision.sla_due_at
    ticket.updated_at = utcnow()

    changes = []
    if ticket.severity != old_sev:
        changes.append(f"severity {old_sev} -> {ticket.severity}")
    if ticket.priority != old_pri:
        changes.append(f"priority {old_pri} -> {ticket.priority}")
    change_note = f" Re-evaluated: {', '.join(changes)}." if changes else " Severity unchanged (only goes up)."
    add_event(db, ticket, "merged", actor="ai",
              rationale=f"Report #{ticket.report_count} merged. {dedupe.rationale}{change_note}",
              payload={**dedupe.payload(), "report_id": str(report.id), "report_count": ticket.report_count,
                       "severity": {"from": old_sev, "to": ticket.severity},
                       "priority": {"from": old_pri, "to": ticket.priority}})
    if newly_hazard:
        add_event(db, ticket, "escalated", actor="ai",
                  rationale=f"{hazard.rationale} A new report raised this ticket to a P1 hazard.",
                  payload=hazard.as_payload())
    return newly_hazard


def merged_message(ticket: Ticket, has_photo: bool) -> str:
    added = "We added your photo" if has_photo else "We added your report"
    people = f"{ticket.report_count} people have reported this"
    return f"Already reported ({ticket.short_code}). {added}. {people}."


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
    image_jpeg = processed.jpeg if processed else None

    if rule_hits:
        return _hazard_fast_path(db, report=report, rule_hits=rule_hits, combined=combined, gps=gps,
                                 image_jpeg=image_jpeg, context=context, timings=timings, started=started,
                                 stt_error=stt_error)

    t = time.perf_counter()
    extraction = extract_draft(image_jpeg=image_jpeg, text=combined, location_context=context)
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

    _record_extraction(report, extraction)
    report.hazard_rule_hits = []
    report.location_id = resolution.location.id if resolution.location else None
    analysis_ms = _ms(started)
    report.stage_timings = {**timings, "analysis_ms": analysis_ms}
    db.add(report)
    db.commit()
    log.info("intake", extra={"report_id": str(report.id), "llm_mode": extraction.mode, "category": draft.category,
                              "confidence": draft.confidence, "hazard": hazard.is_hazard, **report.stage_timings})
    return IntakeResult(report=report, draft=draft, extraction=extraction, resolution=resolution, hazard=hazard,
                        needs_confirmation=bool(reasons), reasons=reasons, timings=timings, analysis_ms=analysis_ms,
                        stt_error=stt_error)


def _record_extraction(report: Report, extraction: Extraction) -> None:
    usage = extraction.usage
    report.extracted_json = extraction.draft.model_dump()
    report.extraction_confidence = extraction.draft.confidence
    report.prompt_version = extraction.prompt_version
    report.llm_mode = extraction.mode
    report.input_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    report.output_tokens = usage.output_tokens
    report.cost_usd = usage.cost_usd


def _hazard_fast_path(db: Session, *, report: Report, rule_hits, combined: str, gps, image_jpeg: bytes | None,
                      context: str | None, timings: dict, started: float, stt_error: str | None) -> IntakeResult:
    """Rules fired: create (or merge into) a P1 ticket and alert on-call now, with no LLM in the loop."""
    t = time.perf_counter()
    hazard = decide(rule_hits)
    draft = normalize(mock_extract(combined, has_image=image_jpeg is not None)).model_copy(
        update={"is_hazard": True, "hazard_type": hazard.hazard_type, "severity": 4,
                "severity_reason": hazard.rationale})
    resolution = resolve_location(db, qr_code=report.location_code, user_text=combined, gps=gps)
    location = resolution.location
    cand_buildings = {c.building_id for c in resolution.candidates}
    building_id = location.building_id if location else (cand_buildings.pop() if len(cand_buildings) == 1 else None)
    embedding = embed_one(ticket_embedding_text(draft.title, draft.summary, draft.category, draft.asset_type))
    extraction = Extraction(draft=draft, mode="rules", latency_ms=0, prompt_version="hazard_rules")

    with building_lock(db, building_id):
        candidates = find_candidates(db, building_id=building_id, location=location, category=draft.category,
                                     embedding=embedding)
        # Deterministic for hazards (no LLM wait): merge on a clear match, or the same room + same hazard type.
        best = candidates[0] if candidates else None
        same_place_same_hazard = (best is not None and location is not None and best.ticket.location_id == location.id
                                  and best.ticket.is_hazard and best.ticket.hazard_type == hazard.hazard_type)
        same_room_clear_match = best is not None and best.location_score == 1.0 and best.score >= 0.80
        if best is not None and (same_room_clear_match or (best.score >= ASK_LLM and same_place_same_hazard)):
            dedupe = DedupeResult("merge", best, candidates)
            newly_hazard = merge_into_ticket(db, best.ticket, report, draft=draft, hazard=hazard, dedupe=dedupe)
            ticket, merged, alert = best.ticket, True, newly_hazard
        else:
            dedupe = DedupeResult("new", best, candidates)
            loc_text = None if location else (draft.location_text_from_user or combined[:200])
            ticket, _ = create_ticket(db, draft=draft, location=location, hazard=hazard, report=report,
                                      embedding=embedding, dedupe=dedupe, building_id=building_id,
                                      location_text=loc_text,
                                      actor_note=" Instant hazard path: created from keyword rules before AI analysis.")
            report.status = "hazard_fast_path"
            merged, alert = False, True
        report.extracted_json = draft.model_dump()
        report.extraction_confidence = draft.confidence
        report.prompt_version = "hazard_rules"
        report.llm_mode = "rules"
        report.hazard_rule_hits = [h.as_dict() for h in rule_hits]
        report.location_id = location.id if location else None
        timings["hazard_fast_path_ms"] = _ms(t)
        analysis_ms = _ms(started)
        report.stage_timings = {**timings, "analysis_ms": analysis_ms}
        report.latency_ms = analysis_ms
        db.add(report)
        db.commit()

    publish(db, "ticket.merged" if merged else "ticket.created", ticket.id, report_count=ticket.report_count)
    if alert:
        alert_on_call(db, ticket.id)
    if not merged:
        _run(enrich_ticket, report.id, ticket.id, image_jpeg, combined, context)
    log.info("hazard fast path", extra={"ticket": ticket.short_code, "merged": merged, "hazard": hazard.hazard_type,
                                        **report.stage_timings})
    message = merged_message(ticket, image_jpeg is not None) if merged else (
        f"Emergency alert sent: {ticket.short_code} is a P1 for {ticket.team.name if ticket.team else ticket.trade}.")
    return IntakeResult(report=report, draft=draft, extraction=extraction, resolution=resolution, hazard=hazard,
                        needs_confirmation=False, reasons=[], timings=timings, analysis_ms=analysis_ms,
                        stt_error=stt_error, ticket=ticket, merged=merged, message=message)


def enrich_ticket(report_id: uuid.UUID, ticket_id: uuid.UUID, image_jpeg: bytes | None, combined: str,
                  context: str | None) -> None:
    """After an instant hazard ticket: let the model add a better title/summary/asset. Never removes the hazard."""
    t = time.perf_counter()
    extraction = extract_draft(image_jpeg=image_jpeg, text=combined, location_context=context)
    try:
        with session_scope() as db:
            report, ticket = db.get(Report, report_id), db.get(Ticket, ticket_id)
            if report is None or ticket is None:
                return
            _record_extraction(report, extraction)
            report.stage_timings = {**(report.stage_timings or {}), "enrich_ms": _ms(t)}
            if extraction.mode == "fallback" or ticket.report_count > 1:
                return
            d = extraction.draft
            ticket.title, ticket.summary = d.title, d.summary
            if ticket.location_id and (asset := pick_asset(db, db.get(Location, ticket.location_id), d.asset_type)):
                ticket.asset_id = asset.id
            ticket.embedding = embed_one(ticket_embedding_text(d.title, d.summary, ticket.category, d.asset_type))
            extra = ""
            if d.is_hazard and d.hazard_type and d.hazard_type != ticket.hazard_type:
                extra = f" The model also noted a possible {taxonomy.HAZARD_LABELS[d.hazard_type]} hazard."
            add_event(db, ticket, "enriched", actor="ai",
                      rationale=f"AI analysis added details after the instant alert ({extraction.mode}). "
                                f"Hazard flag kept (rules can't be overridden).{extra}",
                      payload={"title": d.title, "evidence": d.visible_evidence, "confidence": d.confidence,
                               "llm_mode": extraction.mode})
        with session_scope() as db:
            publish(db, "ticket.updated", ticket_id)
    except Exception:
        log.exception("enrichment failed", extra={"ticket_id": str(ticket_id)})


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


def _set_location_on_existing(db: Session, report: Report, ticket: Ticket, location_id: uuid.UUID) -> None:
    """The hazard fast path may create a ticket before we know the room; the reporter can add it afterwards."""
    location = db.get(Location, location_id)
    if location is None or ticket.location_id is not None:
        return
    ticket.location_id, ticket.building_id, ticket.location_text = location.id, location.building_id, None
    report.location_id = location.id
    add_event(db, ticket, "location_set", actor="reporter",
              rationale=f"Reporter confirmed the location: {location.label}.", payload={"location": location.qr_code})
    db.commit()
    publish(db, "ticket.updated", ticket.id)


def confirm(db: Session, report_id: uuid.UUID, body: ConfirmIn) -> ConfirmResult:
    started = time.perf_counter()
    report = db.get(Report, report_id)
    if report is None:
        raise PipelineError(404, "Report not found")
    if report.ticket_id is not None:  # idempotent (double tap) / hazard fast path already created it
        ticket = db.get(Ticket, report.ticket_id)
        if body.location_id:
            _set_location_on_existing(db, report, ticket, body.location_id)
        hazard = decide(rule_hazards(report_text(report)), ticket.is_hazard, ticket.hazard_type)
        return ConfirmResult(ticket, report.status == "merged", f"Already submitted as {ticket.short_code}.",
                             hazard, report.latency_ms or 0, report.client_elapsed_ms)

    draft, edited = apply_edits(TicketDraft(**report.extracted_json), body)
    location = db.get(Location, body.location_id) if body.location_id else (
        db.get(Location, report.location_id) if report.location_id else None)
    if location is None:
        raise PipelineError(422, "Please choose where this is before submitting.")

    hazard = decide(rule_hazards(report_text(report), report.location_hint), draft.is_hazard, draft.hazard_type)
    embedding = embed_one(ticket_embedding_text(draft.title, draft.summary, draft.category, draft.asset_type))
    note = f" Reporter edited: {', '.join(edited)}." if edited else ""

    with building_lock(db, location.building_id):
        t = time.perf_counter()
        candidates = find_candidates(db, building_id=location.building_id, location=location,
                                     category=draft.category, embedding=embedding)
        dedupe = decide_duplicate(candidates, title=draft.title, summary=draft.summary, category=draft.category,
                                  location=location)
        dedupe_ms = _ms(t)
        if dedupe.decision == "merge" and dedupe.best is not None:
            ticket = dedupe.best.ticket
            alert = merge_into_ticket(db, ticket, report, draft=draft, hazard=hazard, dedupe=dedupe)
            merged = True
        else:
            ticket, _ = create_ticket(db, draft=draft, location=location, hazard=hazard, report=report,
                                      embedding=embedding, dedupe=dedupe,
                                      needs_review=report.llm_mode == "fallback", actor_note=note)
            report.status = "confirmed"
            merged, alert = False, hazard.is_hazard

        confirm_ms = _ms(started)
        report.location_id = location.id
        report.extracted_json = draft.model_dump()
        report.client_elapsed_ms = body.client_elapsed_ms
        report.latency_ms = int((report.stage_timings or {}).get("analysis_ms", 0)) + confirm_ms
        report.stage_timings = {**(report.stage_timings or {}), "dedupe_ms": dedupe_ms, "confirm_ms": confirm_ms}
        report.input_tokens += dedupe.usage.input_tokens + dedupe.usage.cache_read_tokens
        report.output_tokens += dedupe.usage.output_tokens
        report.cost_usd = round(report.cost_usd + dedupe.usage.cost_usd, 6)
        if body.client_elapsed_ms:
            db.add(TimingRun(flow="snapfix", seconds=round(body.client_elapsed_ms / 1000, 2),
                             notes=f"{ticket.short_code} via /report"))
        db.commit()

    publish(db, "ticket.merged" if merged else "ticket.created", ticket.id, report_count=ticket.report_count)
    if alert:
        alert_on_call(db, ticket.id)
    log.info("confirm", extra={"ticket": ticket.short_code, "merged": merged, "priority": ticket.priority,
                               "hazard": ticket.is_hazard, "photo_to_ticket_ms": report.latency_ms,
                               "dedupe_ms": dedupe_ms, "dedupe": dedupe.decision})
    team = ticket.team.name if ticket.team else ticket.trade
    message = (merged_message(ticket, report.photo_path is not None) if merged else
               f"Ticket {ticket.short_code} created and sent to {team} ({ticket.priority}).")
    return ConfirmResult(ticket=ticket, merged=merged, message=message, hazard=hazard,
                         photo_to_ticket_ms=report.latency_ms, client_elapsed_ms=body.client_elapsed_ms,
                         dedupe=dedupe.payload())


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
