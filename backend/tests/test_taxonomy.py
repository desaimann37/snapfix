import pytest

from app import taxonomy
from app.ai.hazards import decide, rule_hazards


def test_every_category_maps_to_a_known_trade():
    for cat in taxonomy.CATEGORIES:
        assert cat.trade in taxonomy.TRADES, cat.key
    assert len(set(taxonomy.CATEGORY_KEYS)) == len(taxonomy.CATEGORY_KEYS)


def test_about_thirty_categories_including_other():
    assert 28 <= len(taxonomy.CATEGORIES) <= 40
    assert "other" in taxonomy.CATEGORY_BY_KEY


def test_inherent_hazard_categories_use_known_hazard_types():
    for cat in taxonomy.CATEGORIES:
        if cat.hazard_type:
            assert cat.hazard_type in taxonomy.HAZARD_TYPES
    for htype, cat in taxonomy.HAZARD_DEFAULT_CATEGORY.items():
        assert htype in taxonomy.HAZARD_TYPES and cat in taxonomy.CATEGORY_BY_KEY


@pytest.mark.parametrize("severity,criticality,hazard,expected", [
    (4, "normal", False, "P1"),
    (3, "normal", False, "P2"),
    (3, "high", False, "P1"),
    (2, "normal", False, "P3"),
    (2, "medium", False, "P3"),
    (2, "high", False, "P2"),
    (1, "normal", False, "P4"),
    (1, "high", False, "P3"),
    (1, "normal", True, "P1"),
])
def test_priority_matrix(severity, criticality, hazard, expected):
    priority, why = taxonomy.compute_priority(severity, criticality, hazard)
    assert priority == expected
    assert why


def test_sla_hours():
    assert taxonomy.SLA_HOURS == {"P1": 1, "P2": 8, "P3": 72, "P4": 336}


def test_location_criticality():
    assert taxonomy.location_criticality("lab") == "high"
    assert taxonomy.location_criticality("restroom") == "high"
    assert taxonomy.location_criticality("office") == "normal"
    assert taxonomy.location_criticality("office", "elevator_out") == "high"
    assert taxonomy.location_criticality(None) == "normal"


ALL_KEYWORDS = [(h, p) for h, phrases in taxonomy.HAZARD_KEYWORDS.items() for p in phrases]


@pytest.mark.parametrize("hazard_type,phrase", ALL_KEYWORDS, ids=[p for _, p in ALL_KEYWORDS])
def test_every_hazard_keyword_triggers(hazard_type, phrase):
    hits = rule_hazards(f"Hi, there is {phrase} near room 210, please help")
    assert any(h.hazard_type == hazard_type for h in hits), f"'{phrase}' did not trigger {hazard_type}"


@pytest.mark.parametrize("text", [
    "There is a fire in the kitchen",
    "smoke coming out of the vent",
    "SMOKING outlet behind the desk",
    "I SMELL GAS near room 210",
])
def test_hazard_regexes_trigger(text):
    assert rule_hazards(text)


@pytest.mark.parametrize("text", [
    "the fire door won't close",
    "fire extinguisher cabinet is empty",
    "smoke detector keeps chirping",
    "dripping faucet in the men's room",
    "light out in classroom 204",
    "projector won't turn on",
    "it's too hot in here",
    "trash overflowing by the elevator",
    "door closer is broken",
    "wifi is dead in the study room",
])
def test_benign_texts_do_not_trigger(text):
    assert rule_hazards(text) == []


def test_gas_is_primary_when_multiple_rules_fire():
    hits = rule_hazards("I smell gas and the floor is slippery")
    assert hits[0].hazard_type == "gas"
    assert {h.hazard_type for h in hits} == {"gas", "slip_trip"}


def test_llm_cannot_remove_a_rule_hazard():
    decision = decide(rule_hazards("I smell gas in room 210"), llm_is_hazard=False, llm_hazard_type=None)
    assert decision.is_hazard and decision.hazard_type == "gas"
    assert decision.sources == ["rules"]


def test_llm_can_add_a_hazard():
    decision = decide([], llm_is_hazard=True, llm_hazard_type="structural")
    assert decision.is_hazard and decision.hazard_type == "structural"
    assert decision.sources == ["llm"]


def test_no_hazard():
    decision = decide([], llm_is_hazard=False)
    assert not decision.is_hazard and decision.hazard_type is None


@pytest.mark.parametrize("raw,expected", [
    ("faucet", "sink"),
    ("Kitchen sink", "sink"),
    ("LED panel", "light fixture"),
    ("ceiling light", "light fixture"),
    ("GFCI outlet", "outlet"),
    ("door closer arm", "door closer"),
    ("spaceship", None),
    (None, None),
])
def test_canonical_asset_type(raw, expected):
    assert taxonomy.canonical_asset_type(raw) == expected


def test_taxonomy_prompt_lists_every_category():
    text = taxonomy.taxonomy_for_prompt()
    for key in taxonomy.CATEGORY_KEYS:
        assert f"- {key} ->" in text
