"""Taxonomy + public config for the frontend."""

from __future__ import annotations

from fastapi import APIRouter

from app import taxonomy
from app.config import get_settings
from app.runtime import effective_llm_mode

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/taxonomy")
def get_taxonomy() -> dict:
    return {
        "trades": taxonomy.TRADES,
        "categories": [
            {"key": c.key, "label": c.label, "trade": c.trade, "description": c.description,
             "default_severity": c.default_severity}
            for c in taxonomy.CATEGORIES
        ],
        "severities": {str(k): v for k, v in taxonomy.SEVERITY_DEFINITIONS.items()},
        "hazard_types": [{"key": h, "label": taxonomy.HAZARD_LABELS[h]} for h in taxonomy.HAZARD_TYPES],
        "priorities": [{"key": p, "sla_hours": taxonomy.SLA_HOURS[p]} for p in taxonomy.PRIORITIES],
    }


@router.get("/config/public")
def public_config() -> dict:
    s = get_settings()
    return {
        "emergency_text": s.emergency_text,
        "llm_mode": effective_llm_mode(),
        "max_upload_mb": s.max_upload_mb,
        "stt_fallback": s.stt_fallback,
    }
