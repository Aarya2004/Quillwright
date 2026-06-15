"""Tier 3 — QR phone-capture pairing channel.

A desktop session creates a pairing (gets a short code), shows it as a QR (tunnel URL
+ code). The phone opens the mobile capture page, sends a capture (photo path +/or
transcript), and it lands in the paired desktop session, which polls for it and forges.
In-process, demo-scoped — no DB, no auth.
"""

from quillwright import pairing


def setup_function():
    pairing.reset()


def test_create_pairing_returns_a_code():
    code = pairing.create()
    assert isinstance(code, str) and len(code) >= 4
    # distinct codes for distinct pairings
    assert pairing.create() != code


def test_poll_is_empty_until_a_capture_arrives():
    code = pairing.create()
    assert pairing.poll(code) is None  # nothing yet


def test_submit_then_poll_delivers_the_capture_once():
    code = pairing.create()
    pairing.submit(code, {"image_paths": ["/tmp/p.png"], "transcript": "replaced the capacitor"})
    got = pairing.poll(code)
    assert got["transcript"] == "replaced the capacitor"
    assert got["image_paths"] == ["/tmp/p.png"]
    # consumed: a second poll is empty again (so the desktop forges it exactly once)
    assert pairing.poll(code) is None


def test_submit_to_unknown_code_is_rejected():
    assert pairing.submit("nope", {"transcript": "x"}) is False


def test_is_valid_distinguishes_known_codes():
    code = pairing.create()
    assert pairing.is_valid(code) is True
    assert pairing.is_valid("bogus") is False
