from types import SimpleNamespace

import pytest

from app import runtime
from app.ai import extract
from app.ai.llm import LLMError, llm
from app.schemas import TicketDraft


@pytest.mark.parametrize("text,category,trade", [
    ("the sink in room 312 keeps dripping", "leak_water", "Plumbing"),
    ("toilet in the men's room won't flush", "toilet_malfunction", "Plumbing"),
    ("projector won't turn on before my lecture", "projector_broken", "IT/AV"),
    ("it's freezing in the reading room", "too_cold", "HVAC"),
    ("trash cans overflowing in the lobby", "trash_overflow", "Custodial"),
    ("I smell gas near room 210", "gas_smell", "Safety/Environmental"),
    ("water pouring from the ceiling", "flooding", "Plumbing"),
    ("wires hanging out of the ceiling and sparking", "exposed_wiring", "Electrical"),
])
def test_mock_extract_categories(text, category, trade):
    draft = extract.mock_extract(text, has_image=False)
    assert draft.category == category
    assert draft.trade == trade
    assert len(draft.title) <= 70


def test_mock_extract_hazard_and_asset():
    draft = extract.mock_extract("I smell gas near room 210", has_image=False)
    assert draft.is_hazard and draft.hazard_type == "gas" and draft.severity == 4
    assert draft.location_text_from_user == "room 210"
    sink = extract.mock_extract("the faucet keeps dripping", has_image=True)
    assert sink.asset_type == "sink" and "Photo attached" in sink.summary


def test_mock_photo_without_text_asks_one_question():
    draft = extract.mock_extract("", has_image=True)
    assert draft.needs_clarification and draft.clarifying_question
    assert draft.confidence < 0.5


def test_mock_scrubs_personal_info():
    draft = extract.mock_extract("leak in 312, call me at 703-555-0199 or jo@example.com", has_image=False)
    assert "555" not in draft.summary and "example.com" not in draft.summary


def test_normalize_forces_trade_from_category_and_truncates():
    draft = extract.mock_extract("sink dripping", has_image=False).model_copy(
        update={"trade": "Electrical", "title": "x" * 120, "confidence": 3.0})
    fixed = extract.normalize(draft)
    assert fixed.trade == "Plumbing" and len(fixed.title) <= 70 and fixed.confidence == 1.0


def test_extract_falls_back_when_llm_fails(monkeypatch):
    def boom(**_):
        raise LLMError("network down")

    monkeypatch.setattr(llm, "structured", boom)
    result = extract.extract_draft(image_jpeg=None, text="sink dripping in 312")
    assert result.mode == "fallback" and result.draft.category == "other" and result.draft.confidence == 0.0
    assert "network down" in result.error


def test_system_prompt_has_taxonomy_and_examples():
    prompt = extract.system_prompt()
    assert "{{TAXONOMY}}" not in prompt
    assert "- leak_water -> Plumbing" in prompt and "Example 8" in prompt


def test_live_call_shape(monkeypatch):
    """Live mode sends a cached system prompt, a base64 JPEG and a structured-output schema (no forced tool)."""
    captured = {}
    draft = extract.mock_extract("sink dripping", has_image=True)

    class FakeMessages:
        def parse(self, **kwargs):
            captured.update(kwargs)
            usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=3000,
                                    cache_creation_input_tokens=0)
            return SimpleNamespace(parsed_output=draft, stop_reason="end_turn", usage=usage, _request_id="req_test")

    monkeypatch.setattr(runtime, "effective_llm_mode", lambda: "live")
    monkeypatch.setattr("app.ai.llm.effective_llm_mode", lambda: "live")
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(messages=FakeMessages()))

    result = extract.extract_draft(image_jpeg=b"\xff\xd8fakejpeg", text="sink dripping",
                                   location_context="Library, 2F Men's Restroom (room 225)")
    assert result.mode == "live" and result.draft.category == "leak_water"
    assert captured["model"] == "claude-sonnet-5-5"
    assert captured["output_format"] is TicketDraft
    assert captured["output_config"] == {"effort": "low"}
    assert "tool_choice" not in captured and "temperature" not in captured
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert "room 225" in content[1]["text"]
    # cost = (1200*2 + 3000*0.2 + 300*10) / 1e6
    assert result.usage.cost_usd == pytest.approx((1200 * 2.0 + 3000 * 2.0 * 0.1 + 300 * 10.0) / 1e6)


def test_live_refusal_degrades(monkeypatch):
    class FakeMessages:
        def parse(self, **kwargs):
            usage = SimpleNamespace(input_tokens=10, output_tokens=0, cache_read_input_tokens=0,
                                    cache_creation_input_tokens=0)
            return SimpleNamespace(parsed_output=None, stop_reason="refusal", usage=usage, _request_id="r")

    monkeypatch.setattr("app.ai.llm.effective_llm_mode", lambda: "live")
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(messages=FakeMessages()))
    result = extract.extract_draft(image_jpeg=None, text="sink dripping")
    assert result.mode == "fallback" and "declined" in result.error
