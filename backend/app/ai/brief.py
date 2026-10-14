"""Technician brief (spec 7.6): RAG over SOP chunks + the asset's ticket history + all reports and photos.

Claude Sonnet 5.5 returns a structured brief whose citations are validated against the SOP sections that were
actually retrieved, so the brief can never cite SOP content we didn't give it. Cached on the ticket.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.ai.embeddings import cosine, embed_one, get_embedder
from app.ai.llm import LLMError, llm, load_prompt
from app.config import get_settings
from app.models import SOP, SOPChunk, Ticket, utcnow
from app.services import add_event

log = logging.getLogger("snapfix.brief")
PROMPT_VERSION = "brief_v1"
TOP_K = 4
TRADE_BOOST, ASSET_BOOST = 0.05, 0.08
# Query<->passage cosine needed for the best SOP to count: (with trade/asset match, without) per embedder.
RELEVANCE = {"hash-384": (0.05, 0.20)}
DEFAULT_RELEVANCE = (0.62, 0.70)


class Cause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cause: str
    reasoning: str
    likelihood: Literal["high", "medium", "low"]


class CitedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    citation: Optional[str]


class TechnicianBriefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    likely_causes: list[Cause]
    tools_parts: list[str]
    safety: list[CitedLine]
    steps: list[CitedLine]
    history_note: Optional[str]
    sop_coverage: Literal["matched", "partial", "none"]


def label(chunk: SOPChunk) -> str:
    return f"SOP: {chunk.sop.title} §{chunk.section_no}"


# --------------------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------------------
def retrieve_sops(db: Session, ticket: Ticket) -> tuple[list[SOPChunk], float, object]:
    """Top-k SOP chunks for this job plus the best SOP's safety, tools and procedure sections.

    Ranking = cosine similarity + a small boost for a matching trade / asset type. (Only ~70 chunks, so this is
    computed in Python on every backend; pgvector would matter at thousands of SOPs.)
    """
    asset_type = ticket.asset.type if ticket.asset else None
    query = f"{ticket.title}. {ticket.summary}. {ticket.category.replace('_', ' ')}. {asset_type or ''}"
    qvec = embed_one(query, query=True)
    chunks = list(db.scalars(select(SOPChunk).join(SOP).options(selectinload(SOPChunk.sop))))
    if not chunks:
        return [], 0.0, None

    def score(c: SOPChunk) -> float:
        boost = TRADE_BOOST if c.sop.trade == ticket.trade else 0.0
        if asset_type and c.sop.asset_type == asset_type:
            boost += ASSET_BOOST
        return cosine(qvec, c.embedding) + boost

    ranked = sorted(chunks, key=score, reverse=True)
    top = ranked[:TOP_K]
    best_sop = top[0].sop_id
    best_sim = max(cosine(qvec, c.embedding) for c in chunks if c.sop_id == best_sop)
    # Always give the model the best SOP's safety (§2), tools (§3) and procedure (§4) sections.
    for c in chunks:
        if c.sop_id == best_sop and c.section_no in (2, 3, 4) and c not in top:
            top.append(c)
    top.sort(key=lambda c: (c.sop.title, c.section_no))
    return top, best_sim, best_sop


def asset_history(db: Session, ticket: Ticket, limit: int = 5) -> list[dict]:
    if ticket.asset_id is None:
        return []
    rows = db.scalars(select(Ticket).options(selectinload(Ticket.events))
                      .where(Ticket.asset_id == ticket.asset_id, Ticket.id != ticket.id)
                      .order_by(Ticket.created_at.desc()).limit(limit)).all()
    out = []
    for t in rows:
        note = next((e.rationale or (e.payload or {}).get("note") for e in reversed(t.events)
                     if e.type == "status_changed" and (e.payload or {}).get("to") == "resolved"), None)
        days = round((utcnow() - t.created_at).total_seconds() / 86400)
        out.append({"short_code": t.short_code, "title": t.title, "status": t.status, "days_ago": max(0, days),
                    "resolution": note})
    return out


def history_facts(history: list[dict]) -> list[str]:
    return [f"{h['short_code']} ({h['days_ago']} days ago, {h['status']}): {h['title']}"
            + (f". Resolution: {h['resolution']}" if h["resolution"] else "") for h in history]


# --------------------------------------------------------------------------------------------------
# Mock (deterministic, built from the real SOP text)
# --------------------------------------------------------------------------------------------------
CAUSES: dict[str, list[tuple[str, str, str]]] = {
    "leak_water": [
        ("Worn faucet cartridge or O-ring", "Dripping from the spout or handle means a worn cartridge.", "high"),
        ("Loose supply or drain connection", "Water under the fixture points to a loose fitting.", "medium"),
        ("High supply pressure", "Pressure above 80 psi shortens cartridge life.", "low"),
    ],
    "clogged_drain": [
        ("Hair or debris in the trap or stopper", "Most slow drains clear at the trap.", "high"),
        ("Blockage further down the branch line", "If the trap is clear, auger the line.", "medium"),
    ],
    "light_out": [
        ("Failed LED driver or ballast", "Fixture out or flickering while the circuit is live.", "high"),
        ("Tripped breaker or lighting control", "Several fixtures out together suggests the circuit.", "medium"),
    ],
    "power_outlet_dead": [
        ("Tripped upstream GFCI", "Many dead outlets are protected by a GFCI elsewhere on the circuit.", "high"),
        ("Failed receptacle", "If the GFCI won't reset, replace the device.", "medium"),
    ],
    "door_wont_close": [
        ("Closer valves out of adjustment", "Slamming or not latching is usually valve adjustment.", "high"),
        ("Misaligned strike or loose hinges", "Check the hardware before adjusting the closer.", "medium"),
    ],
    "too_hot": [
        ("Clogged filter or closed damper", "Little airflow at the diffuser restricts cooling.", "high"),
        ("Thermostat schedule or setpoint", "Check mode and schedule first.", "medium"),
    ],
    "too_cold": [
        ("Thermostat schedule or setpoint", "Check mode, schedule and occupancy override.", "high"),
        ("Heating valve or damper fault", "If airflow is fine but the air is cold, check the valve.", "medium"),
    ],
    "ceiling_tile_damage": [
        ("Active water source above the grid", "Stains return unless the source is fixed.", "high"),
    ],
    "spill": [("Dropped food or beverage", "Clean and dry the area; check whether a leak caused it.", "high")],
}


def _section(chunks: list[SOPChunk], no: int) -> SOPChunk | None:
    return next((c for c in chunks if c.section_no == no), None)


def _bullets(chunk: SOPChunk | None) -> list[str]:
    return [ln[2:].strip() for ln in chunk.text.splitlines() if ln.startswith("- ")] if chunk else []


def _numbered(chunk: SOPChunk | None) -> list[str]:
    if chunk is None:
        return []
    return [re.sub(r"^\d+\.\s*", "", ln).strip() for ln in chunk.text.splitlines() if re.match(r"^\d+\.", ln)]


def mock_brief(ticket: Ticket, chunks: list[SOPChunk], history: list[dict], coverage: str,
               best_sop=None) -> TechnicianBriefOut:
    cat = taxonomy.CATEGORY_BY_KEY.get(ticket.category)
    causes = [Cause(cause=c, reasoning=r, likelihood=lk) for c, r, lk in CAUSES.get(ticket.category, [])]
    if not causes:
        causes = [Cause(cause=f"{cat.label if cat else 'Equipment'} fault", reasoning="Inspect on site to confirm.",
                        likelihood="medium")]
    repeat = [h for h in history if h["days_ago"] <= 60]
    if repeat:
        causes.insert(0, Cause(cause="Repeat failure of the same asset",
                               reasoning=f"{repeat[0]['short_code']} on this asset was {repeat[0]['days_ago']} days "
                                         "ago; fix the root cause, not just the symptom.", likelihood="high"))
    primary = [c for c in chunks if c.sop_id == best_sop] if coverage != "none" else []
    safety_c, tools_c, steps_c = _section(primary, 2), _section(primary, 3), _section(primary, 4)
    safety = [CitedLine(text=b, citation=label(safety_c)) for b in _bullets(safety_c)][:4]
    steps = [CitedLine(text=s, citation=label(steps_c)) for s in _numbered(steps_c)][:10]
    if not steps:
        steps = [CitedLine(text="Inspect the reported equipment and confirm the problem.", citation=None),
                 CitedLine(text="Make the area safe, then repair or escalate to the trade lead.", citation=None)]
    if not safety:
        safety = [CitedLine(text="Keep the area clear while working.", citation=None)]
    note = None
    if history:
        h = history[0]
        note = (f"Same asset had {len(history)} earlier ticket(s); most recent {h['short_code']} "
                f"{h['days_ago']} days ago" + (f" ({h['resolution'].rstrip('.')})" if h["resolution"] else "") + "."
                + (" Possible repeat failure: check supply pressure and the root cause." if repeat else ""))
    where = ticket.location.label if ticket.location else "the reported location"
    sop_name = primary[0].sop.title if primary else None
    summary = f"{cat.label if cat else ticket.category} at {where}" + (
        f"; follow {sop_name}." if sop_name else "; no matching SOP, use general diagnostics.")
    return TechnicianBriefOut(summary=summary, likely_causes=causes[:3], tools_parts=_bullets(tools_c)[:8],
                              safety=safety, steps=steps, history_note=note, sop_coverage=coverage)


# --------------------------------------------------------------------------------------------------
def validate_citations(brief: TechnicianBriefOut, allowed: set[str]) -> tuple[TechnicianBriefOut, int]:
    """Drop any citation that doesn't exactly match a retrieved SOP section (never show invented citations)."""
    removed = 0

    def fix(line: CitedLine) -> CitedLine:
        nonlocal removed
        if line.citation is None:
            return line
        c = line.citation.strip().strip("[]").strip()
        if c in allowed:
            return CitedLine(text=line.text, citation=c)
        removed += 1
        return CitedLine(text=line.text, citation=None)

    return brief.model_copy(update={"safety": [fix(x) for x in brief.safety],
                                    "steps": [fix(x) for x in brief.steps]}), removed


