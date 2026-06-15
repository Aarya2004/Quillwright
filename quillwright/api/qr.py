"""QR code as inline SVG for the phone-capture pairing (Tier 3).

``segno`` is a tiny, pure-Python, zero-dependency QR encoder — but it's only needed on
the local/tunnel demo path (the hosted Space has no tunnel to pair against), so it lives
in the optional ``[capture]`` extra and is lazy-imported, the same pattern as the
``[send]``/``[embed]``/``[audio]`` extras (kept OUT of the Space requirements, ADR-0005).

If segno isn't installed we degrade honestly: an empty string, and the UI shows the
pairing link as scannable text instead of claiming a QR it can't render.
"""

import io


def qr_svg(data: str, scale: int = 5) -> str:
    """Return an inline SVG QR for ``data``, or '' if the encoder isn't installed."""
    try:
        import segno  # noqa: PLC0415 — lazy: optional [capture] dep, not in the Space
    except ImportError:
        return ""
    buf = io.BytesIO()
    # xmldecl=False so the SVG embeds cleanly inline in the desktop HTML (no <?xml?> prolog).
    segno.make(data, error="m").save(buf, kind="svg", scale=scale, border=2, xmldecl=False)
    return buf.getvalue().decode()
