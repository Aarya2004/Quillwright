"""Tokenized PDF link registry (S10).

Twilio MMS attaches media by **URL**, not by file upload — so to text a customer
their estimate PDF we need a public URL Twilio can GET. This registry holds rendered
PDF bytes in process, keyed by a content-hash token, and the server exposes them at
``/api/estimate_pdf/{token}``.

The token is a content hash (deterministic, offline-friendly — no uuid/wall-clock,
matching the rest of the codebase's id scheme), URL-safe, and unguessable enough for
a demo (the bytes are an AI-draft estimate, not a secret). In-process only: it lives
for the life of the server, which is all the MMS fetch needs. A durable/expiring
store is a post-hackathon swap behind this same tiny interface.
"""

import hashlib

# token -> pdf bytes. Process-local; fine for the local demo path.
_PDFS: dict[str, bytes] = {}


def register_pdf(pdf_bytes: bytes) -> str:
    """Store the bytes under a content-hash token and return the token."""
    token = hashlib.sha256(pdf_bytes).hexdigest()[:16]
    _PDFS[token] = pdf_bytes
    return token


def get_pdf(token: str) -> bytes | None:
    """Return the bytes for a token, or None if unknown."""
    return _PDFS.get(token)


def public_pdf_url(token: str, base_url: str) -> str:
    """Build the public URL Twilio fetches the PDF from."""
    return f"{base_url.rstrip('/')}/api/estimate_pdf/{token}"


def reset() -> None:
    """Drop all registered PDFs (tests)."""
    _PDFS.clear()
