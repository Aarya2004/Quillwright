"""Tier 3 — pairing + QR HTTP endpoints + the mobile capture page."""

from fastapi.testclient import TestClient

from quillwright import pairing
from quillwright.server import app

client = TestClient(app)


def setup_function():
    pairing.reset()


def test_create_pairing_returns_code_and_capture_url_and_qr():
    r = client.post("/api/pair/create")
    assert r.status_code == 200
    body = r.json()
    assert body["code"]
    assert body["capture_url"].endswith(f"/m/{body['code']}")
    assert body["qr_svg"].lstrip().startswith("<svg")  # an inline SVG QR


def test_poll_empty_then_capture_then_delivered_once():
    code = client.post("/api/pair/create").json()["code"]
    assert client.get(f"/api/pair/{code}").json()["capture"] is None
    client.post(
        f"/api/pair/{code}/capture",
        json={"image_paths": ["/tmp/p.png"], "transcript": "replaced the capacitor"},
    )
    got = client.get(f"/api/pair/{code}").json()["capture"]
    assert got["transcript"] == "replaced the capacitor"
    # consumed
    assert client.get(f"/api/pair/{code}").json()["capture"] is None


def test_capture_to_unknown_code_is_404():
    r = client.post("/api/pair/bogus/capture", json={"transcript": "x"})
    assert r.status_code == 404


def test_mobile_capture_page_served_for_valid_code():
    code = client.post("/api/pair/create").json()["code"]
    r = client.get(f"/m/{code}")
    assert r.status_code == 200
    assert "capture" in r.text.lower()


def test_mobile_capture_page_rejects_unknown_code():
    r = client.get("/m/bogus")
    assert r.status_code == 404
