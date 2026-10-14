"""Deterministic synthetic seed: campus, teams, SOPs, ~400 historical tickets and the planted demo scenarios.

    python -m app.seed.generate            # wipe + reseed (keeps timing_runs measurements)
    python -m app.seed.generate --no-history

Timestamps are relative to "now" so the 72 h dedupe window and 14 day clustering window always contain
the planted scenarios. Random choices use a fixed seed so the content is identical on every run.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app import taxonomy
from app.ai.embeddings import embed_many, ticket_embedding_text
from app.ai.routing import route_ticket
from app.db import SessionLocal
from app.models import (
    SOP,
    Asset,
    Building,
    Cluster,
    Counter,
    Location,
    Report,
    SOPChunk,
    Team,
    Ticket,
    TicketEvent,
    utcnow,
)
from app.seed import templates as T
from app.services import TICKET_SEQ, TICKET_SEQ_START, add_event, short_code_for

log = logging.getLogger("snapfix.seed")

SEED = 42
DATA_DIR = Path(__file__).resolve().parent
OPEN_STATUSES = ("new", "triaged", "assigned", "in_progress")
WATER_CATEGORIES = {"leak_water", "ceiling_tile_damage", "mold_suspected", "flooding"}

# Demo anchors (referenced by docs/DEMO_SCRIPT.md)
DEMO_ROOM_QR = "engr-101"
REPEAT_SINK_TAG = "LIB-225-SINK-1"
HAZARD_LOCATION_QR = "stuc-249"


# --------------------------------------------------------------------------------------------------
# Campus
# --------------------------------------------------------------------------------------------------
@dataclass
class Campus:
    buildings: dict[str, Building] = field(default_factory=dict)
    locations: list[Location] = field(default_factory=list)
    loc_by_qr: dict[str, Location] = field(default_factory=dict)
    assets: list[Asset] = field(default_factory=list)
    asset_by_tag: dict[str, Asset] = field(default_factory=dict)
    teams: dict[str, Team] = field(default_factory=dict)


def load_campus_json() -> dict:
    return json.loads((DATA_DIR / "buildings.json").read_text(encoding="utf-8"))


def qr_for(building_code: str, room: str) -> str:
    room_l = room.lower()
    if room_l.startswith(building_code.lower()):
        return room_l
    return f"{building_code.lower()}-{room_l}"


def layout_floor(rooms: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    """Place rooms on a 1000x400 floor-plan: two rows of rooms with a corridor band between them."""
    out: dict[str, tuple[float, float, float, float]] = {}
    corridors = [r for r in rooms if r["type"] == "corridor"]
    others = [r for r in rooms if r["type"] != "corridor"]
    top = others[: math.ceil(len(others) / 2)]
    bottom = others[math.ceil(len(others) / 2):]
    for row, y in ((top, 30.0), (bottom, 225.0)):
        if not row:
            continue
        width = 940.0 / len(row)
        for i, r in enumerate(row):
            out[r["room"]] = (30.0 + i * width + 3, y, width - 6, 145.0)
    for r in corridors:
        out[r["room"]] = (30.0, 182.0, 940.0, 36.0)
    return out


def seed_campus(db: Session, rng: random.Random) -> Campus:
    data = load_campus_json()
    campus = Campus()
    for t in data["teams"]:
        team = Team(name=t["name"], trade=t["trade"], on_call_contact=t["on_call_contact"])
        db.add(team)
        campus.teams[t["trade"]] = team

    makes = data["asset_makes"]
    for b in data["buildings"]:
        building = Building(code=b["code"], name=b["name"], lat=b["lat"], lng=b["lng"], floors=b["floors"])
        db.add(building)
        campus.buildings[b["code"]] = building
        db.flush()
        for floor in range(1, b["floors"] + 1):
            rooms = [r for r in b["rooms"] if r["floor"] == floor]
            positions = layout_floor(rooms)
            for r in rooms:
                x, y, w, h = positions[r["room"]]
                loc = Location(
                    building_id=building.id, floor=floor, room=r["room"], label=r["label"],
                    room_type=r["type"], qr_code=qr_for(b["code"], r["room"]), x=x, y=y, w=w, h=h,
                )
                loc.building = building
                db.add(loc)
                campus.locations.append(loc)
                campus.loc_by_qr[loc.qr_code] = loc
    db.flush()

    extra = {}
    for e in data["extra_assets"]:
        extra.setdefault(e["room"], []).append([e["type"], 1])
    for loc in campus.locations:
        specs = list(data["assets_by_room_type"].get(loc.room_type, [])) + extra.get(loc.room, [])
        for asset_type, count in specs:
            for n in range(1, count + 1):
                make, model = rng.choice(makes.get(asset_type, [["Generic", "Standard"]]))
                abbr = re.sub(r"[^A-Z]", "", asset_type.upper())[:6] or "ASSET"
                room_part = loc.room if loc.room.startswith(loc.building.code) else f"{loc.building.code}-{loc.room}"
                tag = f"{room_part}-{abbr}-{n}"
                name = f"{asset_type[0].upper()}{asset_type[1:]} {n} - {loc.label}"
                asset = Asset(
                    location_id=loc.id, type=asset_type, tag=tag, name=name, make=make, model=model,
                    install_date=date(rng.randint(2008, 2023), rng.randint(1, 12), rng.randint(1, 28)),
                )
                asset.location = loc
                db.add(asset)
                campus.assets.append(asset)
                campus.asset_by_tag[tag] = asset
    db.flush()
    return campus


# --------------------------------------------------------------------------------------------------
# SOPs
# --------------------------------------------------------------------------------------------------
def parse_sop(text: str) -> tuple[dict, str]:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, body.strip()


def chunk_sop(body: str) -> list[tuple[int, str, str]]:
    """Split on '## N. Title' headings -> [(N, Title, section text)]."""
    chunks = []
    for m in re.finditer(r"^##\s+(\d+)\.\s+(.+?)\n(.*?)(?=^##\s+\d+\.|\Z)", body, re.M | re.S):
        chunks.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
    return chunks


def seed_sops(db: Session) -> list[SOP]:
    sops = []
    pending: list[tuple[SOPChunk, str]] = []
    for path in sorted((DATA_DIR / "sops").glob("*.md")):
        meta, body = parse_sop(path.read_text(encoding="utf-8"))
        sop = SOP(slug=meta["slug"], title=meta["title"], trade=meta["trade"],
                  asset_type=meta.get("asset_type") or None, body_md=body)
        db.add(sop)
        db.flush()
        for no, title, text in chunk_sop(body):
            chunk = SOPChunk(sop_id=sop.id, section_no=no, section_title=title, text=text)
            db.add(chunk)
            pending.append((chunk, f"{sop.title}. {title}. {text}"))
        sops.append(sop)
    vectors = embed_many([t for _, t in pending])
    for (chunk, _), vec in zip(pending, vectors):
        chunk.embedding = vec
    db.flush()
    return sops


# --------------------------------------------------------------------------------------------------
# Tickets
# --------------------------------------------------------------------------------------------------
@dataclass
class TicketSpec:
    created_at: datetime
    category: str
    location: Location
    asset: Asset | None
    title: str
    summary: str
    severity: int
    report_texts: list[str]
    report_times: list[datetime]
    status: str
    resolved_at: datetime | None = None
    is_hazard: bool = False
    hazard_type: str | None = None
    rule_hits: list[str] = field(default_factory=list)
    assignee: str | None = None
    resolution_note: str | None = None
    tag: str | None = None  # planted scenario marker


def fill(template: str, loc: Location, asset: Asset | None) -> str:
    return template.format(
        label=loc.label, room=f"room {loc.room}" if loc.room[0].isdigit() else loc.label,
        building=loc.building.name, asset=(asset.name if asset else loc.label),
    )


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = [k for k, w in weights.items() if w > 0]
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def pick_location(rng: random.Random, campus: Campus, category: str) -> tuple[Location, Asset | None]:
    if category in T.CATEGORY_ASSET_TYPES:
        types = T.CATEGORY_ASSET_TYPES[category]
        candidates = [a for a in campus.assets if a.type in types and a.tag != REPEAT_SINK_TAG]
        asset = rng.choice(candidates)
        return asset.location, asset
    room_types = T.CATEGORY_ROOM_TYPES.get(category)
    candidates = [loc for loc in campus.locations if not room_types or loc.room_type in room_types]
    return rng.choice(candidates), None


def working_hours(rng: random.Random, day: datetime) -> datetime:
    hour = rng.choices(range(7, 22), weights=[2, 5, 8, 9, 8, 7, 8, 8, 7, 6, 4, 3, 2, 2, 1], k=1)[0]
    return day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)


def resolution_delay(priority: str, rng: random.Random) -> timedelta:
    hours = {"P1": (0.5, 3), "P2": (2, 30), "P3": (12, 110), "P4": (24, 300)}[priority]
    return timedelta(hours=rng.uniform(*hours))


def historical_specs(rng: random.Random, campus: Campus, now: datetime, n: int) -> list[TicketSpec]:
    specs: list[TicketSpec] = []
    for _ in range(n):
        category = weighted_choice(rng, T.CATEGORY_WEIGHTS)
        loc, asset = pick_location(rng, campus, category)
        days_ago = rng.uniform(0.3, 60)
        created = working_hours(rng, now - timedelta(days=days_ago))
        if created >= now:
            created = now - timedelta(hours=rng.uniform(1, 6))
        title, text, summary = rng.choice(T.TICKET_TEMPLATES[category])
        cat = taxonomy.CATEGORY_BY_KEY[category]
        severity = cat.default_severity
        if cat.hazard_type is None and rng.random() < 0.2:
            severity = max(1, min(3, severity + rng.choice((-1, 1))))
        is_hazard = cat.hazard_type is not None
        n_reports = rng.choices((1, 2, 3, 4), weights=(78, 15, 5, 2), k=1)[0]
        report_times = [created] + sorted(
            created + timedelta(minutes=rng.uniform(10, 600)) for _ in range(n_reports - 1))
        extras = T.EXTRA_REPORT_TEXTS.get(category, ["same issue here", "still broken"])
        report_texts = [fill(text, loc, asset)] + [rng.choice(extras) for _ in range(n_reports - 1)]

        age_days = (now - created).total_seconds() / 86400
        r = rng.random()
        if is_hazard:
            status = "closed" if age_days > 1 else "resolved"
        elif age_days > 7:
            status = "closed" if r < 0.85 else ("resolved" if r < 0.97 else "in_progress")
        elif age_days > 2:
            status = "resolved" if r < 0.55 else ("in_progress" if r < 0.8 else "assigned")
        else:
            status = ("resolved" if r < 0.25 else "in_progress" if r < 0.45 else
                      "assigned" if r < 0.7 else "triaged" if r < 0.92 else "new")
        specs.append(TicketSpec(
            created_at=created, category=category, location=loc, asset=asset,
            title=fill(title, loc, asset), summary=fill(summary, loc, asset), severity=severity,
            report_texts=report_texts, report_times=report_times, status=status, is_hazard=is_hazard,
            hazard_type=cat.hazard_type,
            rule_hits=[],
            resolution_note=rng.choice(T.RESOLUTION_NOTES.get(category, ["Completed."])),
        ))
    return specs


def keep_open_tickets_tidy(specs: list[TicketSpec], campus: Campus, now: datetime, rng: random.Random) -> None:
    """Keep recent open tickets diverse so planted scenarios stand out (one open per category per building,
    no stray water tickets on ENGR floors 3-4, nothing open on the repeat-failure sink)."""
    seen: set[tuple[str, str]] = set()
    repeat_sink = campus.asset_by_tag[REPEAT_SINK_TAG]
    for spec in sorted(specs, key=lambda s: s.created_at, reverse=True):
        if spec.status not in OPEN_STATUSES:
            continue
        b = spec.location.building.code
        key = (b, spec.category)
        stray_water = b == "ENGR" and spec.location.floor >= 3 and spec.category in WATER_CATEGORIES
        on_repeat_sink = spec.asset is not None and spec.asset.id == repeat_sink.id
        priority, _ = taxonomy.compute_priority(
            spec.severity, taxonomy.location_criticality(spec.location.room_type, spec.category), spec.is_hazard)
        past_sla = now - spec.created_at > timedelta(hours=taxonomy.SLA_HOURS[priority])  # would have been fixed
        if key in seen or stray_water or on_repeat_sink or spec.is_hazard or past_sla:
            spec.status = "resolved"
        else:
            seen.add(key)
    for spec in specs:
        if spec.status in ("resolved", "closed") and spec.resolved_at is None:
            priority, _ = taxonomy.compute_priority(
                spec.severity, taxonomy.location_criticality(spec.location.room_type, spec.category), spec.is_hazard)
            spec.resolved_at = min(spec.created_at + resolution_delay(priority, rng), now - timedelta(minutes=5))
            if spec.resolved_at <= spec.created_at:
                spec.resolved_at = spec.created_at + timedelta(minutes=30)
        # merged reports can't arrive after the ticket was resolved
        if spec.resolved_at:
            spec.report_times = [t for t in spec.report_times if t <= spec.resolved_at] or [spec.created_at]
            spec.report_texts = spec.report_texts[: len(spec.report_times)]


def planted_specs(campus: Campus, now: datetime) -> list[TicketSpec]:
    L = campus.loc_by_qr
    specs: list[TicketSpec] = []

    # (a) Water-intrusion cluster forming on Engineering Hall floors 3-4 over the last 36 h.
    cluster = [
        (34, "engr-312", "leak_water", "Water dripping from ceiling above lab bench",
         "water is dripping from the ceiling onto the lab bench in the materials lab",
         "Water is dripping from a ceiling tile onto a lab bench in Materials Lab 312. Bench covered with plastic.", 2),
        (28, "engr-318", "ceiling_tile_damage", "Brown water stain spreading on corridor ceiling",
         "big brown water stain on the ceiling tiles in the 3rd floor east hallway, getting bigger",
         "Brown water stain spreading across several ceiling tiles in the 3F east corridor.", 2),
        (20, "engr-418", "leak_water", "Wet ceiling tiles and drip near east stairwell",
         "ceiling tiles are wet and dripping water near the east stairwell on 4",
         "Ceiling tiles near the east stairwell on 4F are wet and dripping water into the corridor.", 2),
        (9, "engr-410", "leak_water", "Water leaking under window after rain",
         "water coming in under the window in office 410 after the rain last night, carpet wet",
         "Water entered under the window in Faculty Offices 410 after overnight rain; carpet below is wet.", 2),
        (3, "engr-314", "mold_suspected", "Damp carpet and musty smell along exterior wall",
         "carpet is damp along the outside wall and it smells musty in 314",
         "Carpet along the exterior wall of Graduate Offices 314 is damp with a musty odor.", 3),
    ]
    for hours, qr, category, title, text, summary, sev in cluster:
        created = now - timedelta(hours=hours)
        specs.append(TicketSpec(
            created_at=created, category=category, location=L[qr], asset=None, title=title, summary=summary,
            severity=sev, report_texts=[text], report_times=[created],
            status="triaged" if hours < 12 else "assigned", tag="cluster"))

    # (b) Repeat-failure sink: two earlier fixes, now leaking again.
    sink = campus.asset_by_tag[REPEAT_SINK_TAG]
    sloc = sink.location
    for days, title, text, summary, note in [
        (48, "Faucet dripping at Sink 1 - 2F Men's Restroom", "left sink faucet keeps dripping",
         "Faucet at Sink 1 in the 2F Men's Restroom drips continuously when closed.",
         "Tightened packing nut; drip stopped."),
        (21, "Faucet leaking at handle, Sink 1 - 2F Men's Restroom",
         "water leaking out around the handle of the left sink",
         "Faucet at Sink 1 in the 2F Men's Restroom leaks around the handle base when running.",
         "Replaced faucet cartridge (AF-C200). Supply pressure not measured."),
    ]:
        created = working_hours(random.Random(days), now - timedelta(days=days))
        specs.append(TicketSpec(
            created_at=created, category="leak_water", location=sloc, asset=sink, title=title, summary=summary,
            severity=2, report_texts=[text], report_times=[created], status="closed",
            resolved_at=created + timedelta(hours=20), resolution_note=note, assignee="tech:plumbing-1",
            tag="repeat_history"))
    created = now - timedelta(hours=7)
    specs.append(TicketSpec(
        created_at=created, category="leak_water", location=sloc, asset=sink,
        title="Faucet leaking again at Sink 1 - 2F Men's Restroom",
        summary="Faucet at Sink 1 in the 2F Men's Restroom is leaking again; water is pooling on the counter. "
                "Same fixture was repaired 21 days ago.",
        severity=2,
        report_texts=["the left sink faucet in the 2nd floor men's room is leaking again, water all over the counter",
                      "sink still dripping, same one as before"],
        report_times=[created, created + timedelta(hours=2)],
        status="assigned", assignee="tech:plumbing-1", tag="repeat_sink"))

    # (c) One hazard ticket from today.
    created = now - timedelta(hours=2)
    specs.append(TicketSpec(
        created_at=created, category="exposed_wiring", location=L[HAZARD_LOCATION_QR], asset=None,
        title="Sparking wires hanging from ceiling light in 2F corridor",
        summary="Wires are hanging out of a ceiling light fixture in the Student Center 2F corridor and one is "
                "sparking. Area below needs to be kept clear.",
        severity=4, report_texts=["wires hanging from the ceiling light in the 2nd floor hallway and one is sparking"],
        report_times=[created], status="assigned", is_hazard=True, hazard_type="electrical",
        rule_hits=["sparking"], assignee="tech:electrical-1", tag="hazard"))
    return specs


def materialize(db: Session, campus: Campus, specs: list[TicketSpec], rng: random.Random, now: datetime) -> list[Ticket]:
    specs.sort(key=lambda s: s.created_at)
    tickets: list[Ticket] = []
    for i, spec in enumerate(specs):
        seq = TICKET_SEQ_START + i
        decision = route_ticket(db, category=spec.category, severity=spec.severity, is_hazard=spec.is_hazard,
                                room_type=spec.location.room_type, now=spec.created_at, teams=campus.teams)
        techs = T.TECHNICIANS.get(decision.trade, ["tech:general-1"])
        assignee = spec.assignee or (rng.choice(techs) if spec.status not in ("new", "triaged") else None)
        ticket = Ticket(
            id=uuid.uuid4(), seq=seq, short_code=short_code_for(seq), title=spec.title[:160], summary=spec.summary,
            category=spec.category, trade=decision.trade, severity=spec.severity, priority=decision.priority,
            is_hazard=spec.is_hazard, hazard_type=spec.hazard_type, status=spec.status,
            needs_review=spec.status == "new", source="seed",
            building_id=spec.location.building_id, location_id=spec.location.id,
            asset_id=spec.asset.id if spec.asset else None, team_id=decision.team_id, assignee=assignee,
            sla_due_at=decision.sla_due_at, triaged_at=spec.created_at + timedelta(seconds=rng.uniform(3, 9)),
            resolved_at=spec.resolved_at if spec.status in ("resolved", "closed") else None,
            report_count=len(spec.report_texts),
        )
        ticket.created_at = spec.created_at
        ticket.updated_at = spec.resolved_at or spec.report_times[-1]
        db.add(ticket)

        for text, at in zip(spec.report_texts, spec.report_times):
            report = Report(text=text, status="confirmed", ticket_id=ticket.id, location_id=spec.location.id,
                            location_code=spec.location.qr_code, llm_mode="seed",
                            extraction_confidence=round(rng.uniform(0.82, 0.97), 2), prompt_version="seed")
            report.created_at = at
            report.updated_at = at
            db.add(report)

        t0 = spec.created_at
        add_event(db, ticket, "created", actor="ai", created_at=t0,
                  rationale=f"Classified as '{spec.category}' ({decision.trade}), severity {spec.severity}: "
                            f"{taxonomy.SEVERITY_DEFINITIONS[spec.severity].split('(')[0].strip()}",
                  payload={"category": spec.category, "trade": decision.trade, "severity": spec.severity})
        if spec.is_hazard:
            why = (f"Hazard rule matched: {', '.join(repr(h) for h in spec.rule_hits)}" if spec.rule_hits
                   else f"Category '{spec.category}' is an inherent {spec.hazard_type} hazard")
            add_event(db, ticket, "escalated", actor="ai", created_at=t0 + timedelta(seconds=1),
                      rationale=f"{why}. Forced P1 and alerted on-call.",
                      payload={"hazard_type": spec.hazard_type, "rule_hits": spec.rule_hits, "source": "rules"})
        add_event(db, ticket, "assigned", actor="ai", created_at=t0 + timedelta(seconds=2),
                  rationale=decision.rationale, payload=decision.as_payload())
        for k, at in enumerate(spec.report_times[1:], start=2):
            add_event(db, ticket, "merged", actor="ai", created_at=at,
                      rationale=f"Report #{k} matched this open ticket (same room, same category, similar text).",
                      payload={"score": round(rng.uniform(0.82, 0.95), 2), "report_count": k})
        if spec.status in ("in_progress", "resolved", "closed") and assignee:
            start = t0 + (((spec.resolved_at or now) - t0) * 0.3)
            add_event(db, ticket, "status_changed", actor=f"user:{assignee}", created_at=start,
                      payload={"from": "assigned", "to": "in_progress"})
        if spec.status in ("resolved", "closed") and spec.resolved_at:
            add_event(db, ticket, "status_changed", actor=f"user:{assignee or 'tech:general-1'}",
                      created_at=spec.resolved_at, rationale=spec.resolution_note,
                      payload={"from": "in_progress", "to": "resolved", "note": spec.resolution_note})
            if spec.status == "closed":
                add_event(db, ticket, "status_changed", actor="user:work-control",
                          created_at=spec.resolved_at + timedelta(hours=12),
                          payload={"from": "resolved", "to": "closed"})
        tickets.append(ticket)

    db.add(Counter(name=TICKET_SEQ, value=TICKET_SEQ_START + len(specs) - 1))
    db.flush()

    # Embeddings for duplicate detection + clustering
    asset_types = {t.id: (spec.asset.type if spec.asset else None) for t, spec in zip(tickets, specs)}
    texts = [ticket_embedding_text(t.title, t.summary, t.category, asset_types[t.id]) for t in tickets]
    for t, vec in zip(tickets, embed_many(texts)):
        t.embedding = vec
    db.flush()
    return tickets


# --------------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------------
def wipe(db: Session) -> None:
    """Delete demo data (keeps timing_runs, which are real volunteer measurements)."""
    db.execute(delete(TicketEvent))
    db.execute(delete(Report))
    db.execute(update(Ticket).values(cluster_id=None, parent_id=None))
    db.execute(delete(Cluster))
    db.execute(delete(Ticket))
    db.execute(delete(SOPChunk))
    db.execute(delete(SOP))
    db.execute(delete(Asset))
    db.execute(delete(Location))
    db.execute(delete(Team))
    db.execute(delete(Building))
    db.execute(delete(Counter))
    db.flush()


def run(db: Session, *, history: bool = True, n_history: int = 400, cluster: bool = True,
        now: datetime | None = None) -> dict:
    started = time.perf_counter()
    now = now or utcnow()
    rng = random.Random(SEED)
    wipe(db)
    campus = seed_campus(db, rng)
    sops = seed_sops(db)
    tickets: list[Ticket] = []
    if history:
        specs = historical_specs(rng, campus, now, n_history)
        keep_open_tickets_tidy(specs, campus, now, rng)
        specs += planted_specs(campus, now)
        tickets = materialize(db, campus, specs, rng, now)
    db.commit()

    clusters = 0
    if cluster and history:
        try:
            from app.ai.cluster import run_clustering
        except ImportError:  # clustering arrives in Phase 4
            run_clustering = None
        if run_clustering is not None:
            clusters = len(run_clustering(db, now=now))
            db.commit()

    summary = {
        "buildings": len(campus.buildings),
        "locations": len(campus.locations),
        "assets": len(campus.assets),
        "teams": len(campus.teams),
        "sops": len(sops),
        "tickets": len(tickets),
        "open_tickets": sum(1 for t in tickets if t.status in OPEN_STATUSES),
        "clusters": clusters,
        "seconds": round(time.perf_counter() - started, 1),
    }
    log.info("seed complete: %s", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Reseed the SnapFix demo database")
    parser.add_argument("--no-history", action="store_true", help="campus + SOPs only, no tickets")
    parser.add_argument("--no-cluster", action="store_true", help="skip the clustering run")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db = SessionLocal()
    try:
        summary = run(db, history=not args.no_history, cluster=not args.no_cluster)
    finally:
        db.close()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
