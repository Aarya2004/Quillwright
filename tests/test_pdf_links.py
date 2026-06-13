"""Tests for the tokenized PDF link registry (used to give Twilio MMS a public
URL for the estimate PDF — SMS can't attach a local file)."""

from quillwright.api.pdf_links import (
    get_pdf,
    public_pdf_url,
    register_pdf,
)


def test_register_then_get_round_trips():
    token = register_pdf(b"%PDF-fake-bytes")
    assert get_pdf(token) == b"%PDF-fake-bytes"


def test_token_is_deterministic_for_same_bytes():
    # Same content -> same token (content hash); no wall-clock / randomness.
    a = register_pdf(b"%PDF-identical")
    b = register_pdf(b"%PDF-identical")
    assert a == b


def test_different_bytes_get_different_tokens():
    assert register_pdf(b"%PDF-one") != register_pdf(b"%PDF-two")


def test_get_unknown_token_returns_none():
    assert get_pdf("not-a-real-token") is None


def test_public_pdf_url_builds_from_base():
    token = "abc123"
    url = public_pdf_url(token, base_url="https://example.test")
    assert url == "https://example.test/api/estimate_pdf/abc123"


def test_public_pdf_url_strips_trailing_slash():
    url = public_pdf_url("t", base_url="https://example.test/")
    assert url == "https://example.test/api/estimate_pdf/t"


def test_token_is_url_safe():
    token = register_pdf(b"%PDF-anything")
    # no slashes / plus / chars that would break a path segment
    assert "/" not in token and "+" not in token and "=" not in token
