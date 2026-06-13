"""Tests for the /api/send_estimate + /api/estimate_pdf endpoints (S10).

The endpoint must:
  - default to mock mode (no creds / no FF_SEND_ENABLED) → draft, not transmit;
  - in real mode, mint a public PDF URL for the SMS path and pass it through;
  - serve the tokenized PDF publicly so Twilio can fetch it for MMS;
  - never call a real provider in the suite (real mode is exercised via the
    send module's own injected-provider tests, not here).
"""

import pytest
from fastapi.testclient import TestClient

from quillwright.server import app

client = TestClient(app)

ROWS = [
    {"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0},
    {"description": "Labor", "quantity": 2, "unit": "hr", "rate": 90.0},
]


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    # Ensure the endpoint resolves to mock unless a test opts into real.
    monkeypatch.delenv("FF_SEND_ENABLED", raising=False)
    yield


def test_send_sms_mock_drafts_not_transmits():
    r = client.post(
        "/api/send_estimate",
        json={"channel": "sms", "recipient": "+15551234567", "rows": ROWS, "tax_rate": 0.13},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "drafted"
    assert out["transmitted"] is False
    assert out["channel"] == "sms"
    assert "230.52" in out["summary"]  # authoritative total flows through


def test_send_email_mock_drafts():
    r = client.post(
        "/api/send_estimate",
        json={"channel": "email", "recipient": "jane@example.com", "rows": ROWS},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "drafted"


def test_send_bad_channel_returns_400():
    r = client.post(
        "/api/send_estimate",
        json={"channel": "pigeon", "recipient": "x", "rows": ROWS},
    )
    assert r.status_code == 400


def test_send_bad_email_returns_400():
    r = client.post(
        "/api/send_estimate",
        json={"channel": "email", "recipient": "no-at-sign", "rows": ROWS},
    )
    assert r.status_code == 400


def test_send_sms_real_mode_mints_pdf_url_and_serves_it(monkeypatch):
    # Inject a fake SMS provider that captures the media_url the server minted.
    captured = {}

    def fake_sms(*, recipient, body, media_url, summary):
        captured["media_url"] = media_url
        return {"sid": "SM_endpoint_test"}

    monkeypatch.setenv("FF_SEND_ENABLED", "1")
    # Dummy creds so the pre-flight config check passes (the fake provider ignores them).
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_test")
    monkeypatch.setenv("FF_SEND_FROM", "+15550000000")
    monkeypatch.setattr("quillwright.api.send._default_sms_provider", fake_sms)

    r = client.post(
        "/api/send_estimate",
        json={"channel": "sms", "recipient": "+15551234567", "rows": ROWS},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sent"
    assert out["transmitted"] is True
    assert out["provider_id"] == "SM_endpoint_test"

    # The minted URL must point at the public PDF route and actually serve a PDF.
    media_url = captured["media_url"]
    assert "/api/estimate_pdf/" in media_url
    token = media_url.rsplit("/", 1)[-1]
    pdf_resp = client.get(f"/api/estimate_pdf/{token}")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content[:4] == b"%PDF"


def test_estimate_pdf_unknown_token_404():
    assert client.get("/api/estimate_pdf/deadbeef").status_code == 404


def test_sms_real_pdf_render_failure_returns_400_not_500(monkeypatch):
    # A PDF render/IO failure on the SMS path must surface as a clean 400 (like the
    # email path), never an unhandled 500. (Regression for the review finding.)
    monkeypatch.setenv("FF_SEND_ENABLED", "1")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("quillwright.server.render_estimate_pdf_bytes", boom)
    r = client.post(
        "/api/send_estimate",
        json={"channel": "sms", "recipient": "+15551234567", "rows": ROWS},
    )
    assert r.status_code == 400
    assert "disk full" in r.text
