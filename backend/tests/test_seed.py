from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import SOP, Asset, Building, Location, Team, Ticket, utcnow
from app.seed import generate

pytestmark = pytest.mark.usefixtures("module_seed")

OPEN = ("new", "triaged", "assigned", "in_progress")


def test_seed_counts(seeded, db):
    assert db.scalar(select(func.count()).select_from(Building)) == 3
    assert 55 <= db.scalar(select(func.count()).select_from(Location)) <= 70
    assert 140 <= db.scalar(select(func.count()).select_from(Asset)) <= 200
    assert db.scalar(select(func.count()).select_from(Team)) == 10
    assert db.scalar(select(func.count()).select_from(SOP)) == 12
    assert 380 <= db.scalar(select(func.count()).select_from(Ticket)) <= 450


def test_room_numbers_unique_across_campus():
    rooms = [r["room"] for b in generate.load_campus_json()["buildings"] for r in b["rooms"]]
    assert len(rooms) == len(set(rooms))


def test_every_sop_has_numbered_sections():
    for path in (generate.DATA_DIR / "sops").glob("*.md"):
        meta, body = generate.parse_sop(path.read_text(encoding="utf-8"))
        sections = generate.chunk_sop(body)
        assert {"slug", "title", "trade"} <= meta.keys(), path.name
        assert [n for n, _, _ in sections][:5] == [1, 2, 3, 4, 5], path.name


def test_planted_water_cluster(seeded, db):
    engr = db.scalar(select(Building).where(Building.code == "ENGR"))
    rows = db.scalars(
        select(Ticket).join(Location, Ticket.location_id == Location.id).where(
            Ticket.building_id == engr.id, Ticket.status.in_(OPEN), Location.floor >= 3,
            Ticket.category.in_(["leak_water", "ceiling_tile_damage", "mold_suspected"]),
            Ticket.created_at >= utcnow() - timedelta(hours=37))).all()
    assert len(rows) == 5


def test_planted_repeat_failure_sink(seeded, db):
    sink = db.scalar(select(Asset).where(Asset.tag == generate.REPEAT_SINK_TAG))
    tickets = db.scalars(select(Ticket).where(Ticket.asset_id == sink.id).order_by(Ticket.created_at)).all()
    assert len(tickets) == 3
    assert [t.status for t in tickets[:2]] == ["closed", "closed"]
    assert tickets[-1].status in OPEN and tickets[-1].report_count == 2


def test_planted_hazard_from_today(seeded, db):
    hazards = db.scalars(select(Ticket).where(Ticket.is_hazard.is_(True), Ticket.status.in_(OPEN))).all()
    assert len(hazards) == 1
    h = hazards[0]
    assert h.priority == "P1" and h.hazard_type == "electrical"
    assert h.created_at >= utcnow() - timedelta(hours=24)


def test_seed_is_deterministic(reseed, db):
    first = db.scalars(select(Ticket.title).order_by(Ticket.seq)).all()
    db.close()
    generate.run(db)
    second = db.scalars(select(Ticket.title).order_by(Ticket.seq)).all()
    assert first == second


def test_tickets_have_embeddings_and_routing(seeded, db):
    missing = db.scalar(select(func.count()).select_from(Ticket).where(
        (Ticket.embedding.is_(None)) | (Ticket.team_id.is_(None)) | (Ticket.sla_due_at.is_(None))))
    assert missing == 0