def _photos(ticket: Ticket, limit: int = 3) -> list[dict]:
    out = []
    for r in ticket.reports:
        if r.photo_path and len(out) < limit:
            path = Path(get_settings().upload_dir) / r.photo_path
            if path.exists():
                data = base64.standard_b64encode(path.read_bytes()).decode()
                out.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
    return out


def _context(ticket: Ticket, chunks: list[SOPChunk], facts: list[str]) -> str:
    reports = "\n".join(f"- {r.text or r.transcript or '(photo only)'}" for r in ticket.reports)
    sop_text = "\n\n".join(f"[{label(c)}] {c.section_title}\n{c.text}" for c in chunks) or "(no relevant SOP)"
    where = (f"{ticket.location.building.name}, {ticket.location.label}" if ticket.location
             else (ticket.location_text or "unknown"))
    asset = f"{ticket.asset.name} ({ticket.asset.tag})" if ticket.asset else "unknown"
    hazard = f"HAZARD {ticket.hazard_type}" if ticket.is_hazard else "not a hazard"
    history = "\n".join(f"- {f}" for f in facts) if facts else "- none"
    return (f"TICKET {ticket.short_code}: {ticket.title}\n"
            f"Category: {ticket.category} ({ticket.trade}), severity {ticket.severity}, {hazard}\n"
            f"Location: {where}\nAsset: {asset}\nSummary: {ticket.summary}\n\n"
            f"REPORTS:\n{reports}\n\nASSET HISTORY FACTS:\n{history}\n\nSOP EXCERPTS:\n{sop_text}")


