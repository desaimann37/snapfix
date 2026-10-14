import pytest

pytestmark = pytest.mark.usefixtures("module_seed")


def test_health(client):
    body = client.get("/api/health").json()
    assert body["db"] is True and body["llm_mode"] == "mock"


def test_queue_pins_hazards_first(client):
    items = client.get("/api/tickets", params={"status": "open"}).json()["items"]
    assert items[0]["is_hazard"] is True
    non_hazard = [i["priority"] for i in items if not i["is_hazard"]]
    assert non_hazard == sorted(non_hazard)


def test_filters(client):
    plumbing = client.get("/api/tickets", params={"trade": "Plumbing", "limit": 50}).json()
    assert plumbing["total"] > 0 and all(t["trade"] == "Plumbing" for t in plumbing["items"])
    engr = client.get("/api/tickets", params={"building": "ENGR", "limit": 50}).json()
    assert all(t["location"]["building_code"] == "ENGR" for t in engr["items"])
    p1 = client.get("/api/tickets", params={"priority": "p1"}).json()
    assert all(t["priority"] == "P1" for t in p1["items"])
    hazard = client.get("/api/tickets", params={"hazard": "true", "status": "open"}).json()
    assert hazard["total"] == 1
    search = client.get("/api/tickets", params={"q": "faucet leaking again"}).json()
    assert search["total"] >= 1


def test_detail_by_short_code_includes_decision_log(client):
    hazard = client.get("/api/tickets", params={"hazard": "true", "status": "open"}).json()["items"][0]
    detail = client.get(f"/api/tickets/{hazard['short_code']}").json()
    assert detail["id"] == hazard["id"]
    types = [e["type"] for e in detail["events"]]
    assert types[:3] == ["created", "escalated", "assigned"]
    assert detail["reports"] and detail["location"]["qr_code"] == "stuc-249"


def test_unknown_ticket_404(client):
    assert client.get("/api/tickets/SF-0001").status_code == 404


def test_patch_status_writes_audit_event(reseed, client):
    ticket = client.get("/api/tickets", params={"status": "triaged", "limit": 1}).json()["items"][0]
    r = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "in_progress", "actor": "test", "note": "on it"})
    assert r.status_code == 200
    detail = r.json()
    assert detail["status"] == "in_progress"
    last = detail["events"][-1]
    assert last["type"] == "status_changed" and last["actor"] == "user:test"
    assert last["payload"]["to"] == "in_progress"


def test_location_lookup_and_search(client):
    loc = client.get("/api/locations/engr-101").json()
    assert "Innovation Lab" in loc["label"] and loc["building_code"] == "ENGR"
    assert client.get("/api/locations/nope-999").status_code == 404
    results = client.get("/api/locations/search", params={"q": "210"}).json()
    assert results[0]["room"] == "210"


def test_floor_plan_counts(client):
    plan = client.get("/api/buildings/ENGR/floors/3").json()
    rooms = {r["room"]: r for r in plan["rooms"]}
    assert rooms["312"]["open_count"] >= 1
    assert all(0 <= r["x"] <= 1000 and 0 <= r["y"] <= 400 for r in plan["rooms"])
