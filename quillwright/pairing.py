"""Phone-capture pairing channel (Tier 3).

The desktop creates a pairing → gets a short ``code`` → renders a QR of
``<public_base>/m/<code>``. The phone opens that mobile capture page, sends a capture
(photo server-path(s) +/or a transcript) to the pairing, and the desktop — which polls
``/api/pair/<code>`` — picks it up and forges live on screen.

In-process and demo-scoped: a dict of ``code -> pending capture``. The capture is
delivered exactly once (the desktop forges it a single time), then cleared. A durable /
multi-session transport is a post-hackathon swap behind this same tiny interface — the
same shape as ``pdf_links`` and the ``EstimateStore``.

Codes come from ``os.urandom`` (URL-safe, unguessable enough for a demo; not
``random``/wall-clock, so nothing here depends on the global RNG or the clock).
"""

import base64
import os

# code -> {"capture": <dict|None>}. Process-local; lives for the server's lifetime.
_PAIRINGS: dict[str, dict] = {}


def _new_code() -> str:
    """A short, URL-safe pairing code (6 chars, ~36 bits)."""
    return base64.urlsafe_b64encode(os.urandom(5)).decode().rstrip("=")[:6]


def create() -> str:
    """Open a new pairing and return its code (desktop side)."""
    code = _new_code()
    while code in _PAIRINGS:  # vanishingly unlikely; keep codes unique anyway
        code = _new_code()
    _PAIRINGS[code] = {"capture": None}
    return code


def is_valid(code: str) -> bool:
    """Whether ``code`` is a live pairing (the mobile page checks before capturing)."""
    return code in _PAIRINGS


def submit(code: str, capture: dict) -> bool:
    """Phone side: hand a capture to the paired desktop. False if the code is unknown."""
    if code not in _PAIRINGS:
        return False
    _PAIRINGS[code]["capture"] = capture
    return True


def poll(code: str) -> dict | None:
    """Desktop side: take the pending capture (delivered once), or None if none waiting."""
    pairing = _PAIRINGS.get(code)
    if not pairing or pairing["capture"] is None:
        return None
    capture = pairing["capture"]
    pairing["capture"] = None  # consume: the desktop forges it exactly once
    return capture


def reset() -> None:
    """Drop all pairings (tests)."""
    _PAIRINGS.clear()
