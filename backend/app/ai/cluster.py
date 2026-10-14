"""Root-cause clustering (spec 7.5).

Per building, over open tickets from the last 14 days: features = text embedding + floor + time.
HDBSCAN (min_cluster_size=3) when there are enough tickets for density estimates to mean something; otherwise,
or if HDBSCAN finds nothing, agglomerative clustering with a distance threshold. Every cluster must pass a
cohesion check. Claude Haiku 5.5 names each cluster and writes a root-cause hypothesis.
"""

from __future__ import annotations

import hashlib
import logging
import warnings
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app import taxonomy
from app.ai.embeddings import as_np, get_embedder
from app.ai.llm import LLMError, llm, load_prompt
from app.models import Building, Cluster, Ticket, utcnow

log = logging.getLogger("snapfix.cluster")

WINDOW_DAYS = 14
MIN_CLUSTER = 3
HDBSCAN_MIN_POINTS = 15
W_FLOOR, W_TIME = 0.6, 0.5
OPEN_STATUSES = ("new", "triaged", "assigned", "in_progress")
PROMPT = "cluster_name_v1"
# Per-embedder distance threshold (agglomerative, average linkage) and minimum mean pairwise cosine.
PARAMS = {"hash-384": {"threshold": 1.25, "cohesion": 0.12}}
DEFAULT_PARAMS = {"threshold": 0.85, "cohesion": 0.60}

THEMES = {
    "water intrusion": ({"leak_water", "ceiling_tile_damage", "flooding", "mold_suspected"},
                        "a roof, window or riser leak", "one combined plumbing + roofing inspection"),
    "electrical": ({"light_out", "power_outlet_dead", "exposed_wiring"},
                   "a shared circuit, panel or lighting-control fault",
                   "one electrician check of the shared circuit/panel"),
    "comfort / HVAC": ({"too_hot", "too_cold", "hvac_noise"},
                       "an air handler or zone controller problem", "one HVAC check of the serving air handler"),
    "drainage": ({"clogged_drain", "toilet_malfunction"},
                 "a blocked branch drain line", "one camera inspection of the shared drain line"),
}


