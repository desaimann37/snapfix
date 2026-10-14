import pytest

from app.ai import location as L


@pytest.mark.parametrize("text,rooms", [
    ("leak in room 312", ["312"]),
    ("Rm. 210 smells like gas", ["210"]),
    ("water stain near 318 and in room 410", ["410", "318"]),
    ("the sink is dripping", []),
])
def test_parse_rooms(text, rooms):
    assert sorted(L.parse_rooms(text)) == sorted(rooms)


@pytest.mark.parametrize("text,floor", [
    ("3rd floor men's room", 3), ("second floor bathroom", 2), ("floor 4 corridor", 4), ("in the 2F lobby", 2),
    ("ground floor entrance", 1), ("the lab", None),
])
def test_parse_floor(text, floor):
    assert L.parse_floor(text) == floor


def test_room_type_and_phrase():
    assert L.parse_room_type("3rd floor men's room") == "restroom"
    assert L.parse_room_type("hallway outside 318") == "corridor"
    assert L.location_phrase("I smell gas near room 210") == "room 210"
    assert L.location_phrase("water on the 3rd floor men's room floor").startswith("3rd floor")


def test_resolve_qr(seeded, db):
    r = L.resolve_location(db, qr_code="ENGR-101", user_text="chair broken")
    assert r.method == "qr" and r.location.room == "101" and r.confidence == 1.0


def test_resolve_explicit_room(seeded, db):
    r = L.resolve_location(db, user_text="I smell gas near room 210")
    assert r.method == "text" and r.location.room == "210" and r.location.building.code == "ENGR"


def test_resolve_named_room(seeded, db):
    r = L.resolve_location(db, user_text="it's freezing in the quiet reading room")
    assert r.location is not None and r.location.room == "220"


def test_resolve_floor_and_type_needs_building(seeded, db):
    ambiguous = L.resolve_location(db, user_text="3rd floor restroom is out of soap")
    assert ambiguous.location is None and len(ambiguous.candidates) == 3
    r = L.resolve_location(db, user_text="2nd floor men's room in the library, sink dripping")
    assert r.location is not None and r.location.room == "225"


def test_resolve_from_photo_sign(seeded, db):
    r = L.resolve_location(db, user_text="door won't close", image_text="312 MATERIALS LAB")
    assert r.method == "image" and r.location.room == "312"


def test_resolve_gps_is_building_level_only(seeded, db):
    r = L.resolve_location(db, user_text="light out", gps=(38.83162, -77.30779))  # at the Library
    assert r.location is None and r.method == "gps"
    assert r.candidates and all(c.building.code == "LIB" for c in r.candidates)


def test_resolve_nothing(seeded, db):
    r = L.resolve_location(db, user_text="broken thing")
    assert r.location is None and r.method == "none"
