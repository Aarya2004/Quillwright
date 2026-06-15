"""Quillwright tool endpoints for a voice agent (ElevenLabs Conversational AI).

ElevenLabs owns the phone call, the speech-to-text, the dialogue, and the (great) TTS.
Quillwright stays the source of truth: the agent calls these small JSON tools to forge
and refine an estimate, and every customer-facing number comes from a tool response —
never the agent's free speech (Facts-from-Tools, ADR-0004).

Each tool takes a ``session_id`` (the agent passes its conversation id) so refinement
turns edit the same estimate. State is in-process and demo-scoped, like the pairing store
and the Twilio call state — a durable backend is a swap behind this same interface.

Tools:
  - ``forge(session_id, description)``    → itemized estimate + total from a job description
  - ``edit(session_id, request)``         → add / remove / change a line (catalog-priced)
  - ``lookup_price(item)``                → a single catalog price (read-only)
  - ``text_estimate(session_id, to)``     → SMS the estimate PDF to the caller
"""

# session_id -> {"rows": list[dict], "job_title": str, "tax_rate": float}
_SESSIONS: dict[str, dict] = {}

_JOB_TITLE = "Phone estimate"
_TAX_RATE = 0.13


def reset_sessions() -> None:
    """Drop all voice-agent session state (tests)."""
    _SESSIONS.clear()


def _session(session_id: str) -> dict:
    return _SESSIONS.setdefault(
        session_id, {"rows": [], "job_title": _JOB_TITLE, "tax_rate": _TAX_RATE}
    )


def _rows_from_est(est: dict) -> list[dict]:
    return [
        {
            "description": li["description"],
            "quantity": li["quantity"],
            "unit": li["unit"],
            "rate": li["rate"],
        }
        for li in est["line_items"]
    ]


def _spoken_items(est: dict) -> list[dict]:
    """A compact, speech-friendly view of the lines (no internal fields)."""
    return [
        {"description": li["description"], "quantity": li["quantity"], "rate": li["rate"]}
        for li in est["line_items"]
    ]


def forge(session_id: str, description: str) -> dict:
    """Forge an estimate from a spoken job description; store it on the session."""
    from quillwright.api.estimate import forge_estimate

    forged = forge_estimate(description or "", trade="hvac")
    est = forged.get("estimate")
    if est is None or not est.get("line_items"):
        return {
            "ok": False,
            "message": "I couldn't build an estimate from that. "
            "Try naming the parts and the labor.",
        }
    sess = _session(session_id)
    sess["rows"] = _rows_from_est(est)
    return {
        "ok": True,
        "items": _spoken_items(est),
        "item_count": len(est["line_items"]),
        "total": round(est["total"], 2),
    }


def edit(session_id: str, request: str) -> dict:
    """Apply a spoken edit (add / remove / change) to the session's estimate. The catalog
    owns every price (Facts-from-Tools); returns the assistant's reply + the new total."""
    from quillwright.api.chat import chat_about_estimate

    sess = _session(session_id)
    out = chat_about_estimate(request or "", sess["rows"], tax_rate=sess["tax_rate"])
    est = out["estimate"]
    sess["rows"] = _rows_from_est(est)
    return {
        "ok": True,
        "reply": out["reply"],
        "items": _spoken_items(est),
        "item_count": len(est["line_items"]),
        "total": round(est["total"], 2),
    }


def lookup_price(item: str) -> dict:
    """A single catalog price (read-only) so the agent can answer 'how much is X?'."""
    from quillwright.api.estimate import CATALOG

    hit = CATALOG.lookup(item or "")
    if not hit:
        return {"found": False, "item": item}
    return {
        "found": True,
        "description": hit["description"],
        "rate": hit["rate"],
        "unit": hit["unit"],
    }


def text_estimate(session_id: str, to: str, base_url: str | None = None, sms=None) -> dict:
    """SMS the estimate PDF to the caller. Reuses the S10 send path + tokenized PDF link.
    ``sms`` is injectable for tests; otherwise the real Twilio MMS provider is used."""
    import os

    from quillwright.api.estimate import save_estimate_record
    from quillwright.api.pdf_links import public_pdf_url, register_pdf
    from quillwright.api.recalc import recalc_estimate
    from quillwright.api.send import _default_sms_provider, _render_pdf_bytes

    sess = _session(session_id)
    rows, job_title, tax_rate = sess["rows"], sess["job_title"], sess["tax_rate"]
    if not rows:
        return {"ok": False, "message": "There's no estimate to send yet."}
    if not to:
        return {"ok": False, "message": "I need a phone number to text it to."}

    base = (base_url if base_url is not None else os.environ.get("FF_PUBLIC_BASE_URL", "")).rstrip(
        "/"
    )
    est = recalc_estimate(rows, job_title=job_title, tax_rate=tax_rate)
    save_estimate_record(rows, job_title, tax_rate, thread=[])  # persist the draft (ADR-0013)
    n = len(est["line_items"])
    send = sms or _default_sms_provider
    try:
        pdf_bytes = _render_pdf_bytes(rows, job_title=job_title, tax_rate=tax_rate)
        token = register_pdf(pdf_bytes)
        media_url = public_pdf_url(token, base_url=base or "")
        send(
            recipient=to,
            body=(
                f"Your Quillwright estimate: {n} item{'s' if n != 1 else ''}, "
                f"total ${est['total']:.2f}. AI-generated draft — review before accepting."
            ),
            media_url=media_url,
            summary="",
        )
        return {"ok": True, "sent": True, "total": round(est["total"], 2)}
    except Exception as exc:  # noqa: BLE001 — report a clean failure to the agent
        return {"ok": False, "sent": False, "message": f"Couldn't text it: {exc}"}