class ClusterNaming(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    hypothesis: str
    recommended_action: str
    confidence: float


def _params() -> dict:
    return PARAMS.get(get_embedder().name, DEFAULT_PARAMS)


def features(tickets: list[Ticket], floors: int, now: datetime) -> np.ndarray:
    emb = np.stack([as_np(t.embedding) for t in tickets])
    floor = np.array([[(t.location.floor if t.location else (floors + 1) / 2) / max(floors, 1)] for t in tickets])
    age = np.array([[(now - t.created_at).total_seconds() / 3600 / (WINDOW_DAYS * 24)] for t in tickets])
    return np.hstack([emb, floor * W_FLOOR, age * W_TIME])


def cluster_labels(x: np.ndarray) -> tuple[np.ndarray, str]:
    from sklearn.cluster import HDBSCAN, AgglomerativeClustering

    if len(x) >= HDBSCAN_MIN_POINTS:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            labels = HDBSCAN(min_cluster_size=MIN_CLUSTER, min_samples=2).fit_predict(x)
        if (labels >= 0).any():
            return labels, "hdbscan"
    labels = AgglomerativeClustering(n_clusters=None, distance_threshold=_params()["threshold"],
                                     linkage="average").fit_predict(x)
    return labels, "agglomerative"


def cohesion(tickets: list[Ticket]) -> float:
    emb = np.stack([as_np(t.embedding) for t in tickets])
    sims = emb @ emb.T
    n = len(tickets)
    return float((sims.sum() - n) / (n * (n - 1))) if n > 1 else 1.0


def signature(ticket_ids) -> str:
    return hashlib.sha1(",".join(sorted(str(i) for i in ticket_ids)).encode()).hexdigest()[:16]


def theme_for(tickets: list[Ticket]) -> tuple[str, str, str]:
    cats = {t.category for t in tickets}
    best = max(THEMES.items(), key=lambda kv: len(cats & kv[1][0]))
    if cats & best[1][0]:
        return best[0], best[1][1], best[1][2]
    top = Counter(t.category for t in tickets).most_common(1)[0][0]
    return taxonomy.CATEGORY_BY_KEY[top].label.lower(), "a common underlying cause", "one combined inspection"


def mock_naming(building: Building, tickets: list[Ticket], now: datetime) -> ClusterNaming:
    theme, cause, action = theme_for(tickets)
    floors = sorted({t.location.floor for t in tickets if t.location})
    if not floors:
        floor_txt = "the building"
    else:
        floor_txt = f"floor {floors[0]}" if len(floors) == 1 else f"floors {floors[0]}–{floors[-1]}"
    span_h = max(1, round((now - min(t.created_at for t in tickets)).total_seconds() / 3600))
    counts = Counter(taxonomy.CATEGORY_BY_KEY[t.category].label.lower() for t in tickets)
    parts = ", ".join(f"{n} {label}" for label, n in counts.most_common())
    rooms = ", ".join(sorted({t.location.room for t in tickets if t.location}))
    n = len(tickets)
    return ClusterNaming(
        name=f"{building.name} {floor_txt} {theme}"[:60],
        hypothesis=(f"{n} open reports ({parts}) on {floor_txt} (rooms {rooms}) within {span_h} h point to a single "
                    f"cause, most likely {cause}. Recommend {action} instead of {n} separate visits."),
        recommended_action=f"Schedule {action} and link the {n} tickets to it.",
        confidence=0.75 if theme == "water intrusion" else 0.55,
    )


def name_cluster(building: Building, tickets: list[Ticket], now: datetime) -> tuple[ClusterNaming, str]:
    lines = []
    for t in sorted(tickets, key=lambda t: t.created_at):
        where = f"floor {t.location.floor}, {t.location.label} ({t.location.room})" if t.location else "unknown room"
        hours = round((now - t.created_at).total_seconds() / 3600)
        lines.append(f"- {t.short_code} | {t.category} | {where} | {hours} h ago | {t.title}: {t.summary}")
    content = f"Building: {building.name} ({building.floors} floors)\nTickets:\n" + "\n".join(lines)
    try:
        result = llm.structured(stage="cluster_name", role="fast", system=load_prompt(PROMPT), content=content,
                                schema=ClusterNaming, mock=lambda: mock_naming(building, tickets, now),
                                max_tokens=600, effort="low")
        naming = result.value
        naming.confidence = max(0.0, min(1.0, naming.confidence))
        return naming, result.mode
    except LLMError as exc:
        log.warning("cluster naming failed (%s); using template", exc)
        return mock_naming(building, tickets, now), "fallback"


def _overlap(a: set, b: set) -> float:
    return len(a & b) / max(1, min(len(a), len(b)))


def run_clustering(db: Session, *, now: datetime | None = None) -> list[Cluster]:
    """Find clusters in every building, upsert them, and return the open clusters."""
    now = now or utcnow()
    changed = False
    for building in db.scalars(select(Building).order_by(Building.code)):
        tickets = list(db.scalars(
            select(Ticket).options(selectinload(Ticket.location)).where(
                Ticket.building_id == building.id, Ticket.status.in_(OPEN_STATUSES), Ticket.parent_id.is_(None),
                Ticket.created_at >= now - timedelta(days=WINDOW_DAYS), Ticket.embedding.is_not(None))
            .order_by(Ticket.created_at)))
        existing = list(db.scalars(select(Cluster).where(Cluster.building_id == building.id)))
        found: list[list[Ticket]] = []
        method = "none"
        if len(tickets) >= MIN_CLUSTER:
            labels, method = cluster_labels(features(tickets, building.floors, now))
            for label in sorted(set(labels) - {-1}):
                members = [t for t, lab in zip(tickets, labels) if lab == label]
                if len(members) >= MIN_CLUSTER and cohesion(members) >= _params()["cohesion"]:
                    found.append(members)

        live_ids: set[str] = set()
        for members in found:
            ids = {str(t.id) for t in members}
            sig = signature(ids)
            handled = [c for c in existing if c.status in ("dismissed", "confirmed")]
            if any(_overlap(ids, set(c.ticket_ids)) >= 0.5 for c in handled):
                continue  # a manager already handled this pattern; don't resurrect it
            match = next((c for c in existing if c.status == "open" and _overlap(ids, set(c.ticket_ids)) >= 0.5), None)
            if match is not None and match.signature == sig:
                live_ids.add(str(match.id))
                continue
            naming, mode = name_cluster(building, members, now)
            if match is None:
                match = Cluster(building_id=building.id, status="open")
                db.add(match)
                existing.append(match)
            match.name, match.hypothesis = naming.name, naming.hypothesis
            match.recommended_action, match.confidence = naming.recommended_action, naming.confidence
            match.ticket_ids, match.signature, match.llm_mode = sorted(ids), sig, mode
            db.flush()
            db.execute(update(Ticket).where(Ticket.cluster_id == match.id).values(cluster_id=None))
            for t in members:
                t.cluster_id = match.id
            live_ids.add(str(match.id))
            changed = True
            log.info("cluster", extra={"building": building.code, "size": len(members), "method": method,
                                       "llm_mode": mode, "cluster_name": naming.name})
        for c in existing:  # open clusters whose pattern disappeared (tickets resolved) are retired
            if c.status == "open" and str(c.id) not in live_ids:
                db.execute(update(Ticket).where(Ticket.cluster_id == c.id).values(cluster_id=None))
                db.delete(c)
                changed = True
        db.flush()
    db.commit()
    if changed:
        from app.events import broker

        broker.publish("cluster.updated", {"at": now.isoformat()})
    return list(db.scalars(select(Cluster).where(Cluster.status == "open").order_by(Cluster.created_at)))
