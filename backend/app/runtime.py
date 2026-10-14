"""Process-wide runtime switches (e.g. the hidden admin 'offline mock fallback' toggle)."""

from __future__ import annotations

import logging
import threading

from app.config import get_settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_llm_mode_override: str | None = None
_warned_no_key = False


def set_llm_mode_override(mode: str | None) -> None:
    global _llm_mode_override
    if mode not in (None, "live", "mock"):
        raise ValueError("mode must be live, mock or None")
    with _lock:
        _llm_mode_override = mode


def llm_mode_override() -> str | None:
    return _llm_mode_override


def effective_llm_mode() -> str:
    """'live' only when configured AND an API key is present; otherwise 'mock' (the app keeps working)."""
    global _warned_no_key
    settings = get_settings()
    mode = _llm_mode_override or settings.llm_mode
    if mode == "live" and not settings.anthropic_api_key:
        if not _warned_no_key:
            log.warning("LLM_MODE=live but ANTHROPIC_API_KEY is empty; using mock mode")
            _warned_no_key = True
        return "mock"
    return "live" if mode == "live" else "mock"
