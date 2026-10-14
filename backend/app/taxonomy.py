"""Fixed taxonomy: trades, categories, severities, priorities/SLAs, hazard keyword rules.

This module is the backbone of accuracy and safety. Everything here is deterministic and unit-tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------------------
# Trades
# --------------------------------------------------------------------------------------------------
TRADES: list[str] = [
    "Plumbing",
    "Electrical",
    "HVAC",
    "Carpentry/Doors & Locks",
    "Custodial",
    "Grounds",
    "Elevator",
    "IT/AV",
    "Safety/Environmental",
    "General",
]


# --------------------------------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Category:
    key: str
    label: str
    trade: str
    description: str
    default_severity: int
    keywords: tuple[str, ...] = field(default_factory=tuple)  # used by mock mode + keyword baseline
    hazard_type: str | None = None  # category that is inherently a hazard


CATEGORIES: list[Category] = [
    Category("leak_water", "Water leak / drip", "Plumbing",
             "Water dripping or leaking from a pipe, faucet, fixture, or ceiling (not large-scale flooding).", 2,
             ("leak", "leaking", "drip", "dripping", "drips", "water stain", "wet ceiling", "water damage")),
    Category("clogged_drain", "Clogged / slow drain", "Plumbing",
             "Sink, shower or floor drain that is slow, blocked or backing up.", 2,
             ("clog", "clogged", "drain", "slow drain", "backed up", "won't drain", "not draining")),
    Category("toilet_malfunction", "Toilet / urinal problem", "Plumbing",
             "Toilet or urinal that runs, won't flush, is clogged or overflowing.", 2,
             ("toilet", "urinal", "flush", "flushing", "overflowing toilet", "running toilet")),
    Category("fountain_broken", "Drinking fountain / bottle filler", "Plumbing",
             "Drinking fountain or bottle-filling station not working, low pressure or leaking.", 1,
             ("fountain", "bottle filler", "water fountain", "drinking fountain", "bottle station")),
    Category("flooding", "Flooding / major water", "Plumbing",
             "Significant water on the floor, burst pipe, water pouring or spreading.", 4,
             ("flood", "flooding", "flooded", "burst pipe", "pouring", "gushing", "water everywhere"),
             hazard_type="water_intrusion"),
    Category("light_out", "Light out / flickering", "Electrical",
             "Light fixture, lamp or bulb that is out, flickering or buzzing.", 1,
             ("light", "lights", "bulb", "lamp", "flicker", "flickering", "dark", "fixture out", "light out")),
    Category("exposed_wiring", "Exposed / damaged wiring", "Electrical",
             "Exposed, damaged or hanging wires, open junction box, sparking equipment.", 4,
             ("wire", "wires", "wiring", "junction box", "sparking", "spark", "exposed"),
             hazard_type="electrical"),
    Category("power_outlet_dead", "Outlet / power out", "Electrical",
             "Outlet, circuit or equipment with no power; tripped breaker or GFCI.", 2,
             ("outlet", "socket", "plug", "no power", "power out", "breaker", "gfci", "charging station")),
    Category("too_hot", "Too hot", "HVAC",
             "Room is too warm or AC is not working.", 2,
             ("too hot", "hot", "warm", "stuffy", "ac not working", "air conditioning", "no ac", "sweltering")),
    Category("too_cold", "Too cold", "HVAC",
             "Room is too cold or heat is not working.", 2,
             ("too cold", "cold", "freezing", "chilly", "no heat", "heat not working", "heater")),
    Category("hvac_noise", "HVAC noise / airflow", "HVAC",
             "Rattling, banging or whistling vents/units; no airflow from vents.", 1,
             ("vent", "rattling", "rattle", "banging", "hvac noise", "airflow", "whistling", "air handler")),
    Category("door_wont_close", "Door won't close / latch", "Carpentry/Doors & Locks",
             "Door that will not close, latch or stay open; broken door closer or hinge.", 2,
             ("door", "won't close", "doesn't close", "closer", "hinge", "latch", "slams", "door stuck")),
    Category("lock_broken", "Lock / card reader broken", "Carpentry/Doors & Locks",
             "Broken lock, key not working, card reader or access control failure.", 3,
             ("lock", "locked", "key", "card reader", "badge", "keypad", "can't unlock", "won't lock")),
    Category("broken_furniture", "Broken furniture", "Carpentry/Doors & Locks",
             "Broken or unsafe chair, desk, table, shelf or other furniture.", 1,
             ("chair", "desk", "table", "shelf", "bench", "furniture", "cabinet", "wobbly")),
    Category("broken_window", "Broken window / glass", "Carpentry/Doors & Locks",
             "Cracked or broken window, glass door or glass panel; window won't close.", 3,
             ("window", "glass", "cracked glass", "broken glass", "shattered", "pane")),
    Category("spill", "Spill", "Custodial",
             "Liquid or food spilled on a floor or surface (non-chemical).", 2,
             ("spill", "spilled", "spilt", "coffee", "soda", "sticky floor", "puddle", "wet floor")),
    Category("trash_overflow", "Trash / recycling overflow", "Custodial",
             "Trash or recycling bins full or overflowing; litter.", 1,
             ("trash", "garbage", "recycling", "bin", "overflowing bin", "litter", "rubbish")),
    Category("supplies_empty", "Restroom supplies empty", "Custodial",
             "Out of soap, paper towels, toilet paper or other consumables.", 1,
             ("soap", "paper towel", "paper towels", "toilet paper", "dispenser", "hand sanitizer", "empty")),
    Category("pest", "Pests", "Custodial",
             "Insects, rodents or other pests sighted.", 2,
             ("mouse", "mice", "rat", "rats", "roach", "cockroach", "ants", "bugs", "pest", "bees", "wasp")),
    Category("graffiti", "Graffiti / vandalism", "Custodial",
             "Graffiti, stickers, vandalism or defaced surfaces.", 1,
             ("graffiti", "vandalism", "vandalized", "tagged", "spray paint", "sticker")),
    Category("biohazard", "Biohazard cleanup", "Safety/Environmental",
             "Blood, vomit, needles/sharps, sewage or other bodily fluids.", 4,
             ("blood", "vomit", "needle", "syringe", "sharps", "feces", "sewage", "bodily fluid"),
             hazard_type="biohazard"),
    Category("ceiling_tile_damage", "Ceiling tile damage", "General",
             "Stained, missing, broken, wet or displaced ceiling tiles.", 2,
             ("ceiling tile", "tile", "ceiling stain", "stained ceiling", "missing tile", "ceiling")),
    Category("trip_hazard", "Trip hazard", "General",
             "Uneven flooring, loose carpet/tiles, cords across walkway, broken step.", 3,
             ("trip", "tripping", "uneven", "loose carpet", "loose tile", "pothole", "cord across", "broken step")),
    Category("elevator_out", "Elevator problem", "Elevator",
             "Elevator out of service, stuck, doors malfunctioning, or entrapment.", 3,
             ("elevator", "lift", "stuck between floors", "elevator stuck", "elevator out")),
    Category("projector_broken", "Projector / AV problem", "IT/AV",
             "Projector, display, speakers, microphone or classroom AV not working.", 2,
             ("projector", "screen", "display", "hdmi", "speaker", "microphone", "av", "tv", "monitor")),
    Category("wifi_dead_zone", "Wi-Fi / network", "IT/AV",
             "No or weak Wi-Fi, network jack dead.", 1,
             ("wifi", "wi-fi", "internet", "network", "no signal", "ethernet", "connection")),
    Category("mold_suspected", "Suspected mold / musty", "Safety/Environmental",
             "Visible mold growth, musty odor, persistent dampness.", 3,
             ("mold", "mould", "mildew", "musty", "damp smell", "fungus")),
    Category("gas_smell", "Gas odor", "Safety/Environmental",
             "Smell of natural gas / rotten eggs; suspected gas leak.", 4,
             ("gas", "rotten egg", "propane"), hazard_type="gas"),
    Category("smoke_odor", "Smoke / burning odor", "Safety/Environmental",
             "Smoke, burning smell, smoldering, or fire.", 4,
             ("smoke", "burning", "fire", "smoldering", "flames"), hazard_type="fire_smoke"),
    Category("chemical_spill", "Chemical spill / fumes", "Safety/Environmental",
             "Spilled chemicals, chemical odor or fumes, lab spill.", 4,
             ("chemical", "acid", "fumes", "solvent", "ammonia", "bleach", "toxic", "mercury"),
             hazard_type="chemical"),
    Category("snow_ice", "Snow / ice", "Grounds",
             "Snow or ice on walkways, steps, entrances or parking areas.", 3,
             ("snow", "ice", "icy", "sleet", "frozen")),
    Category("tree_hazard", "Tree / landscaping hazard", "Grounds",
             "Fallen or hanging tree limbs, dead trees, overgrown landscaping blocking paths.", 3,
             ("tree", "branch", "limb", "fallen tree", "bushes", "landscaping", "overgrown")),
    Category("other", "Other", "General",
             "Anything that does not clearly fit another category.", 2, ()),
]

CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
CATEGORY_KEYS: list[str] = [c.key for c in CATEGORIES]


def trade_for_category(category: str) -> str:
    return CATEGORY_BY_KEY.get(category, CATEGORY_BY_KEY["other"]).trade


# --------------------------------------------------------------------------------------------------
# Severity
# --------------------------------------------------------------------------------------------------
SEVERITY_DEFINITIONS: dict[int, str] = {
    4: "Immediate danger to people or property (gas smell, sparking/exposed live wiring, flooding, "
       "fire/smoke, structural failure, elevator entrapment, chemical/biohazard exposure).",
    3: "Blocks use of a space or a critical function (overflowing toilet, exterior door won't lock, "
       "no heat in winter, elevator out of service, broken window, trip hazard in a walkway).",
    2: "Degraded but still usable (dripping faucet, one light out among several, slow drain, "
       "room uncomfortably warm, projector flickering).",
    1: "Cosmetic or minor (graffiti, scuffed wall, wobbly chair, stained ceiling tile, empty soap).",
}

# --------------------------------------------------------------------------------------------------
# Priority + SLA
# --------------------------------------------------------------------------------------------------
PRIORITIES = ["P1", "P2", "P3", "P4"]
SLA_HOURS: dict[str, int] = {"P1": 1, "P2": 8, "P3": 72, "P4": 336}

# Room types whose problems matter more (labs, restrooms, elevators, mechanical spaces...).
ROOM_CRITICALITY: dict[str, str] = {
    "lab": "high",
    "restroom": "high",
    "elevator": "high",
    "mechanical": "high",
    "kitchen": "high",
    "server": "high",
    "classroom": "medium",
    "corridor": "medium",
    "lobby": "medium",
    "stairwell": "medium",
    "study": "medium",
    "exterior": "medium",
    "office": "normal",
    "conference": "normal",
    "storage": "normal",
    "lounge": "normal",
}

HIGH_CRITICALITY_CATEGORIES = {"elevator_out"}


def location_criticality(room_type: str | None, category: str | None = None) -> str:
    if category in HIGH_CRITICALITY_CATEGORIES:
        return "high"
    return ROOM_CRITICALITY.get((room_type or "").lower(), "normal")


def compute_priority(severity: int, criticality: str, is_hazard: bool) -> tuple[str, str]:
    """Return (priority, explanation). Deterministic and explainable."""
    severity = max(1, min(4, int(severity)))
    if is_hazard:
        return "P1", "Hazard flag forces P1."
    bump = 1 if criticality == "high" else 0
    effective = min(4, severity + bump)
    priority = {4: "P1", 3: "P2", 2: "P3", 1: "P4"}[effective]
    why = f"Severity {severity}"
    if bump:
        why += " + 1 for high-criticality location"
    why += f" = {effective} -> {priority}."
    return priority, why


# --------------------------------------------------------------------------------------------------
# Hazards: deterministic keyword rules. The LLM may ADD a hazard but can never remove one of these.
# --------------------------------------------------------------------------------------------------
HAZARD_TYPES = [
    "gas",
    "electrical",
    "water_intrusion",
    "fire_smoke",
    "structural",
    "slip_trip",
    "biohazard",
    "chemical",
]

HAZARD_LABELS = {
    "gas": "Gas",
    "electrical": "Electrical",
    "water_intrusion": "Water intrusion / flooding",
    "fire_smoke": "Fire / smoke",
    "structural": "Structural",
    "slip_trip": "Slip / trip",
    "biohazard": "Biohazard",
    "chemical": "Chemical",
}

# Plain phrases (matched case-insensitively on word boundaries, flexible whitespace).
HAZARD_KEYWORDS: dict[str, list[str]] = {
    "gas": [
        "smell gas", "smells like gas", "smelled gas", "smelling gas", "gas smell", "gas odor",
        "gas odour", "gas leak", "leaking gas", "rotten egg smell", "rotten eggs", "natural gas",
        "propane smell", "hissing gas",
    ],
    "electrical": [
        "sparking", "sparks", "sparked", "exposed wire", "exposed wires", "exposed wiring", "live wire",
        "bare wire", "bare wires", "electrical fire", "electric shock", "got shocked", "shocked me",
        "electrocuted", "outlet smoking", "smoking outlet", "burning outlet", "melted outlet", "arcing",
    ],
    "water_intrusion": [
        "water pouring", "pouring water", "water gushing", "gushing water", "burst pipe", "pipe burst",
        "flooding", "flooded", "flood", "water everywhere", "inches of water", "water rushing",
        "water coming through the ceiling", "water coming through ceiling",
    ],
    "fire_smoke": [
        "smoky", "flames", "on fire", "burning smell", "smells like burning", "smell of burning",
        "smoldering", "smouldering",
    ],
    "structural": [
        "ceiling sagging", "sagging ceiling", "ceiling is sagging", "ceiling collapsed", "ceiling collapse",
        "collapsed ceiling", "ceiling caving", "caving in", "falling debris", "debris falling",
        "ceiling falling", "cracked beam", "wall collapsing", "structural damage", "falling bricks",
        "stairs collapsing",
    ],
    "slip_trip": [
        "slipped", "slippery", "someone fell", "person fell", "fell down", "tripped", "trip hazard",
        "tripping hazard", "black ice", "icy sidewalk", "icy steps", "icy walkway", "ice on the stairs",
        "ice on the steps", "broken step", "broken stair", "loose railing", "hole in the floor",
        "open manhole",
    ],
    "biohazard": [
        "blood", "bloody", "vomit", "vomited", "threw up", "throw up", "needle", "needles", "syringe",
        "sharps", "feces", "human waste", "sewage", "bodily fluid", "bodily fluids",
    ],
    "chemical": [
        "chemical spill", "chemical smell", "chemical odor", "chemical leak", "spilled chemicals",
        "acid spill", "acid", "ammonia smell", "chlorine smell", "fumes", "toxic", "mercury", "hazmat",
        "corrosive", "solvent spill", "lab spill",
    ],
}

# Hand-written regexes for words that need exclusions ("fire door", "smoke detector" are not hazards).
HAZARD_REGEXES: dict[str, list[str]] = {
    "fire_smoke": [
        r"\bfire\b(?!\s+(?:extinguisher|door|doors|exit|drill|escape|hydrant|lane|marshal|pit))",
        r"\bsmok(?:e|ing)\b(?!\s+(?:detector|detectors))",
    ],
}


def _phrase_to_regex(phrase: str) -> str:
    parts = [re.escape(p) for p in phrase.split()]
    return r"\b" + r"\s+".join(parts) + r"\b"


@dataclass(frozen=True)
class HazardRule:
    hazard_type: str
    pattern: str
    source: str  # the phrase or regex, for the decision log
    regex: re.Pattern


def _build_rules() -> list[HazardRule]:
    rules: list[HazardRule] = []
    for htype, phrases in HAZARD_KEYWORDS.items():
        for phrase in phrases:
            pat = _phrase_to_regex(phrase)
            rules.append(HazardRule(htype, pat, phrase, re.compile(pat, re.IGNORECASE)))
    for htype, pats in HAZARD_REGEXES.items():
        for pat in pats:
            rules.append(HazardRule(htype, pat, pat, re.compile(pat, re.IGNORECASE)))
    return rules


HAZARD_RULES: list[HazardRule] = _build_rules()

# When a rule fires, which category best describes it (used by the no-LLM fast path).
HAZARD_DEFAULT_CATEGORY: dict[str, str] = {
    "gas": "gas_smell",
    "electrical": "exposed_wiring",
    "water_intrusion": "flooding",
    "fire_smoke": "smoke_odor",
    "structural": "ceiling_tile_damage",
    "slip_trip": "trip_hazard",
    "biohazard": "biohazard",
    "chemical": "chemical_spill",
}

# Order used to pick the "primary" hazard when several rules fire.
HAZARD_PRIORITY_ORDER = ["gas", "fire_smoke", "electrical", "chemical", "structural", "water_intrusion",
                         "biohazard", "slip_trip"]

SAFETY_TEXT: dict[str, str] = {
    "gas": "If you smell gas: leave the area now. Do not use light switches, phones or anything that "
           "could spark inside the area. Call 911 / campus police from a safe distance.",
    "fire_smoke": "If you see fire or smoke: pull the nearest fire alarm, leave the building by the "
                  "stairs and call 911.",
    "electrical": "Stay clear of the exposed wiring or sparking equipment. Do not touch it or anything "
                  "wet near it. Keep others away until an electrician arrives.",
    "chemical": "Leave the area and keep others out. Do not try to clean up the chemical. If anyone "
                "was exposed, call 911.",
    "structural": "Move away from the damaged area and keep others clear. Do not stand under a sagging "
                  "or damaged ceiling.",
    "water_intrusion": "Stay away from standing water near outlets or equipment. Move valuables if it is "
                       "safe to do so.",
    "biohazard": "Do not touch or clean it up. Keep others away. Custodial/EHS staff with protective "
                 "equipment are on the way.",
    "slip_trip": "Warn others and keep people away from the area until it is fixed.",
}


# --------------------------------------------------------------------------------------------------
# Asset types (canonical) + synonyms, so free-text from the LLM maps to seeded assets.
# --------------------------------------------------------------------------------------------------
ASSET_SYNONYMS: dict[str, str] = {
    "sink": "sink", "faucet": "sink", "tap": "sink", "basin": "sink",
    "toilet": "toilet", "urinal": "toilet", "commode": "toilet",
    "water fountain": "water fountain", "drinking fountain": "water fountain", "bottle filler": "water fountain",
    "water heater": "water heater",
    "light fixture": "light fixture", "light": "light fixture", "lights": "light fixture", "lamp": "light fixture",
    "bulb": "light fixture", "ceiling light": "light fixture", "led panel": "light fixture",
    "outlet": "outlet", "socket": "outlet", "receptacle": "outlet", "gfci": "outlet",
    "electrical panel": "electrical panel", "breaker panel": "electrical panel", "panel": "electrical panel",
    "thermostat": "thermostat",
    "hvac unit": "HVAC unit", "hvac": "HVAC unit", "air handler": "HVAC unit", "ahu": "HVAC unit",
    "air conditioner": "HVAC unit", "ac unit": "HVAC unit", "vent": "HVAC unit", "diffuser": "HVAC unit",
    "radiator": "HVAC unit",
    "door closer": "door closer", "closer": "door closer", "door": "door closer",
    "lock": "lock", "card reader": "lock", "badge reader": "lock", "keypad": "lock",
    "window": "window",
    "ceiling tile": "ceiling tile",
    "elevator": "elevator", "lift": "elevator",
    "projector": "projector", "display": "projector", "screen": "projector",
    "wifi access point": "wifi access point", "access point": "wifi access point", "router": "wifi access point",
    "fume hood": "fume hood",
    "hand dryer": "hand dryer",
    "soap dispenser": "soap dispenser", "paper towel dispenser": "soap dispenser",
    "chair": "chair", "desk": "desk", "table": "desk",
}


def canonical_asset_type(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in ASSET_SYNONYMS:
        return ASSET_SYNONYMS[v]
    for key in sorted(ASSET_SYNONYMS, key=len, reverse=True):
        if re.search(_phrase_to_regex(key), v):
            return ASSET_SYNONYMS[key]
    return None


def taxonomy_for_prompt() -> str:
    """Render the taxonomy as plain text for the extraction system prompt (stable => cacheable)."""
    lines = ["TRADES: " + ", ".join(TRADES), "", "CATEGORIES (key -> trade: definition):"]
    for c in CATEGORIES:
        lines.append(f"- {c.key} -> {c.trade}: {c.description}")
    lines += ["", "SEVERITY:"]
    for level in (4, 3, 2, 1):
        lines.append(f"- {level}: {SEVERITY_DEFINITIONS[level]}")
    lines += ["", "HAZARD TYPES: " + ", ".join(HAZARD_TYPES)]
    return "\n".join(lines)
