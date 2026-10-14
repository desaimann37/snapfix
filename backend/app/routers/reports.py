"""Reporting flow: POST a photo/text/audio -> AI draft; confirm -> routed (or merged) ticket."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.images import ImageRejected
from app.config import get_settings
from app.db import get_db
from app.models import Location
from app.pipeline import PipelineError, confirm, hazard_out, intake
from app.routers.tickets import load_ticket
from app.schemas import ConfirmIn, ConfirmOut, ReportIntakeOut
from app.serializers import location_out, media_url, ticket_out

router = APIRouter(prefix="/api/reports", tags=["reports"])

MAX_TEXT = 2000


def _read_upload(upload: UploadFile | None, kind: str) -> bytes | None:
    if upload is None or not upload.filename:
        return None
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"{kind.title()} is larger than {get_settings().max_upload_mb} MB")
    if not data:
        return None
    ctype = (upload.content_type or "").lower()
    if kind == "image" and ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
        raise HTTPException(415, "Please upload an image file")
    if kind == "audio" and ctype and not (ctype.startswith("audio/") or ctype.startswith("video/webm")
                                          or ctype == "application/octet-stream"):
        raise HTTPException(415, "Please upload an audio file")
    return data


@router.post("", response_model=ReportIntakeOut)
def create_report(
    image: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    transcript: str = Form(default=""),
    location_code: str | None = Form(default=None),
    lat: float | None = Form(default=None),
    lng: float | None = Form(default=None),
    location_hint: str | None = Form(default=None),
    reporter_name: str | None = Form(default=None),
    reporter_contact: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ReportIntakeOut:
    image_bytes = _read_upload(image, "image")
    audio_bytes = _read_upload(audio, "audio")
    gps = (lat, lng) if lat is not None and lng is not None else None
    try:
        result = intake(
            db, image=image_bytes, text=text[:MAX_TEXT], transcript=transcript[:MAX_TEXT], audio=audio_bytes,
            audio_name=(audio.filename if audio else None) or "audio.webm", location_code=location_code, gps=gps,
            location_hint=(location_hint or "")[:200] or None, reporter_name=(reporter_name or "")[:120] or None,
            reporter_contact=(reporter_contact or "")[:160] or None,
        )
    except ImageRejected as exc:
        raise HTTPException(415, str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(exc.status, exc.message) from exc

    candidates = []
    if result.resolution.candidates:
        ids = [c.id for c in result.resolution.candidates]
        rows = db.scalars(select(Location).options(selectinload(Location.building)).where(Location.id.in_(ids))).all()
        order = {i: n for n, i in enumerate(ids)}
        candidates = [location_out(r) for r in sorted(rows, key=lambda r: order[r.id])]
    ticket = load_ticket(db, str(result.ticket.id)) if result.ticket else None
    return ReportIntakeOut(
        report_id=result.report.id,
        draft=result.draft,
        location=location_out(result.resolution.location),
        location_method=result.resolution.method,
        location_explanation=result.resolution.explanation,
        location_candidates=candidates,
        needs_confirmation=result.needs_confirmation,
        confirmation_reasons=result.reasons,
        hazard=hazard_out(result.hazard),
        llm_mode=result.extraction.mode,
        extraction_error=result.extraction.error,
        photo_url=media_url(result.report.photo_path),
        transcript=result.report.transcript,
        stt_error=result.stt_error,
        timings=result.timings,
        analysis_ms=result.analysis_ms,
        ticket=ticket_out(ticket) if ticket else None,
        merged=result.merged,
        message=result.message,
    )


@router.post("/{report_id}/confirm", response_model=ConfirmOut)
def confirm_report(report_id: uuid.UUID, body: ConfirmIn, db: Session = Depends(get_db)) -> ConfirmOut:
    try:
        result = confirm(db, report_id, body)
    except PipelineError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    ticket = load_ticket(db, str(result.ticket.id))
    return ConfirmOut(
        ticket=ticket_out(ticket),
        merged=result.merged,
        message=result.message,
        report_count=ticket.report_count,
        photo_to_ticket_ms=result.photo_to_ticket_ms,
        client_elapsed_ms=result.client_elapsed_ms,
        hazard=hazard_out(result.hazard),
        dedupe=result.dedupe,
    )
