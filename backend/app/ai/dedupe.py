"""Duplicate detection (spec 7.3).

1. Embed title + summary + category + asset type (bge-small).
2. Candidates: open tickets in the same building from the last 72 h, nearest by cosine (pgvector), top 5.
3. score = 0.55 * text_sim + 0.25 * location_score + 0.20 * category_match
4. >= 0.80 auto-merge; 0.60-0.80 ask Claude Haiku 5.5 "same physical issue?"; < 0.60 new ticket.

text_sim is the cosine similarity rescaled to 0-1 between a floor and a ceiling measured for the embedder
(bge-small: unrelated facilities texts ~0.55, same issue in other words ~0.85-0.9). Without rescaling, two
separate leaks in different rooms on the same floor would auto-merge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.embeddings import as_np, cosine, get_embedder
from app.ai.llm import LLMError, LLMUsage, llm, load_prompt
from app.db import is_postgres
from app.models import Location, Ticket, utcnow

W_TEXT, W_LOCATION, W_CATEGORY = 0.55, 0.25, 0.20
AUTO_MERGE, ASK_LLM = 0.80, 0.60
WINDOW_HOURS = 72
TOP_K = 5
OPEN_STATUSES = ("new", "triaged", "assigned", "in_progress")
CONFIRM_PROMPT = "dedupe_confirm_v1"

# (floor, ceiling) of raw cosine per embedder -> mapped to text_sim 0..1
SIM_CALIBRATION = {"hash-384": (0.10, 0.70)}
DEFAULT_CALIBRATION = (0.55, 0.90)


class DuplicateVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    same_issue: bool
    reason: str


@dataclass
class Candidate:
    ticket: Ticket
    cosine: float
    text_sim: float
    location_score: float
    category_match: float
    score: float

    def breakdown(self) -> dict:
        return {
            "ticket": self.ticket.short_code,
            "score": round(self.score, 3),
            "text_sim": round(self.text_sim, 3),
            "cosine": round(self.cosine, 3),
            "location_score": self.location_score,
            "category_match": self.category_match,
            "formula": "0.55*text + 0.25*location + 0.20*category",
        }


@dataclass
class DedupeResult:
    decision: str  # merge | new
    best: Candidate | None
    candidates: list[Candidate] = field(default_factory=list)
    llm_used: bool = False
    llm_mode: str | None = None
    llm_reason: str | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)

    @property
    def rationale(self) -> str:
        if self.best is None:
            return "No open tickets nearby in the last 72 h."
        b = self.best.breakdown()
        base = (f"Best match {b['ticket']} scored {b['score']:.2f} (text {b['text_sim']:.2f}, "
                f"location {b['location_score']}, category {b['category_match']}).")
        if self.llm_used:
            verdict = "same issue" if self.decision == "merge" else "different issue"
            why = ("Strong match but in a different room" if self.best.score >= AUTO_MERGE
                   else "Borderline score")
            return f"{base} {why}, so Claude Haiku was asked: {verdict}. {self.llm_reason or ''}".strip()
        if self.decision == "merge":
            return f"{base} Above the 0.80 auto-merge threshold."
        return f"{base} Below the 0.60 threshold, so a new ticket."

    def payload(self) -> dict:
        return {
            "decision": self.decision,
            "best": self.best.breakdown() if self.best else None,
            "candidates": [c.breakdown() for c in self.candidates],
            "llm_used": self.llm_used,
            "llm_mode": self.llm_mode,
            "llm_reason": self.llm_reason,
            "thresholds": {"auto_merge": AUTO_MERGE, "ask_llm": ASK_LLM},
        }


def calibrated(cos: float) -> float:
    floor, ceiling = SIM_CALIBRATION.get(get_embedder().name, DEFAULT_CALIBRATION)
    return max(0.0, min(1.0, (cos - floor) / (ceiling - floor)))


def location_score(new: Location | None, existing: Ticket) -> float:
    if new is None or existing.location is None:
        return 0.3 if new is not None and existing.building_id == new.building_id else 0.0
    if existing.location_id == new.id:
        return 1.0
    if existing.location.building_id == new.building_id and existing.location.floor == new.floor:
        return 0.6
    if existing.location.building_id == new.building_id:
        return 0.3
    return 0.0


def score_candidate(ticket: Ticket, *, embedding, location: Location | None, category: str) -> Candidate:
    cos = cosine(embedding, ticket.embedding)
    text = calibrated(cos)
    loc = location_score(location, ticket)
    cat = 1.0 if ticket.category == category else 0.0
    return Candidate(ticket, cos, text, loc, cat, W_TEXT * text + W_LOCATION * loc + W_CATEGORY * cat)


def find_candidates(
    db: Session,
    *,
    building_id: uuid.UUID | None,
    location: Location | None,
    category: str,
    embedding,
    now: datetime | None = None,
    exclude: set[uuid.UUID] | None = None,
) -> list[Candidate]:
    if building_id is None:
        return []
    now = now or utcnow()
    filters = [Ticket.building_id == building_id, Ticket.status.in_(OPEN_STATUSES),
               Ticket.created_at >= now - timedelta(hours=WINDOW_HOURS), Ticket.embedding.is_not(None)]
    if exclude:
        filters.append(Ticket.id.not_in(exclude))
    stmt = select(Ticket).options(selectinload(Ticket.location)).where(*filters)
    if is_postgres(db):
        rows = db.scalars(stmt.order_by(Ticket.embedding.cosine_distance(as_np(embedding))).limit(TOP_K)).all()
    else:  # SQLite (tests): same filters, similarity in numpy
        rows = sorted(db.scalars(stmt).all(), key=lambda t: -cosine(embedding, t.embedding))[:TOP_K]
    scored = [score_candidate(t, embedding=embedding, location=location, category=category) for t in rows]
    return sorted(scored, key=lambda c: -c.score)


def _confirm_with_llm(best: Candidate, *, title: str, summary: str, category: str,
                      location: Location | None) -> tuple[DuplicateVerdict, str, LLMUsage]:
    t = best.ticket
    existing_loc = t.location.label if t.location else (t.location_text or "unknown")
    new_loc = location.label if location else "unknown"
    content = (
        f"EXISTING TICKET {t.short_code} (open, {t.report_count} report(s))\n"
        f"Title: {t.title}\nSummary: {t.summary}\nCategory: {t.category}\nLocation: {existing_loc}\n\n"
        f"NEW REPORT\nTitle: {title}\nSummary: {summary}\nCategory: {category}\nLocation: {new_loc}\n\n"
        "Same physical issue?"
    )

    def mock() -> DuplicateVerdict:
        same_place = location is not None and t.location_id == location.id
        same = same_place and t.category == category
        reason = ("Same room and same kind of problem." if same else
                  "Different room or a different kind of problem.")
        return DuplicateVerdict(same_issue=same, reason=reason)

    result = llm.structured(stage="dedupe_confirm", role="fast", system=load_prompt(CONFIRM_PROMPT),
                            content=content, schema=DuplicateVerdict, mock=mock, max_tokens=300, effort="low")
    return result.value, result.mode, result.usage


def decide_duplicate(candidates: list[Candidate], *, title: str, summary: str, category: str,
                     location: Location | None) -> DedupeResult:
    if not candidates:
        return DedupeResult("new", None, [])
    best = candidates[0]
    # Auto-merge only within the same room; a strong match elsewhere always gets a second opinion,
    # because identical wording ("water dripping from the ceiling") can describe two separate leaks.
    if best.score >= AUTO_MERGE and best.location_score == 1.0:
        return DedupeResult("merge", best, candidates)
    if best.score < ASK_LLM:
        return DedupeResult("new", best, candidates)
    try:
        verdict, mode, usage = _confirm_with_llm(best, title=title, summary=summary, category=category,
                                                 location=location)
    except LLMError as exc:  # can't confirm -> keep them separate (a missed merge is the safe failure)
        return DedupeResult("new", best, candidates, llm_used=True, llm_mode="fallback",
                            llm_reason=f"Duplicate check unavailable ({exc}); kept as a separate ticket.")
    return DedupeResult("merge" if verdict.same_issue else "new", best, candidates, llm_used=True, llm_mode=mode,
                        llm_reason=verdict.reason, usage=usage)
