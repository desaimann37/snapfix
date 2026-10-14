"""Speech-to-text fallback for uploaded audio (the browser's Web Speech API is the primary path).

Uses faster-whisper `small.en` on CPU when installed (`uv sync --extra stt`); otherwise reports that the
fallback is unavailable and the user can type instead.
"""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)
MAX_AUDIO_MB = 10


@lru_cache
def _model():
    from faster_whisper import WhisperModel  # optional dependency

    return WhisperModel("small.en", device="cpu", compute_type="int8")


def transcribe(audio: bytes, filename: str = "audio.webm") -> tuple[str | None, str | None]:
    """Return (transcript, error)."""
    if get_settings().stt_fallback != "faster-whisper":
        return None, "Server speech-to-text is disabled; please type your report."
    if len(audio) > MAX_AUDIO_MB * 1024 * 1024:
        return None, f"Audio is larger than {MAX_AUDIO_MB} MB."
    try:
        model = _model()
    except ImportError:
        return None, "Server speech-to-text isn't installed (uv sync --extra stt); please type your report."
    except Exception as exc:  # model download / load failure
        log.warning("stt: model load failed: %s", exc)
        return None, "Speech-to-text is unavailable right now; please type your report."
    suffix = os.path.splitext(filename)[1] or ".webm"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        segments, _info = model.transcribe(path, language="en", beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return (text or None), (None if text else "No speech detected.")
    except Exception as exc:
        log.warning("stt: transcription failed: %s", exc)
        return None, "Couldn't transcribe that recording; please type your report."
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
