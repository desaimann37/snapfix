"""Anthropic client wrapper: live/mock switch, timeouts + retries, structured outputs, usage/cost/timing logs.

Every AI call goes through `LLMClient` and supplies a deterministic `mock` callable, so the app, tests and
demo run without an API key or internet (`LLM_MODE=mock`, or automatically when no key is configured).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Generic, TypeVar

import anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.runtime import effective_llm_mode

log = logging.getLogger("snapfix.llm")

T = TypeVar("T", bound=BaseModel)
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class LLMError(RuntimeError):
    """Any failure of a live call (network, timeout, refusal, truncation). Callers degrade gracefully."""


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: LLMUsage) -> LLMUsage:
        return LLMUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            round(self.cost_usd + other.cost_usd, 6),
        )

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass
class LLMResult(Generic[T]):
    value: T
    mode: str  # live | mock
    model: str | None
    latency_ms: int
    usage: LLMUsage = field(default_factory=LLMUsage)


@lru_cache
def load_prompt(name: str) -> str:
    """Versioned prompt files live in app/ai/prompts/<name>.md."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _cost(role: str, usage: Any) -> float:
    s = get_settings()
    price_in, price_out = (s.price_main_input, s.price_main_output) if role == "main" else (
        s.price_fast_input, s.price_fast_output)
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    dollars = (
        usage.input_tokens * price_in
        + cache_write * price_in * 1.25
        + cache_read * price_in * 0.10
        + usage.output_tokens * price_out
    ) / 1_000_000
    return round(dollars, 6)


def _usage(role: str, raw: Any) -> LLMUsage:
    return LLMUsage(
        input_tokens=raw.input_tokens or 0,
        output_tokens=raw.output_tokens or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
        cost_usd=_cost(role, raw),
    )


class LLMClient:
    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None

    @property
    def mode(self) -> str:
        return effective_llm_mode()

    def model_for(self, role: str) -> str:
        s = get_settings()
        return s.anthropic_model_main if role == "main" else s.anthropic_model_fast

    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            s = get_settings()
            self._client = anthropic.Anthropic(
                api_key=s.anthropic_api_key, timeout=s.llm_timeout_s, max_retries=s.llm_max_retries)
        return self._client

    # ------------------------------------------------------------------------------------------
    def structured(
        self,
        *,
        stage: str,
        role: str,
        system: str,
        content: list[dict] | str,
        schema: type[T],
        mock: Callable[[], T],
        max_tokens: int = 2048,
        effort: str = "low",
    ) -> LLMResult[T]:
        """One schema-constrained call (structured outputs). The system prompt is cached (it's stable)."""
        started = time.perf_counter()
        if self.mode == "mock":
            value = mock()
            ms = int((time.perf_counter() - started) * 1000)
            log.info("llm call", extra={"stage": stage, "mode": "mock", "latency_ms": ms})
            return LLMResult(value=value, mode="mock", model=None, latency_ms=ms)

        model = self.model_for(role)
        try:
            response = self.client().messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": effort},
            )
        except anthropic.APIStatusError as exc:  # 4xx/5xx after SDK retries
            raise LLMError(f"{stage}: API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise LLMError(f"{stage}: connection error: {exc}") from exc
        except anthropic.AnthropicError as exc:
            raise LLMError(f"{stage}: {exc}") from exc
        except Exception as exc:  # schema validation of the parsed output, etc.
            raise LLMError(f"{stage}: {exc}") from exc

        ms = int((time.perf_counter() - started) * 1000)
        usage = _usage(role, response.usage)
        log.info("llm call", extra={"stage": stage, "mode": "live", "model": model, "latency_ms": ms,
                                    "stop_reason": response.stop_reason, "request_id": response._request_id,
                                    **usage.as_dict()})
        if response.stop_reason == "refusal":
            raise LLMError(f"{stage}: model declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"{stage}: output truncated at max_tokens")
        if response.parsed_output is None:
            raise LLMError(f"{stage}: no structured output returned")
        return LLMResult(value=response.parsed_output, mode="live", model=model, latency_ms=ms, usage=usage)

    # ------------------------------------------------------------------------------------------
    def create(self, *, stage: str, role: str, **kwargs: Any) -> tuple[anthropic.types.Message, LLMUsage, int]:
        """Raw messages.create for the tool-use agent loop (live mode only)."""
        started = time.perf_counter()
        model = self.model_for(role)
        try:
            response = self.client().messages.create(model=model, **kwargs)
        except anthropic.APIStatusError as exc:
            raise LLMError(f"{stage}: API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"{stage}: connection error: {exc}") from exc
        except anthropic.AnthropicError as exc:
            raise LLMError(f"{stage}: {exc}") from exc
        ms = int((time.perf_counter() - started) * 1000)
        usage = _usage(role, response.usage)
        log.info("llm call", extra={"stage": stage, "mode": "live", "model": model, "latency_ms": ms,
                                    "stop_reason": response.stop_reason, **usage.as_dict()})
        if response.stop_reason == "refusal":
            raise LLMError(f"{stage}: model declined the request")
        return response, usage, ms


llm = LLMClient()
