import uuid
from types import SimpleNamespace

import pytest

from app.ai import dedupe as D


def _loc(building, floor, lid=None):
    return SimpleNamespace(id=lid or uuid.uuid4(), building_id=building, floor=floor, label=f"Room on floor {floor}")


def _ticket(location, category="leak_water"):
    return SimpleNamespace(location=location, location_id=location.id if location else None,
                           building_id=location.building_id if location else None, category=category,
                           short_code="SF-0001", title="t", summary="s", report_count=1, location_text=None)


def test_location_score_levels():
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    room = _loc(b1, 3)
    assert D.location_score(room, _ticket(room)) == 1.0
    assert D.location_score(room, _ticket(_loc(b1, 3))) == 0.6
    assert D.location_score(room, _ticket(_loc(b1, 1))) == 0.3
    assert D.location_score(room, _ticket(_loc(b2, 3))) == 0.0


def test_formula_weights():
    assert (D.W_TEXT, D.W_LOCATION, D.W_CATEGORY) == (0.55, 0.25, 0.20)
    assert (D.AUTO_MERGE, D.ASK_LLM) == (0.80, 0.60)


def test_calibration_is_clamped():
    assert D.calibrated(-1.0) == 0.0 and D.calibrated(2.0) == 1.0


def _cand(score, same_room=True, category="leak_water"):
    room = _loc(uuid.uuid4(), 2)
    t = _ticket(room, category)
    return D.Candidate(ticket=t, cosine=0.85, text_sim=0.8, location_score=1.0 if same_room else 0.6,
                       category_match=1.0, score=score), room


def test_thresholds():
    c, room = _cand(0.85)
    assert D.decide_duplicate([c], title="a", summary="b", category="leak_water", location=room).decision == "merge"
    c, room = _cand(0.55)
    assert D.decide_duplicate([c], title="a", summary="b", category="leak_water", location=room).decision == "new"
    assert D.decide_duplicate([], title="a", summary="b", category="leak_water", location=room).decision == "new"


def test_borderline_asks_the_fast_model():
    c, room = _cand(0.7)
    same = D.decide_duplicate([c], title="a", summary="b", category="leak_water", location=room)
    assert same.llm_used and same.decision == "merge" and same.llm_mode == "mock"
    other_room = _loc(room.building_id, 2)
    diff = D.decide_duplicate([c], title="a", summary="b", category="leak_water", location=other_room)
    assert diff.llm_used and diff.decision == "new"
    assert "Haiku" in diff.rationale


def test_strong_match_in_another_room_is_never_auto_merged():
    c, room = _cand(0.9, same_room=False)
    other_room = _loc(room.building_id, 3)
    result = D.decide_duplicate([c], title="a", summary="b", category="leak_water", location=other_room)
    assert result.llm_used and result.decision == "new"
    assert "different room" in result.rationale


def submit(client, text, code):
    return client.post("/api/reports", data={"text": text, "location_code": code}).json()


def confirm(client, report_id):
    return client.post(f"/api/reports/{report_id}/confirm", json={}).json()


def test_three_reports_of_the_same_leak_make_one_ticket(reseed, client):
    texts = [
        "water dripping from the ceiling",
        "the ceiling is leaking onto my desk",
        "there's a leak, water keeps dripping on the carpet",
    ]
    outs = [confirm(client, submit(client, t, "engr-207")["report_id"]) for t in texts]
    codes = {o["ticket"]["short_code"] for o in outs}
    assert len(codes) == 1
    assert [o["merged"] for o in outs] == [False, True, True]
    assert outs[-1]["report_count"] == 3 and "3 people" in outs[-1]["message"]

    detail = client.get(f"/api/tickets/{codes.pop()}").json()
    merges = [e for e in detail["events"] if e["type"] == "merged"]
    assert len(merges) == 2 and merges[0]["payload"]["best"]["score"] >= 0.6
    assert len(detail["reports"]) == 3

    other = confirm(client, submit(client, "the light is out", "engr-207")["report_id"])
    assert other["merged"] is False and other["ticket"]["short_code"] not in codes


@pytest.mark.parametrize("category", ["leak_water", "projector_broken"])
def test_merge_never_lowers_severity(reseed, client, db, category):
    from app.ai.dedupe import DedupeResult
    from app.ai.hazards import decide
    from app.models import Report, Ticket
    from app.pipeline import merge_into_ticket
    from app.schemas import TicketDraft

    ticket = db.query(Ticket).filter(Ticket.status == "triaged").first()
    ticket.severity, ticket.priority = 3, "P2"
    report = Report(text="x")
    db.add(report)
    db.flush()
    low = TicketDraft(title="t", summary="s", category=category, trade="Plumbing", severity=1, severity_reason="r",
                      is_hazard=False, hazard_type=None, asset_type=None, location_text_from_image=None,
                      location_text_from_user=None, visible_evidence=[], needs_clarification=False,
                      clarifying_question=None, confidence=0.9, image_relevant=True)
    merge_into_ticket(db, ticket, report, draft=low, hazard=decide([]), dedupe=DedupeResult("merge", None))
    assert ticket.severity == 3 and ticket.priority == "P2"
    db.rollback()
