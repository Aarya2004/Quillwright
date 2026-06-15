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
    voice.reset_calls()
    yield
    est_api.reset_estimate_store()
    voice.reset_calls()


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
        call_sid="CA_test",
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
    # The spoken TwiML reads back the total, then ASKS (conversational, not a hang-up).
    assert "<Say " in result["twiml"]  # voiced <Say voice="...">
    assert f"{result['estimate']['total']:.2f}" in result["twiml"]
    assert "<Gather" in result["twiml"] and 'input="speech"' in result["twiml"]
    assert "/api/voice/refine" in result["twiml"]
    # It does NOT text yet — the PDF goes out when the caller says they're done.
    assert sent == {}
    # Call state is held so the refine turns can edit the same rows.
    assert voice._call_state("CA_test") is not None


def test_handle_recording_empty_transcript_is_graceful():
    result = voice.handle_recording(
        recording_url="https://api.twilio.com/rec/empty",
        from_number="+15551234567",
        call_sid="CA_empty",
        download=lambda url: "/tmp/x.wav",
        transcribe=lambda path: {"transcript": ""},
        sms=lambda **kw: {"sid": "x"},
        base_url="https://demo.example.com",
    )
    # No transcript → no forge, a polite spoken fallback, nothing saved.
    assert result["estimate"] is None
    assert "<Say " in result["twiml"]
    assert est_api.estimate_store().list_estimates() == []


# --- conversational refine loop (Tier A) ---


def _fresh_call(call_sid="CA_conv"):
    """Forge an estimate on a call so a refine turn has state to edit. Returns the
    captured SMS dict (populated only when the loop finishes)."""
    sent = {}
    voice.handle_recording(
        recording_url="https://api.twilio.com/rec/abc",
        from_number="+15551234567",
        call_sid=call_sid,
        download=lambda url: "/tmp/x.wav",
        transcribe=lambda path: {
            "transcript": "replaced the capacitor and contactor, one hour labor"
        },
        sms=lambda **kw: sent.update(kw) or {"sid": "SM"},
        base_url="https://demo.example.com",
    )
    return sent


def test_refine_adds_an_item_and_reasks():
    sent = _fresh_call("CA_add")
    before = voice._call_state("CA_add")["rows"]
    out = voice.handle_refine(
        call_sid="CA_add",
        speech_result="add a refrigerant",
        base_url="https://demo.example.com",
        sms=lambda **kw: sent.update(kw),
    )
    after = voice._call_state("CA_add")["rows"]
    assert len(after) == len(before) + 1  # the refrigerant line was added (catalog-priced)
    assert "<Gather" in out["twiml"] and "/api/voice/refine" in out["twiml"]  # still asking
    assert sent == {}  # not done yet → no text


def test_refine_done_texts_pdf_and_ends():
    sent = _fresh_call("CA_done")
    out = voice.handle_refine(
        call_sid="CA_done",
        speech_result="no that's it",
        base_url="https://demo.example.com",
        sms=lambda **kw: sent.update(kw),
    )
    # Finishing speaks a goodbye, texts the PDF, and does NOT <Gather> again.
    assert "<Gather" not in out["twiml"]
    assert sent["to"] == "+15551234567"
    assert sent["media_url"].startswith("https://demo.example.com/api/estimate_pdf/")
    # Call state is cleared once the conversation ends.
    assert voice._call_state("CA_done") is None


def test_refine_unknown_call_is_graceful():
    out = voice.handle_refine(
        call_sid="CA_nonexistent",
        speech_result="add a contactor",
        base_url="https://demo.example.com",
        sms=lambda **kw: None,
    )
    assert "<Say " in out["twiml"]  # a polite fallback, no crash


# --- async job pattern (forge runs off-thread; Twilio polls /api/voice/status) ---


def test_status_unknown_call_is_graceful():
    out = voice.handle_status(call_sid="CA_never", base_url="https://demo.example.com")
    assert "<Say " in out  # polite fallback, no crash


def test_status_while_working_holds_and_redirects():
    voice._JOBS["CA_w"] = {"status": "working", "twiml": None}
    out = voice.handle_status(call_sid="CA_w", base_url="https://demo.example.com")
    assert "<Pause" in out and "/api/voice/status" in out  # parks Twilio, polls again


def test_status_when_done_returns_the_jobs_twiml():
    voice._JOBS["CA_d"] = {"status": "done", "twiml": "<Response><Say>ready</Say></Response>"}
    out = voice.handle_status(call_sid="CA_d", base_url="https://demo.example.com")
    assert out == "<Response><Say>ready</Say></Response>"
    assert "CA_d" not in voice._JOBS  # cleared after delivery


def test_start_recording_job_returns_immediately_then_completes():
    import time

    # Inject fast stubs so the background thread finishes quickly (no model, no network).
    def fake_download(url):
        return "/tmp/x.wav"

    # Patch the module-level default the background job uses via handle_recording.
    orig_dl = voice._download_recording
    voice._download_recording = fake_download
    try:
        twiml = voice.start_recording_job(
            recording_url="https://api.twilio.com/rec/abc",
            from_number="+15551234567",
            call_sid="CA_job",
            base_url="https://demo.example.com",
        )
        # Returns a holding response straight away.
        assert "<Pause" in twiml and "/api/voice/status" in twiml
        # The job eventually completes (stub forge is fast). Poll briefly.
        for _ in range(50):
            if voice._JOBS.get("CA_job", {}).get("status") != "working":
                break
            time.sleep(0.1)
        assert voice._JOBS["CA_job"]["status"] in ("done", "error")
    finally:
        voice._download_recording = orig_dl


def test_voice_endpoints_are_wired():
    from fastapi.testclient import TestClient

    from quillwright.server import app

    client = TestClient(app)
    # The inbound greeting webhook returns TwiML (form-POST, like Twilio sends).
    r = client.post("/api/voice/incoming")
    assert r.status_code == 200
    assert "<Record" in r.text
    assert "xml" in r.headers["content-type"]
    # The refine webhook exists too.
    r2 = client.post("/api/voice/refine", data={"CallSid": "CA_x", "SpeechResult": "done"})
    assert r2.status_code == 200
    assert "xml" in r2.headers["content-type"]
