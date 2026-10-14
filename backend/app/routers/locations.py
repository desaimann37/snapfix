"""Buildings, locations (QR lookup + search) and floor plans."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Building, Location, Ticket
from app.schemas import BuildingOut, LocationOut
from app.serializers import building_out, location_out

router = APIRouter(prefix="/api", tags=["locations"])

OPEN_STATUSES = ("new", "triaged", "assigned", "in_progress")


@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings(db: Session = Depends(get_db)) -> list[BuildingOut]:
    return [building_out(b) for b in db.scalars(select(Building).order_by(Building.code))]


@router.get("/locations/search", response_model=list[LocationOut])
def search_locations(
    q: str = "", building: str | None = None, limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db),
) -> list[LocationOut]:
    stmt = select(Location).join(Building).options(selectinload(Location.building))
    if building:
        stmt = stmt.where(Building.code == building.upper())
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Location.label.ilike(like), Location.room.ilike(like), Building.name.ilike(like),
                              Building.code.ilike(like), Location.qr_code.ilike(like)))
        stmt = stmt.order_by(case((Location.room == q, 0), else_=1), Building.code, Location.floor, Location.room)
    else:
        stmt = stmt.order_by(Building.code, Location.floor, Location.room)
    return [location_out(loc) for loc in db.scalars(stmt.limit(limit))]


@router.get("/locations/{qr_code}", response_model=LocationOut)
def get_location(qr_code: str, db: Session = Depends(get_db)) -> LocationOut:
    loc = db.scalar(select(Location).options(selectinload(Location.building))
                    .where(Location.qr_code == qr_code.lower()))
    if loc is None:
        raise HTTPException(404, f"Unknown location code '{qr_code}'")
    return location_out(loc)


@router.get("/buildings/{code}/floors/{floor}")
def floor_plan(code: str, floor: int, db: Session = Depends(get_db)) -> dict:
    building = db.scalar(select(Building).where(Building.code == code.upper()))
    if building is None:
        raise HTTPException(404, f"Unknown building '{code}'")
    rooms = db.scalars(select(Location).options(selectinload(Location.building))
                       .where(Location.building_id == building.id, Location.floor == floor)
                       .order_by(Location.room)).all()
    counts = dict(db.execute(
        select(Ticket.location_id, func.count()).where(Ticket.building_id == building.id,
                                                       Ticket.status.in_(OPEN_STATUSES))
        .group_by(Ticket.location_id)).all())
    hazards = set(db.scalars(select(Ticket.location_id).where(
        Ticket.building_id == building.id, Ticket.status.in_(OPEN_STATUSES), Ticket.is_hazard.is_(True))))
    return {
        "building": building_out(building).model_dump(mode="json"),
        "floor": floor,
        "rooms": [
            {**location_out(r).model_dump(mode="json"), "open_count": counts.get(r.id, 0), "hazard": r.id in hazards}
            for r in rooms
        ],
    }
