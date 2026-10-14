"""Admin routes (protected by ADMIN_TOKEN): demo reset and the hidden offline-mock toggle."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db import SessionLocal
from app.events import broker
from app.runtime import effective_llm_mode, llm_mode_override, set_llm_mode_override

router = APIRouter(prefix="/api/admin", tags=["admin"])
_reset_lock = threading.Lock()


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or x_admin_token != get_settings().admin_token:
        raise HTTPException(401, "Admin token required (X-Admin-Token header)")


@router.post("/demo-reset", dependencies=[Depends(require_admin)])
def demo_reset() -> dict:
    """Wipe and reseed to the exact demo starting state."""
    from app.seed import generate

    if not _reset_lock.acquire(blocking=False):
        raise HTTPException(409, "A reset is already running")
    try:
        set_llm_mode_override(None)
        with SessionLocal() as db:
            summary = generate.run(db)
    finally:
        _reset_lock.release()
    broker.publish("ticket.updated", {"reset": True})
    broker.publish("cluster.updated", {"reset": True})
    return {"ok": True, "summary": summary, "llm_mode": effective_llm_mode()}


class LlmModeBody(BaseModel):
    mode: str | None  # "live" | "mock" | null (= follow LLM_MODE)


@router.get("/llm-mode", dependencies=[Depends(require_admin)])
def get_llm_mode() -> dict:
    return {"override": llm_mode_override(), "effective": effective_llm_mode()}


@router.post("/llm-mode", dependencies=[Depends(require_admin)])
def post_llm_mode(body: LlmModeBody) -> dict:
    try:
        set_llm_mode_override(body.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"override": llm_mode_override(), "effective": effective_llm_mode()}
