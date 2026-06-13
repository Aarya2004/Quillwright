"""Tests for Finalize & Send (S10, ADR-0005 honest-framing).

The send layer must:
  - resolve three states like FF_REAL_MODELS does: real-send (enabled + creds),
    mock-confirm (Space / disabled), and refuse-on-bad-input;
  - never hit the network in the test suite (providers are injected/mocked);
  - keep Facts-from-Tools: send adds no numbers — the PDF/summary come from recalc.
"""

import pytest

from quillwright.api import send as send_mod
from quillwright.api.send import (
    SendError,
    estimate_summary_line,
    resolve_send_mode,
    send_estimate,
)

ROWS = [
    {"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0},
    {"description": "Labor", "quantity": 2, "unit": "hr", "rate": 90.0},
]


# --- mode resolution -------------------------------------------------------


def test_mode_is_mock_by_default(monkeypatch):
    monkeypatch.delenv("FF_SEND_ENABLED", raising=False)
    assert resolve_send_mode() == "mock"


def test_mode_is_real_only_when_enabled_flag_set(monkeypatch):
    monkeypatch.setenv("FF_SEND_ENABLED", "1")
    assert resolve_send_mode() == "real"
    monkeypatch.setenv("FF_SEND_ENABLED", "0")
    assert resolve_send_mode() == "mock"


# --- input validation (refuse before any provider work) --------------------


def test_send_rejects_unknown_channel():
    with pytest.raises(SendError):
        send_estimate(channel="carrier-pigeon", recipient="x", rows=ROWS, mode="mock")


def test_sms_rejects_empty_recipient():
    with pytest.raises(SendError):
        send_estimate(channel="sms", recipient="  ", rows=ROWS, mode="mock")


def test_email_rejects_recipient_without_at_sign():
    with pytest.raises(SendError):
        send_estimate(channel="email", recipient="not-an-email", rows=ROWS, mode="mock")


# --- mock path (Space / disabled): drafts, never transmits -----------------


def test_mock_sms_reports_drafted_not_sent():
    out = send_estimate(channel="sms", recipient="+15551234567", rows=ROWS, mode="mock")
    assert out["status"] == "drafted"  # honest: nothing left the box
    assert out["transmitted"] is False
    assert out["channel"] == "sms"
    assert out["recipient"] == "+15551234567"
    # summary carries the authoritative total (Facts-from-Tools), no provider id
    assert "$" in out["summary"]
    assert "provider_id" not in out or out["provider_id"] is None


def test_mock_email_reports_drafted_not_sent():
    out = send_estimate(channel="email", recipient="jane@example.com", rows=ROWS, mode="mock")
    assert out["status"] == "drafted"
    assert out["transmitted"] is False
    assert out["channel"] == "email"


# --- real path with INJECTED providers (no network) ------------------------


def test_real_sms_calls_sms_provider_and_reports_sent(monkeypatch):
    calls = {}

    def fake_sms(*, recipient, body, media_url, summary):
        calls["recipient"] = recipient
        calls["media_url"] = media_url
        return {"sid": "SM_fake_123"}

    out = send_estimate(
        channel="sms",
        recipient="+15551234567",
        rows=ROWS,
        mode="real",
        sms_provider=fake_sms,
        pdf_url="https://example.test/e/abc.pdf",
    )
    assert out["status"] == "sent"
    assert out["transmitted"] is True
    assert out["provider_id"] == "SM_fake_123"
    assert calls["recipient"] == "+15551234567"
    assert calls["media_url"] == "https://example.test/e/abc.pdf"  # MMS attaches via URL


def test_real_email_calls_email_provider_with_pdf_bytes(monkeypatch):
    seen = {}

    def fake_email(*, recipient, subject, body, pdf_bytes, filename):
        seen["recipient"] = recipient
        seen["pdf_len"] = len(pdf_bytes)
        seen["filename"] = filename
        return {"id": "EM_fake_456"}

    out = send_estimate(
        channel="email",
        recipient="jane@example.com",
        rows=ROWS,
        mode="real",
        email_provider=fake_email,
    )
    assert out["status"] == "sent"
    assert out["provider_id"] == "EM_fake_456"
    assert seen["recipient"] == "jane@example.com"
    assert seen["pdf_len"] > 0  # a real PDF was rendered and attached
    assert seen["filename"].endswith(".pdf")


def test_real_sms_without_pdf_url_errors_loud(monkeypatch):
    # MMS cannot attach a local file; a public PDF URL is required. Fail loud,
    # never silently downgrade to a link-less text (mirrors the brain's loud
    # failure when FF_BACKEND=modal lacks its URL).
    def fake_sms(**_):
        raise AssertionError("provider must not be called without a media url")

    with pytest.raises(SendError):
        send_estimate(
            channel="sms",
            recipient="+15551234567",
            rows=ROWS,
            mode="real",
            sms_provider=fake_sms,
            pdf_url=None,
        )


def test_provider_failure_surfaces_as_send_error(monkeypatch):
    def boom(**_):
        raise RuntimeError("twilio 401")

    with pytest.raises(SendError):
        send_estimate(
            channel="email",
            recipient="jane@example.com",
            rows=ROWS,
            mode="real",
            email_provider=boom,
        )


# --- summary is authoritative (Facts-from-Tools) ---------------------------


def test_estimate_summary_uses_recalc_total():
    # 24*1 + 90*2 = 204 subtotal; *1.13 = 230.52 total
    summary = estimate_summary_line(ROWS, job_title="AC Repair", tax_rate=0.13)
    assert "230.52" in summary
    assert "AC Repair" in summary


def test_default_real_providers_are_lazy(monkeypatch):
    # The real providers must be resolvable only when asked for (lazy import),
    # so the Space / stub never needs twilio or sendgrid installed.
    assert callable(send_mod._default_sms_provider)
    assert callable(send_mod._default_email_provider)


# --- missing-cred handling: fail loud, never leak the env var name ----------


def test_real_sms_without_creds_errors_without_leaking_key(monkeypatch):
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "FF_SEND_FROM"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SendError) as exc:
        # default provider path (no injected provider) + a pdf_url so we reach the
        # cred check rather than the missing-url guard
        send_estimate(
            channel="sms",
            recipient="+15551234567",
            rows=ROWS,
            mode="real",
            pdf_url="https://example.test/e/abc.pdf",
        )
    # the message must NOT disclose the raw env-var name
    assert "TWILIO_ACCOUNT_SID" not in str(exc.value)
    assert "not configured" in str(exc.value).lower()


def test_real_email_without_creds_errors_without_leaking_key(monkeypatch):
    for k in ("SENDGRID_API_KEY", "FF_SEND_FROM_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SendError) as exc:
        send_estimate(channel="email", recipient="jane@example.com", rows=ROWS, mode="real")
    assert "SENDGRID_API_KEY" not in str(exc.value)
    assert "not configured" in str(exc.value).lower()


def test_injected_provider_bypasses_cred_check(monkeypatch):
    # An injected provider must NOT require real creds (so tests/alt backends work).
    for k in ("SENDGRID_API_KEY", "FF_SEND_FROM_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    out = send_estimate(
        channel="email",
        recipient="jane@example.com",
        rows=ROWS,
        mode="real",
        email_provider=lambda **_: {"id": "EM_injected"},
    )
    assert out["status"] == "sent"