def generate_brief(db: Session, ticket: Ticket, *, refresh: bool = False) -> dict:
    if ticket.brief_json and not refresh:
        return ticket.brief_json
    chunks, best_sim, best_sop = retrieve_sops(db, ticket)
    with_match, without = RELEVANCE.get(get_embedder().name, DEFAULT_RELEVANCE)
    best = next((c.sop for c in chunks if c.sop_id == best_sop), None)
    same_trade = best is not None and (best.trade == ticket.trade
                                       or (ticket.asset is not None and best.asset_type == ticket.asset.type))
    relevant = best_sim >= (with_match if same_trade else without)
    coverage = "matched" if chunks and relevant else "none"
    context_chunks = chunks if coverage != "none" else []
    history = asset_history(db, ticket)
    content = _photos(ticket) + [{"type": "text", "text": _context(ticket, context_chunks, history_facts(history))}]

    started = utcnow()
    usage = None
    try:
        result = llm.structured(stage="brief", role="main", system=load_prompt(PROMPT_VERSION), content=content,
                                schema=TechnicianBriefOut,
                                mock=lambda: mock_brief(ticket, context_chunks, history, coverage, best_sop),
                                max_tokens=3000, effort="low")
        brief, mode, usage = result.value, result.mode, result.usage
    except LLMError as exc:
        log.warning("brief generation failed (%s); using SOP-only template", exc)
        brief, mode = mock_brief(ticket, context_chunks, history, coverage, best_sop), "fallback"
    brief, removed = validate_citations(brief, {label(c) for c in context_chunks})
    if coverage == "none":
        brief = brief.model_copy(update={"sop_coverage": "none"})

    titles = sorted({c.sop.title for c in context_chunks})
    data = {
        **brief.model_dump(),
        "sources": [{"citation": label(c), "title": c.sop.title, "section": c.section_title} for c in context_chunks],
        "history": history,
        "llm_mode": mode,
        "prompt_version": PROMPT_VERSION,
        "invalid_citations_removed": removed,
        "generated_at": started.isoformat(),
        "cost_usd": usage.cost_usd if usage else 0.0,
    }
    ticket.brief_json = data
    ticket.brief_generated_at = started
    add_event(db, ticket, "brief_generated", actor="ai",
              rationale=(f"Technician brief written from {len(titles)} SOP(s) ({', '.join(titles) or 'none matched'}) "
                         f"and {len(history)} asset history item(s). Coverage: {brief.sop_coverage}."
                         + (f" {removed} unverifiable citation(s) removed." if removed else "")),
              payload={"llm_mode": mode, "sources": data["sources"], "coverage": brief.sop_coverage})
    db.commit()
    return data


def is_stale(ticket: Ticket) -> bool:
    """A cached brief is stale if new reports were merged after it was written."""
    if ticket.brief_generated_at is None:
        return True
    last = max((r.created_at for r in ticket.reports), default=None)
    return bool(last and last > ticket.brief_generated_at)
