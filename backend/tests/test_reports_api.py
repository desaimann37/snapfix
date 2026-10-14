import io
from pathlib import Path

from PIL import Image

from app.config import get_settings


def jpeg_bytes(with_gps: bool = False, size=(2400, 1600)) -> bytes:
    img = Image.new("RGB", size, (180, 190, 200))
    buf = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (38.0, 49.0, 53.76), 3: "W", 4: (77.0, 18.0, 28.08)}
        img.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def submit(client, *, text="", image: bytes | None = None, **form):
    files = {"image": ("photo.jpg", image, "image/jpeg")} if image else None
    return client.post("/api/reports", data={"text": text, **form}, files=files)


def test_photo_and_text_to_plumbing_ticket(reseed, client):
    r = submit(client, text="the sink in the 1st floor women's restroom in engineering keeps dripping",
               image=jpeg_bytes())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm_mode"] == "mock"
    assert body["draft"]["category"] == "leak_water" and body["draft"]["trade"] == "Plumbing"
    assert body["location"]["room"] == "111" and body["location_method"] == "text"
    assert body["needs_confirmation"] is False
    assert body["photo_url"].startswith("/media/") and body["analysis_ms"] >= 0

    c = client.post(f"/api/reports/{body['report_id']}/confirm", json={"client_elapsed_ms": 14200})
    assert c.status_code == 200, c.text
    out = c.json()
    t = out["ticket"]
    assert t["trade"] == "Plumbing" and t["team"]["name"] == "Plumbing Shop"
    assert t["location"]["room"] == "111" and t["status"] == "triaged"
    assert t["asset"] is not None and t["asset"]["type"] == "sink"
    assert out["photo_to_ticket_ms"] >= 0 and out["client_elapsed_ms"] == 14200

    detail = client.get(f"/api/tickets/{t['short_code']}").json()
    assert [e["type"] for e in detail["events"]][:2] == ["created", "assigned"]
    assert detail["reports"][0]["photo_url"] == body["photo_url"]
    assert client.get(body["photo_url"]).status_code == 200


def test_report_at_repeat_sink_merges_into_open_ticket(reseed, client):
    """The planted repeat-failure sink already has an open leak ticket: a new report merges into it."""
    body = submit(client, text="the sink in the 2nd floor men's room of the library keeps dripping",
                  image=jpeg_bytes()).json()
    out = client.post(f"/api/reports/{body['report_id']}/confirm", json={}).json()
    assert out["merged"] is True and out["report_count"] == 3
    assert "Already reported" in out["message"] and "3 people" in out["message"]
    assert out["ticket"]["asset"]["tag"] == "LIB-225-SINK-1"


def test_qr_route_resolves_location(client, seeded):
    body = submit(client, text="chair is broken", location_code="engr-101").json()
    assert body["location"]["qr_code"] == "engr-101" and body["location_method"] == "qr"
    assert body["draft"]["category"] == "broken_furniture"


def test_exif_is_stripped_but_gps_used(client, seeded):
    body = submit(client, text="light out", image=jpeg_bytes(with_gps=True)).json()
    saved = Path(get_settings().upload_dir) / Path(body["photo_url"]).name
    img = Image.open(saved)
    assert not img.getexif()  # no EXIF (incl. GPS) on disk
    assert max(img.size) == 1568  # resized to the long-edge limit
    assert body["location_method"] == "gps"  # GPS read before stripping -> Library candidates
    assert all(c["building_code"] == "LIB" for c in body["location_candidates"])


def test_needs_confirmation_when_location_unknown(client, seeded):
    body = submit(client, text="light flickering").json()
    assert body["needs_confirmation"] is True and body["location"] is None
    assert any("where" in r.lower() for r in body["confirmation_reasons"])
    r = client.post(f"/api/reports/{body['report_id']}/confirm", json={})
    assert r.status_code == 422
    loc = client.get("/api/locations/engr-204").json()
    r = client.post(f"/api/reports/{body['report_id']}/confirm", json={"location_id": loc["id"]})
    assert r.status_code == 200 and r.json()["ticket"]["location"]["room"] == "204"


def test_confirm_with_edits_and_idempotency(client, seeded):
    body = submit(client, text="something wrong in room 305").json()
    r = client.post(f"/api/reports/{body['report_id']}/confirm",
                    json={"edits": {"category": "projector_broken", "title": "Projector dead in 305", "severity": 3}})
    t = r.json()["ticket"]
    assert t["category"] == "projector_broken" and t["trade"] == "IT/AV" and t["title"] == "Projector dead in 305"
    again = client.post(f"/api/reports/{body['report_id']}/confirm", json={}).json()
    assert again["ticket"]["id"] == t["id"] and "Already submitted" in again["message"]


def test_rejects_bad_input(client, seeded):
    assert submit(client).status_code == 422  # nothing to report
    r = client.post("/api/reports", data={"text": "x"}, files={"image": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    r = client.post("/api/reports", data={"text": "x"}, files={"image": ("a.jpg", b"not really a jpeg", "image/jpeg")})
    assert r.status_code == 415
    big = b"\xff\xd8" + b"0" * (11 * 1024 * 1024)
    r = client.post("/api/reports", data={"text": "x"}, files={"image": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413


def test_taxonomy_and_public_config(client):
    tax = client.get("/api/taxonomy").json()
    assert len(tax["categories"]) >= 30 and "Plumbing" in tax["trades"]
    cfg = client.get("/api/config/public").json()
    assert cfg["llm_mode"] == "mock" and "911" in cfg["emergency_text"]
