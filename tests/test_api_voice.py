"""Tier 2 — inbound voice-call capture (S12).

Call a Twilio number → the agent records the caller, transcribes the recording,
forges an estimate, saves it as a DRAFT (ADR-0013), reads back a spoken summary,
and texts the PDF. Tested without the `twilio` package or a network: the recording
download and the SMS send are injectable.
"""

import pytest

import quillwright.api.estimate as est_api
from quillwright.api import voice


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FF_ESTIMATE_STORE", str(tmp_path))
    est_api.reset_estimate_store()
    yield
    est_api.reset_estimate_store()


def test_greeting_twiml_records_to_the_recording_endpoint(monkeypatch):
    monkeypatch.setenv("FF_PUBLIC_BASE_URL", "https://demo.example.com")
    xml = voice.greeting_twiml()
    assert xml.startswith("<?xml")
    assert "<Response>" in xml
    assert "<Record" in xml
    # Records POST to the recording-complete webhook on the public base URL.
    assert "https://demo.example.com/api/voice/recording" in xml


def test_greeting_twiml_uses_relative_action_without_base_url(monkeypatch):
    monkeypatch.delenv("FF_PUBLIC_BASE_URL", raising=False)
    xml = voice.greeting_twiml()
    assert 'action="/api/voice/recording"' in xml


def test_handle_recording_forges_saves_draft_and_summarizes():
    def fake_download(url):
        # Pretend we fetched the .wav; return a local path the stub transcriber reads.
        return "/tmp/does-not-matter.wav"

    def fake_transcribe(path):
        return {"transcript": "replaced the capacitor and contactor, one hour labor"}

    sent = {}

    def fake_sms(*, to, body, media_url):
        sent.update(to=to, body=body, media_url=media_url)
        return {"sid": "SM_test"}

    result = voice.handle_recording(
        recording_url="https://api.twilio.com/rec/abc",
        from_number="+15551234567",
        download=fake_download,
        transcribe=fake_transcribe,
        sms=fake_sms,
        base_url="https://demo.example.com",
    )

    # The estimate was forged and is non-empty.
    assert result["estimate"]["line_items"]
    assert result["estimate"]["total"] > 0
    # It was saved as a DRAFT in the per-account store.
    listed = est_api.estimate_store().list_estimates()
    assert len(listed) == 1
    # The spoken TwiML reads back the total.
    assert "<Say>" in result["twiml"]
    assert f"{result['estimate']['total']:.2f}" in result["twiml"]
    # The caller was texted the PDF link.
    assert sent["to"] == "+15551234567"
    assert sent["media_url"].startswith("https://demo.example.com/api/estimate_pdf/")


def test_handle_recording_empty_transcript_is_graceful():
    result = voice.handle_recording(
        recording_url="https://api.twilio.com/rec/empty",
        from_number="+15551234567",
        download=lambda url: "/tmp/x.wav",
        transcribe=lambda path: {"transcript": ""},
        sms=lambda **kw: {"sid": "x"},
        base_url="https://demo.example.com",
    )
    # No transcript → no forge, a polite spoken fallback, nothing saved.
    assert result["estimate"] is None
    assert "<Say>" in result["twiml"]
    assert est_api.estimate_store().list_estimates() == []


def test_handle_recording_skips_sms_when_no_from_number():
    calls = []
    voice.handle_recording(
        recording_url="https://api.twilio.com/rec/abc",
        from_number="",
        download=lambda url: "/tmp/x.wav",
        transcribe=lambda path: {"transcript": "topped up refrigerant and labor"},
        sms=lambda **kw: calls.append(kw),
        base_url="https://demo.example.com",
    )
    assert calls == []  # nothing to text


def test_voice_endpoints_are_wired():
    from fastapi.testclient import TestClient

    from quillwright.server import app

    client = TestClient(app)
    # The inbound greeting webhook returns TwiML (form-POST, like Twilio sends).
    r = client.post("/api/voice/incoming")
    assert r.status_code == 200
    assert "<Record" in r.text
    assert "xml" in r.headers["content-type"]
