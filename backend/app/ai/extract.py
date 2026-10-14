"""Photo + text -> TicketDraft (spec 7.1).

Live: Claude Sonnet 5.5 with structured outputs (schema = TicketDraft). Mock: a deterministic keyword
classifier over the same taxonomy (also used as the "keyword baseline" in the eval). If the live call
fails we still return a usable draft (category=other, needs review) so a ticket can always be created.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

from app import taxonomy
from app.ai import location as loc_parse
from app.ai.hazards import rule_hazards
from app.ai.llm import LLMError, LLMUsage, llm, load_prompt
from app.schemas import TicketDraft

PROMPT_VERSION = "extract_v1"
TITLE_MAX = 70

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d[\s().-]?){7,}\d")


def scrub_pii(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def system_prompt() -> str:
    return load_prompt(PROMPT_VERSION).replace("{{TAXONOMY}}", taxonomy.taxonomy_for_prompt())


def build_user_content(image_jpeg: bytes | None, text: str, location_context: str | None) -> list[dict]:
    content: list[dict] = []
    if image_jpeg:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.standard_b64encode(image_jpeg).decode("ascii")},
        })
    lines = [
        "Photo: attached above." if image_jpeg else "Photo: none attached.",
        f'Reporter: "{text}"' if text else 'Reporter: ""',
    ]
    if location_context:
        lines.append(f"Known location (from the QR code they scanned): {location_context}")
    lines.append("Return the work-order draft JSON.")
    content.append({"type": "text", "text": "\n".join(lines)})
    return content


# --------------------------------------------------------------------------------------------------
# Mock / keyword baseline
# --------------------------------------------------------------------------------------------------
def _kw_regex(keyword: str) -> re.Pattern:
    return re.compile(r"\b" + r"\s+".join(re.escape(p) for p in keyword.split()) + r"\b", re.IGNORECASE)


_KEYWORDS = [(c.key, [(kw, _kw_regex(kw), len(kw.split())) for kw in c.keywords]) for c in taxonomy.CATEGORIES]


def keyword_scores(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for key, kws in _KEYWORDS:
        score = sum(weight for _, rx, weight in kws if rx.search(text))
        if score:
            scores[key] = score
    return scores


def keyword_category(text: str) -> tuple[str, int]:
    scores = keyword_scores(text)
    if not scores:
        return "other", 0
    order = {k: i for i, k in enumerate(taxonomy.CATEGORY_KEYS)}
    best = max(scores.items(), key=lambda kv: (kv[1], -order[kv[0]]))
    return best


def _title_from_text(text: str, fallback: str) -> str:
    t = re.sub(r"\s+", " ", text).strip().rstrip(".!?")
    if not t:
        return fallback
    t = t[0].upper() + t[1:]
    if len(t) > TITLE_MAX:
        t = t[:TITLE_MAX].rsplit(" ", 1)[0]
    return t


def _severity_short(level: int) -> str:
    return taxonomy.SEVERITY_DEFINITIONS[level].split("(")[0].strip()


def mock_extract(text: str, has_image: bool) -> TicketDraft:
    """Deterministic draft from keywords (mock mode + eval baseline)."""
    clean = scrub_pii(text.strip())
    category, score = keyword_category(clean)
    hits = rule_hazards(clean)
    if hits:
        rule_cat = taxonomy.HAZARD_DEFAULT_CATEGORY[hits[0].hazard_type]
        if taxonomy.CATEGORY_BY_KEY[category].hazard_type is None and score < 2:
            category = rule_cat
    cat = taxonomy.CATEGORY_BY_KEY[category]
    is_hazard = bool(hits) or cat.hazard_type is not None
    hazard_type = hits[0].hazard_type if hits else cat.hazard_type
    severity = 4 if is_hazard else cat.default_severity

    if not clean and has_image:
        return TicketDraft(
            title="Photo report (no description)", summary="Photo received without a description.",
            category="other", trade="General", severity=2, severity_reason="Not enough information yet.",
            is_hazard=False, hazard_type=None, asset_type=None, location_text_from_image=None,
            location_text_from_user=None, visible_evidence=[], needs_clarification=True,
            clarifying_question="What's the problem you'd like to report?", confidence=0.3, image_relevant=True)

    confidence = {0: 0.3, 1: 0.62}.get(score, 0.78 if score == 2 else 0.86)
    summary = f'Reporter says: "{clean}".' if clean else "No description provided."
    if has_image:
        summary += " Photo attached."
    return TicketDraft(
        title=_title_from_text(clean, f"{cat.label} reported"),
        summary=summary,
        category=category,
        trade=cat.trade,
        severity=severity,
        severity_reason=("Hazard keywords detected." if is_hazard else
                         f"Default severity for {cat.label.lower()}: {_severity_short(severity)}"),
        is_hazard=is_hazard,
        hazard_type=hazard_type if is_hazard else None,
        asset_type=taxonomy.canonical_asset_type(clean),
        location_text_from_image=None,
        location_text_from_user=loc_parse.location_phrase(clean),
        visible_evidence=[],
        needs_clarification=score == 0,
        clarifying_question="Can you describe what is broken?" if score == 0 else None,
        confidence=confidence,
        image_relevant=True,
    )


def fallback_draft(text: str) -> TicketDraft:
    """Used when the live model call fails: still lets us create a ticket, flagged for human review."""
    clean = scrub_pii(text.strip())
    return TicketDraft(
        title=_title_from_text(clean, "Facilities report (needs review)"),
        summary=(f'Reporter says: "{clean}". Automatic classification was unavailable; please review.'
                 if clean else "Automatic classification was unavailable; please review the photo."),
        category="other", trade="General", severity=2, severity_reason="Classification unavailable.",
        is_hazard=False, hazard_type=None, asset_type=None, location_text_from_image=None,
        location_text_from_user=loc_parse.location_phrase(clean), visible_evidence=[],
        needs_clarification=False, clarifying_question=None, confidence=0.0, image_relevant=True)


def normalize(draft: TicketDraft) -> TicketDraft:
    data = draft.model_dump()
    data["trade"] = taxonomy.trade_for_category(data["category"])
    title = re.sub(r"\s+", " ", data["title"]).strip()
    data["title"] = title if len(title) <= TITLE_MAX else title[:TITLE_MAX].rsplit(" ", 1)[0]
    data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    if not data["is_hazard"]:
        data["hazard_type"] = None
    elif data["hazard_type"] is None:
        data["hazard_type"] = taxonomy.CATEGORY_BY_KEY[data["category"]].hazard_type
    data["visible_evidence"] = [e for e in data["visible_evidence"] if e][:5]
    return TicketDraft(**data)


# --------------------------------------------------------------------------------------------------
@dataclass
class Extraction:
    draft: TicketDraft
    mode: str  # live | mock | fallback
    latency_ms: int
    usage: LLMUsage = field(default_factory=LLMUsage)
    error: str | None = None
    prompt_version: str = PROMPT_VERSION


def extract_draft(*, image_jpeg: bytes | None, text: str, location_context: str | None = None) -> Extraction:
    try:
        result = llm.structured(
            stage="extract",
            role="main",
            system=system_prompt(),
            content=build_user_content(image_jpeg, text, location_context),
            schema=TicketDraft,
            mock=lambda: mock_extract(text, has_image=image_jpeg is not None),
            max_tokens=2048,
            effort="low",
        )
    except LLMError as exc:
        return Extraction(draft=fallback_draft(text), mode="fallback", latency_ms=0, error=str(exc))
    return Extraction(draft=normalize(result.value), mode=result.mode, latency_ms=result.latency_ms,
                      usage=result.usage)
