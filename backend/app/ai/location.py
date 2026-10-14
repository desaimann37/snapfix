"""Location resolution (spec 7.1): QR -> explicit room in text -> sign in photo -> GPS -> ask the user.

Never invents a room: if nothing matches confidently we return candidates for the user to pick.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Building, Location

ROOM_IN_TEXT = [
    re.compile(r"\b(?:room|rm\.?|suite|office|lab|classroom|#)\s*#?\s*([a-z]?\d{3,4}[a-z]?)\b", re.I),
    re.compile(r"\b(?:near|in|at|outside|by|beside|next\s+to|across\s+from|opposite)\s+(?:room\s+)?(\d{3,4})\b", re.I),
]
NUMBER_ON_SIGN = re.compile(r"\b([a-z]?\d{3,4}[a-z]?)\b", re.I)

FLOOR_WORDS = {"ground": 1, "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
               "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}
FLOOR_PATTERNS = [
    re.compile(r"\b(ground|first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s+floor\b", re.I),
    re.compile(r"\bfloor\s+(\d)\b", re.I),
    re.compile(r"\blevel\s+(\d)\b", re.I),
    re.compile(r"\b(\d)\s?f\b", re.I),
    re.compile(r"\bon\s+(\d)\b", re.I),
]
ROOM_TYPE_PATTERNS = [
    (re.compile(r"\b(?:men'?s|mens|women'?s|womens|ladies|gents)\s*(?:room|restroom|bathroom|washroom|toilets?)?\b"
                r"|\b(?:restroom|bathroom|washroom|toilets?|lavatory)\b", re.I), "restroom"),
    (re.compile(r"\b(?:hallway|hall|corridor)\b", re.I), "corridor"),
    (re.compile(r"\b(?:lobby|front\s+desk|info\s+desk)\b", re.I), "lobby"),
    (re.compile(r"\belevators?\b", re.I), "elevator"),
    (re.compile(r"\b(?:kitchen|cafe|food\s+court|cafeteria)\b", re.I), "kitchen"),
    (re.compile(r"\b(?:mechanical\s+room|boiler\s+room|mech\s+room)\b", re.I), "mechanical"),
    (re.compile(r"\b(?:entrance|walkway|sidewalk|plaza|outside|parking)\b", re.I), "exterior"),
]
GENDER = [
    (re.compile(r"\b(?:women'?s|womens|ladies)\b", re.I), "women"),
    (re.compile(r"\b(?:men'?s|mens|gents)\b", re.I), "men"),
]
GENERIC_LABEL_WORDS = {"room", "rooms", "the", "and", "of", "restroom", "restrooms", "men's", "women's", "1f", "2f",
                       "3f", "4f", "floor", "corridor", "offices", "office", "lab", "main", "wing", "east", "west"}
BUILDING_ALIASES = {"ENGR": ["engineering", "engr", "eng hall"], "LIB": ["library", "lib"],
                    "STUC": ["student center", "student centre", "stuc", "student union"]}
GPS_MAX_METERS = 400


@dataclass
class LocationResolution:
    location: Location | None
    method: str  # qr | text | image | gps | none
    confidence: float
    candidates: list[Location] = field(default_factory=list)
    explanation: str = ""

    def payload(self) -> dict:
        return {"method": self.method, "confidence": self.confidence, "explanation": self.explanation,
                "location_id": str(self.location.id) if self.location else None,
                "candidates": [str(c.id) for c in self.candidates]}


def location_phrase(text: str) -> str | None:
    """The location words a reporter used ("room 210", "3rd floor men's room", "near 318")."""
    for rx in ROOM_IN_TEXT:
        m = rx.search(text)
        if m:
            return m.group(0).strip()
    for rx in FLOOR_PATTERNS[:3]:
        m = rx.search(text)
        if m:
            tail = text[m.end(): m.end() + 30]
            rt = next((p.search(tail) for p, _ in ROOM_TYPE_PATTERNS if p.search(tail)), None)
            return (m.group(0) + (tail[: rt.end()] if rt else "")).strip()
    return None


def parse_floor(text: str) -> int | None:
    for rx in FLOOR_PATTERNS:
        m = rx.search(text)
        if m:
            raw = m.group(1).lower()
            return FLOOR_WORDS.get(raw) or (int(raw) if raw.isdigit() else None)
    return None


def parse_room_type(text: str) -> str | None:
    for rx, room_type in ROOM_TYPE_PATTERNS:
        if rx.search(text):
            return room_type
    return None


def parse_rooms(text: str) -> list[str]:
    rooms: list[str] = []
    for rx in ROOM_IN_TEXT:
        rooms += [m.group(1).upper() for m in rx.finditer(text)]
    return list(dict.fromkeys(rooms))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _building_from_text(text: str, buildings: list[Building]) -> Building | None:
    low = text.lower()
    for b in buildings:
        names = BUILDING_ALIASES.get(b.code, []) + [b.name.lower()]
        if any(re.search(r"\b" + re.escape(n) + r"\b", low) for n in names):
            return b
    return None


def _nearest_building(gps: tuple[float, float], buildings: list[Building]) -> tuple[Building | None, float]:
    best, dist = None, float("inf")
    for b in buildings:
        d = haversine_m(gps[0], gps[1], b.lat, b.lng)
        if d < dist:
            best, dist = b, d
    return (best, dist) if dist <= GPS_MAX_METERS else (None, dist)


def _label_matches(text: str, locations: list[Location]) -> list[Location]:
    low = text.lower()
    out = []
    for loc in locations:
        words = [w for w in re.findall(r"[a-z0-9']+", loc.label.lower()) if w not in GENERIC_LABEL_WORDS]
        if words and all(re.search(r"\b" + re.escape(w) + r"\b", low) for w in words):
            out.append(loc)
    return out


def _by_floor_and_type(
    locations: list[Location], floor: int | None, room_type: str | None, text: str
) -> list[Location]:
    rows = [loc for loc in locations if (floor is None or loc.floor == floor) and
            (room_type is None or loc.room_type == room_type)]
    if room_type == "restroom":
        gender = next((g for rx, g in GENDER if rx.search(text)), None)
        if gender:  # word boundary: "men's" is a substring of "women's"
            gendered = [loc for loc in rows if re.search(rf"\b{gender}'s\b", loc.label.lower())]
            rows = gendered or [loc for loc in rows if not re.search(r"\b(?:wo)?men's\b", loc.label.lower())]
    return rows


def resolve_location(
    db: Session,
    *,
    qr_code: str | None = None,
    user_text: str = "",
    image_text: str | None = None,
    gps: tuple[float, float] | None = None,
) -> LocationResolution:
    locations = list(db.scalars(select(Location).options(selectinload(Location.building))))
    buildings = list(db.scalars(select(Building)))

    # 1) QR code from /r/{qr_code}
    if qr_code:
        loc = next((x for x in locations if x.qr_code == qr_code.lower()), None)
        if loc:
            return LocationResolution(loc, "qr", 1.0, [], f"Scanned QR code for {loc.label}.")

    building = _building_from_text(user_text, buildings)
    if building is None and gps:
        building, _ = _nearest_building(gps, buildings)
    scoped = [x for x in locations if building is None or x.building_id == building.id]

    def by_room(numbers: list[str]) -> list[Location]:
        return [x for x in scoped if x.room.upper() in numbers]

    # 2) explicit room / place in the reporter's words
    rooms = parse_rooms(user_text)
    if rooms:
        hits = by_room(rooms)
        if len(hits) == 1:
            return LocationResolution(hits[0], "text", 0.92, [], f"Reporter mentioned room {hits[0].room}.")
        if hits:
            return LocationResolution(None, "text", 0.4, hits[:6], f"Room {rooms[0]} exists in several buildings.")
    named = _label_matches(user_text, scoped)
    if len(named) == 1:
        return LocationResolution(named[0], "text", 0.85, [], f"Reporter named '{named[0].label}'.")
    floor, room_type = parse_floor(user_text), parse_room_type(user_text)
    if floor is not None or room_type is not None:
        hits = _by_floor_and_type(scoped, floor, room_type, user_text)
        if len(hits) == 1 and building is not None:
            phrase = location_phrase(user_text) or user_text
            return LocationResolution(hits[0], "text", 0.75, [], f"Matched '{phrase}'.")
        if hits and len(hits) <= 6:
            return LocationResolution(None, "text", 0.35, hits, "Several rooms match the description; please pick one.")

    # 3) room-number sign visible in the photo
    if image_text:
        numbers = [m.group(1).upper() for m in NUMBER_ON_SIGN.finditer(image_text)]
        hits = by_room(numbers)
        if len(hits) == 1:
            return LocationResolution(hits[0], "image", 0.85, [], f"Read room sign '{image_text}' in the photo.")
        named = _label_matches(image_text, scoped)
        if len(named) == 1:
            return LocationResolution(named[0], "image", 0.8, [], f"Read sign '{image_text}' in the photo.")

    # 4) GPS -> nearest building (building-level only; never guess the room)
    if building is not None:
        cands = sorted(scoped, key=lambda x: (x.floor, x.room))[:8]
        how = "Photo GPS" if gps else "Reporter text"
        return LocationResolution(None, "gps" if gps else "text", 0.3, cands,
                                  f"{how} places this in {building.name}; please pick the room.")

    # 5) ask the user
    return LocationResolution(None, "none", 0.0, [], "No location found; please pick one.")
