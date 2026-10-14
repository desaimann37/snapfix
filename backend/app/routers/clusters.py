"""Root-cause clusters: list, run now, confirm (-> parent inspection ticket), dismiss."""

from __future__ import annotations

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.cluster import run_clustering
from app.ai.embeddings import embed_one, ticket_embedding_text
from app.ai.routing import route_ticket
from app.db import get_db
from app.events import broker
from app.models import Cluster, Ticket, utcnow
from app.routers.tickets import ticket_query
from app.serializers import ticket_out
from app.services import add_event, next_ticket_seq, short_code_for

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


def cluster_out(db: Session, c: Cluster) -> dict:
    ids = [uuid.UUID(i) for i in c.ticket_ids]
    members = db.scalars(ticket_query().where(Ticket.id.in_(ids)).order_by(Ticket.created_at)).all() if ids else []
    parent = db.scalar(ticket_query().where(Ticket.id == c.parent_ticket_id)) if c.parent_ticket_id else None
    return {
        "id": str(c.id),
        "name": c.name,
        "hypothesis": c.hypothesis,
        "recommended_action": c.recommended_action,
        "confidence": c.confidence,
        "status": c.status,
        "building": {"code": c.building.code, "name": c.building.name} if c.building else None,
        "llm_mode": c.llm_mode,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
        "tickets": [ticket_out(t).model_dump(mode="json") for t in members],
        "parent_ticket": ticket_out(parent).model_dump(mode="json") if parent else None,
    }


def _load(db: Session, cluster_id: uuid.UUID) -> Cluster:
    c = db.scalar(select(Cluster).options(selectinload(Cluster.building)).where(Cluster.id == cluster_id))
    if c is None:
        raise HTTPException(404, "Cluster not found")
    return c


@router.get("")
def list_clusters(status: str = Query("open", pattern="^(open|confirmed|dismissed|all)$"),
                  db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Cluster).options(selectinload(Cluster.building)).order_by(Cluster.created_at.desc())
    if status != "all":
        stmt = stmt.where(Cluster.status == status)
    return [cluster_out(db, c) for c in db.scalars(stmt)]


@router.post("/run")
def run_now(db: Session = Depends(get_db)) -> list[dict]:
    clusters = run_clustering(db)
    return [cluster_out(db, _load(db, c.id)) for c in clusters]


@router.post("/{cluster_id}/confirm")
def confirm_cluster(cluster_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    cluster = _load(db, cluster_id)
    if cluster.status != "open":
        raise HTTPException(409, f"Cluster is already {cluster.status}")
    ids = [uuid.UUID(i) for i in cluster.ticket_ids]
    members = list(db.scalars(select(Ticket).options(selectinload(Ticket.location)).where(Ticket.id.in_(ids))))
    if not members:
        raise HTTPException(409, "Cluster has no tickets left")

    category = Counter(t.category for t in members).most_common(1)[0][0]
    severity = max(t.severity for t in members)
    is_hazard = any(t.is_hazard for t in members)
    locations = {t.location_id for t in members}
    location = members[0].location if len(locations) == 1 else None
    floors = sorted({t.location.floor for t in members if t.location})
    rooms = ", ".join(sorted({t.location.room for t in members if t.location}))
    floor_txt = f"floors {floors[0]}–{floors[-1]}" if len(floors) > 1 else (f"floor {floors[0]}" if floors else "")
    where = None if location else f"{cluster.building.name}, {floor_txt} (rooms {rooms})"
    decision = route_ticket(db, category=category, severity=severity, is_hazard=is_hazard,
                            room_type=location.room_type if location else None)
    codes = ", ".join(t.short_code for t in sorted(members, key=lambda t: t.seq))
    title = f"Inspection: {cluster.name}"[:160]
    summary = f"{cluster.hypothesis} Linked tickets: {codes}."
    seq = next_ticket_seq(db)
    parent = Ticket(
        id=uuid.uuid4(), seq=seq, short_code=short_code_for(seq), title=title, summary=summary, category=category,
        trade=decision.trade, severity=severity, priority=decision.priority, is_hazard=is_hazard,
        hazard_type=next((t.hazard_type for t in members if t.is_hazard), None), status="triaged", source="snapfix",
        building_id=cluster.building_id, location_id=location.id if location else None, location_text=where,
        team_id=decision.team_id, sla_due_at=decision.sla_due_at, triaged_at=utcnow(),
        report_count=sum(t.report_count for t in members),
        embedding=embed_one(ticket_embedding_text(title, summary, category, None)),
    )
    db.add(parent)
    db.flush()
    add_event(db, parent, "created", actor="user:manager",
              rationale=(f"Manager confirmed the root-cause cluster '{cluster.name}'. "
                         f"{cluster.recommended_action or ''}").strip(),
              payload={"cluster_id": str(cluster.id), "linked": codes, "confidence": cluster.confidence})
    add_event(db, parent, "assigned", actor="ai", rationale=decision.rationale, payload=decision.as_payload())
    for t in members:
        t.parent_id = parent.id
        add_event(db, t, "linked", actor="user:manager",
                  rationale=f"Linked to parent inspection {parent.short_code} ({cluster.name}).",
                  payload={"parent": parent.short_code})
    cluster.status = "confirmed"
    cluster.parent_ticket_id = parent.id
    db.commit()
    broker.publish("ticket.created", ticket_out(db.scalar(ticket_query().where(Ticket.id == parent.id)))
                   .model_dump(mode="json"))
    broker.publish("cluster.updated", {"id": str(cluster.id), "status": "confirmed"})
    return cluster_out(db, _load(db, cluster.id))


@router.post("/{cluster_id}/dismiss")
def dismiss_cluster(cluster_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    cluster = _load(db, cluster_id)
    if cluster.status != "open":
        raise HTTPException(409, f"Cluster is already {cluster.status}")
    cluster.status = "dismissed"
    db.commit()
    broker.publish("cluster.updated", {"id": str(cluster.id), "status": "dismissed"})
    return cluster_out(db, cluster)

