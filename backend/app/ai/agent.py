"""Dispatcher chat agent (spec 7.7): a Claude tool-use loop over read-only query tools.

The intake pipeline itself runs as a deterministic sequence (app/pipeline.py) for demo reliability; this agent
answers questions like "what's open in Engineering Hall over P2?" or "draft a status update for SF-1042".
Capped at 6 tool calls and 30 s per request. Mock mode answers with a deterministic intent parser.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.ai.llm import LLMError, LLMUsage, llm, load_prompt
from app.ai.location import BUILDING_ALIASES
from app.config import get_settings
from app.models import Building, Cluster, Location, Ticket
from app.runtime import effective_llm_mode

log = logging.getLogger("snapfix.agent")
MAX_TOOL_CALLS = 6
DEADLINE_S = 30.0
PROMPT = "agent_v1"
OPEN = ("new", "triaged", "assigned", "in_progress")
STATUS_LABEL = {"new": "new", "triaged": "triaged", "assigned": "assigned", "in_progress": "in progress",
                "resolved": "resolved", "closed": "closed"}

TOOLS = [
    {
        "name": "search_tickets",
        "description": "Search work orders. Use for questions about what is open, by building, trade, priority or "
                       "hazard. Returns up to `limit` tickets, most urgent first.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "resolved", "all"]},
                "building": {"type": ["string", "null"], "description": "building code or name, e.g. ENGR"},
                "trade": {"type": ["string", "null"], "enum": [*taxonomy.TRADES, None]},
                "min_priority": {"type": ["string", "null"], "enum": ["P1", "P2", "P3", "P4", None],
                                 "description": "P2 means P1 or P2"},
                "hazard_only": {"type": "boolean"},
                "query": {"type": ["string", "null"], "description": "free-text search in title/summary"},
                "limit": {"type": "integer"},
            },
            "required": ["status", "building", "trade", "min_priority", "hazard_only", "query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_ticket",
        "description": "Full details of one ticket by its code (e.g. SF-1042): reports, status, team, SLA, events.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"],
                         "additionalProperties": False},
    },
    {
        "name": "get_clusters",
        "description": "Open root-cause clusters (groups of related tickets with a hypothesis).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "get_kpis",
        "description": "Current operations KPIs: open tickets by priority, hazards, SLA breaches, duplicates, latency.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


# --------------------------------------------------------------------------------------------------
# Tool implementations (read-only)
# --------------------------------------------------------------------------------------------------
def _building(db: Session, ref: str | None) -> Building | None:
    if not ref:
        return None
    ref_l = ref.strip().lower()
    for b in db.scalars(select(Building)):
        names = [b.code.lower(), b.name.lower(), *BUILDING_ALIASES.get(b.code, [])]
        if any(n == ref_l or n in ref_l or ref_l in n for n in names):
            return b
    return None


def _brief_ticket(t: Ticket) -> dict:
    where = f"{t.location.building.code} {t.location.label}" if t.location else (t.location_text or "unknown")
    return {"code": t.short_code, "title": t.title, "priority": t.priority, "status": t.status,
            "hazard": t.hazard_type if t.is_hazard else None, "location": where,
            "team": t.team.name if t.team else None,
            "reports": t.report_count, "created_at": t.created_at.isoformat()}


def search_tickets(db: Session, status: str = "open", building: str | None = None, trade: str | None = None,
                   min_priority: str | None = None, hazard_only: bool = False, query: str | None = None,
                   limit: int = 10) -> dict:
    stmt = select(Ticket).options(selectinload(Ticket.location).selectinload(Location.building),
                                  selectinload(Ticket.team))
    if status == "open":
        stmt = stmt.where(Ticket.status.in_(OPEN))
    elif status == "resolved":
        stmt = stmt.where(Ticket.status.in_(("resolved", "closed")))
    b = _building(db, building)
    if building and b is None:
        return {"error": f"Unknown building '{building}'", "tickets": []}
    if b:
        stmt = stmt.where(Ticket.building_id == b.id)
    if trade:
        stmt = stmt.where(Ticket.trade == trade)
    if min_priority in taxonomy.PRIORITIES:
        stmt = stmt.where(Ticket.priority.in_(taxonomy.PRIORITIES[: taxonomy.PRIORITIES.index(min_priority) + 1]))
    if hazard_only:
        stmt = stmt.where(Ticket.is_hazard.is_(True))
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(Ticket.title.ilike(like), Ticket.summary.ilike(like)))
    rows = db.scalars(stmt.order_by(Ticket.is_hazard.desc(), Ticket.priority, Ticket.created_at.desc())
                      .limit(max(1, min(int(limit or 10), 25)))).all()
    return {"building": b.name if b else None, "count": len(rows), "tickets": [_brief_ticket(t) for t in rows]}


def get_ticket(db: Session, code: str) -> dict:
    t = db.scalar(select(Ticket).options(selectinload(Ticket.location).selectinload(Location.building),
                                         selectinload(Ticket.team), selectinload(Ticket.reports),
                                         selectinload(Ticket.events)).where(Ticket.short_code == code.strip().upper()))
    if t is None:
        return {"error": f"No ticket {code}"}
    return {**_brief_ticket(t), "summary": t.summary, "category": t.category, "severity": t.severity,
            "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
            "reports_text": [r.text or r.transcript for r in t.reports if r.text or r.transcript][:5],
            "recent_events": [f"{e.type}: {e.rationale or ''}"[:200] for e in t.events[-5:]]}


def get_clusters(db: Session) -> dict:
    rows = db.scalars(select(Cluster).where(Cluster.status == "open")).all()
    out = []
    for c in rows:
        ids = [uuid.UUID(i) for i in c.ticket_ids]
        codes = db.scalars(select(Ticket.short_code).where(Ticket.id.in_(ids))).all() if ids else []
        out.append({"name": c.name, "hypothesis": c.hypothesis, "confidence": c.confidence, "tickets": codes})
    return {"count": len(out), "clusters": out}


def get_kpis(db: Session) -> dict:
    from app.routers.dashboard import compute_kpis

    return compute_kpis(db)


def run_tool(db: Session, name: str, args: dict) -> dict:
    fns = {"search_tickets": search_tickets, "get_ticket": get_ticket, "get_clusters": get_clusters,
           "get_kpis": get_kpis}
    if name not in fns:
        return {"error": f"Unknown tool {name}"}
    try:
        return fns[name](db, **args)
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}


# --------------------------------------------------------------------------------------------------
@dataclass
class AgentReply:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    mode: str = "mock"
    latency_ms: int = 0
    usage: LLMUsage = field(default_factory=LLMUsage)


def _summ(result: dict) -> str:
    if "error" in result:
        return result["error"]
    if "tickets" in result:
        return f"{result.get('count', len(result['tickets']))} ticket(s)"
    if "clusters" in result:
        return f"{result['count']} cluster(s)"
    if "code" in result:
        return result["code"]
    return "ok"


def chat(db: Session, message: str, history: list[dict] | None = None) -> AgentReply:
    started = time.perf_counter()
    if effective_llm_mode() == "mock":
        reply = mock_chat(db, message)
        reply.latency_ms = int((time.perf_counter() - started) * 1000)
        return reply

    messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in (history or [])[-6:]
                            if m.get("role") in ("user", "assistant") and m.get("content")]
    messages.append({"role": "user", "content": message})
    system = [{"type": "text", "text": load_prompt(PROMPT), "cache_control": {"type": "ephemeral"}}]
    calls: list[dict] = []
    usage = LLMUsage()
    deadline = time.monotonic() + DEADLINE_S
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining < 2:
                return AgentReply("I ran out of time looking that up. Try a narrower question.", calls, "live",
                                  int((time.perf_counter() - started) * 1000), usage)
            response, u, _ = llm.create(stage="agent", role="main", max_tokens=2000, system=system, tools=TOOLS,
                                        messages=messages, output_config={"effort": "low"},
                                        timeout=min(get_settings().llm_timeout_s, remaining))
            usage = usage.add(u)
            if response.stop_reason != "tool_use":
                text = "".join(b.text for b in response.content if b.type == "text").strip()
                return AgentReply(text or "I couldn't find an answer.", calls, "live",
                                  int((time.perf_counter() - started) * 1000), usage)
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if len(calls) >= MAX_TOOL_CALLS:
                    result = {"error": "Tool-call budget reached; answer with what you have."}
                else:
                    result = run_tool(db, block.name, dict(block.input))
                    calls.append({"name": block.name, "input": dict(block.input), "summary": _summ(result)})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(result, default=str)[:12000]})
            messages.append({"role": "user", "content": results})
    except LLMError as exc:
        log.warning("agent live call failed (%s); answering in mock mode", exc)
        reply = mock_chat(db, message)
        reply.mode = "fallback"
        reply.latency_ms = int((time.perf_counter() - started) * 1000)
        return reply


# --------------------------------------------------------------------------------------------------
# Mock agent: deterministic intent parsing over the same tools
# --------------------------------------------------------------------------------------------------
def _fmt_tickets(result: dict, heading: str) -> str:
    tickets = result.get("tickets", [])
    if not tickets:
        return f"{heading}: none found."
    lines = [f"{heading}: **{len(tickets)}**"]
    for t in tickets:
        hz = f" · HAZARD ({t['hazard']})" if t["hazard"] else ""
        lines.append(f"- **{t['code']}** {t['title']} · {t['priority']}{hz} · {t['location']} · "
                     f"{STATUS_LABEL.get(t['status'], t['status'])}")
    return "\n".join(lines)


def _email(t: dict) -> str:
    status = STATUS_LABEL.get(t["status"], t["status"])
    safety = ""
    if t.get("hazard"):
        safety = ("\n\nFor your safety, please stay away from the affected area until our team confirms it is safe. "
                  "If you notice smoke, fire or a gas smell, leave the area and call 911.")
    return (f"**Subject:** Update on {t['code']}: {t['title']}\n\n"
            f"Hello,\n\nThank you for reporting this. We have received {t['reports']} report(s) about "
            f"\"{t['title']}\" at {t['location']}. The work order is currently **{status}** and assigned to our "
            f"{t['team'] or 'maintenance team'} (priority {t['priority']}).{safety}\n\n"
            f"We'll post another update when the work is complete.\n\nFacilities Work Control")


def mock_chat(db: Session, message: str) -> AgentReply:
    text = message.lower()
    calls: list[dict] = []

    def call(name: str, **args) -> dict:
        result = run_tool(db, name, args)
        calls.append({"name": name, "input": args, "summary": _summ(result)})
        return result

    code = re.search(r"\bsf-?\s?(\d{3,4})\b", text)
    if code:
        ticket = call("get_ticket", code=f"SF-{int(code.group(1)):04d}")
        if "error" in ticket:
            return AgentReply(ticket["error"] + ".", calls)
        if any(w in text for w in ("email", "update", "draft", "message", "notice")):
            return AgentReply(_email(ticket), calls)
        hz = f" It is a **{ticket['hazard']} hazard**." if ticket["hazard"] else ""
        return AgentReply(f"**{ticket['code']}** {ticket['title']}: {ticket['priority']}, "
                          f"{STATUS_LABEL.get(ticket['status'], ticket['status'])}, {ticket['team']}, "
                          f"{ticket['reports']} report(s), at {ticket['location']}.{hz}\n\n{ticket['summary']}", calls)
    if any(w in text for w in ("cluster", "root cause", "pattern", "related")):
        res = call("get_clusters")
        if not res["clusters"]:
            return AgentReply("No open root-cause clusters right now.", calls)
        lines = [f"**{res['count']} open cluster(s)**"]
        lines += [f"- **{c['name']}** ({len(c['tickets'])} tickets: {', '.join(c['tickets'])}): {c['hypothesis']}"
                  for c in res["clusters"]]
        return AgentReply("\n".join(lines), calls)
    if any(w in text for w in ("kpi", "stats", "how are we", "overview", "summary", "metrics")):
        k = call("get_kpis")
        p = k["open_by_priority"]
        lat = k["photo_to_ticket_ms"]["p50"]
        return AgentReply(
            f"**{k['open_total']} open tickets** (P1 {p['P1']}, P2 {p['P2']}, P3 {p['P3']}, P4 {p['P4']}), "
            f"{k['hazards_open']} open hazard(s), {k['sla_breaches']} past SLA, "
            f"{k['duplicates_prevented_30d']} duplicate reports merged in 30 days"
            + (f", median photo → ticket {lat / 1000:.1f} s." if lat else "."), calls)

    building = next((b for b, names in BUILDING_ALIASES.items() for n in names + [b.lower()]
                     if re.search(rf"\b{re.escape(n)}\b", text)), None)
    pr = re.search(r"\bp\s?([1-4])\b", text)
    trade = next((t for t in taxonomy.TRADES if t.split("/")[0].lower() in text), None)
    hazard = any(w in text for w in ("hazard", "danger", "emergenc", "unsafe"))
    status = "resolved" if any(w in text for w in ("resolved", "closed", "fixed")) else "open"
    if building or pr or trade or hazard or "open" in text or "ticket" in text:
        res = call("search_tickets", status=status, building=building, trade=trade,
                   min_priority=f"P{pr.group(1)}" if pr else None, hazard_only=hazard, query=None, limit=10)
        scope = " ".join(x for x in [
            status, "hazard" if hazard else "", trade or "", "tickets",
            f"in {res.get('building')}" if res.get("building") else "",
            f"at P{pr.group(1)} or higher" if pr else ""] if x)
        return AgentReply(_fmt_tickets(res, scope[0].upper() + scope[1:]), calls)
    return AgentReply("I can look up work orders for you. Try:\n- \"What's open in Engineering Hall over P2?\"\n"
                      "- \"Any hazards right now?\"\n- \"Draft a status update email for SF-1006\"\n"
                      "- \"Show root-cause clusters\"\n- \"How are we doing today?\"", calls)
