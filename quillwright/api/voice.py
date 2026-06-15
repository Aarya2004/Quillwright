"""Inbound voice-call capture (S12) — call a number, the agent forges an estimate.

Flow (all reuse; no new business logic):

  1. Twilio routes an inbound call to ``POST /api/voice/incoming``. We answer with
     TwiML: a short greeting then ``<Record>``, which posts the ``RecordingUrl`` to
     ``POST /api/voice/recording`` when the caller hangs up.
  2. The recording webhook downloads the ``.wav``/``.mp3``, transcribes it (Audio role
     — Nemotron Omni on the Best Stack, Cohere Transcribe on the Private Stack, same
     ``transcribe_audio`` resolution as the mic button), forges an estimate, and saves
     it as a **DRAFT** under ``account_id="demo"`` (ADR-0013). It then ``<Say>``s the
     spoken total back on the call and texts the caller the PDF by SMS.

Honesty (ADR-0004, ADR-0013): the estimate's numbers all come from the catalog +
``recalc`` (Facts-from-Tools); the call produces a draft a human approves later. On a
call the agent runs to completion without the interactive Agent Pause (``forge_estimate``
is the non-streaming path — a missing price is auto-flagged in the trace, never blocks).

The public base URL is read from ``FF_PUBLIC_BASE_URL`` (the ngrok/cloudflared tunnel),
so Twilio can fetch the recording-action URL and the PDF media URL. SMS reuses the S10
``send_estimate`` SMS provider and the tokenized PDF registry — nothing new is sent.
"""

import os
from collections.abc import Callable
from xml.sax.saxutils import escape


def public_base_url() -> str:
    """The tunnel's public base URL (FF_PUBLIC_BASE_URL), trailing slash stripped, or ''."""
    return os.environ.get("FF_PUBLIC_BASE_URL", "").rstrip("/")


def _action_url(path: str, base_url: str | None = None) -> str:
    """An absolute URL on the public base when known, else a relative path (Twilio
    resolves a relative <Record action> against the request host)."""
    base = (base_url if base_url is not None else public_base_url()).rstrip("/")
    return f"{base}{path}" if base else path


def greeting_twiml(base_url: str | None = None) -> str:
    """Answer an inbound call: greet, then record the caller's job description.

    ``<Record>`` posts the RecordingUrl to /api/voice/recording on hang-up (or after the
    silence timeout). ``playBeep`` cues the caller; ``maxLength`` caps a runaway call.
    """
    action = _action_url("/api/voice/recording", base_url)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>"
        "<Say>Welcome to Quillwright. After the beep, describe the job — the parts you "
        "used and the labor — then hang up. I'll forge an estimate and text it to you.</Say>"
        f'<Record action="{escape(action)}" method="POST" maxLength="120" '
        'playBeep="true" timeout="5" />'
        "<Say>I didn't catch a recording. Goodbye.</Say>"
        "</Response>"
    )


def _say_response(message: str) -> str:
    """A bare spoken TwiML response (no recording)."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<Response><Say>{escape(message)}</Say></Response>'
    )


def _download_recording(url: str) -> str:
    """Fetch a Twilio RecordingUrl to a local temp file. Twilio serves the media at
    ``<url>.wav`` (a safer container for Omni than the browser's webm). Auth with the
    standard Twilio creds when present (recordings on a real account are protected)."""
    import tempfile

    import requests  # already a core dep

    media_url = url if url.endswith((".wav", ".mp3")) else f"{url}.wav"
    auth = None
    sid, token = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    if sid and token:
        auth = (sid, token)
    resp = requests.get(media_url, auth=auth, timeout=30)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(resp.content)
        return tmp.name


def _send_sms(*, to: str, body: str, media_url: str) -> dict:
    """Text the caller via Twilio (lazy import — same optional [send] dep as S10)."""
    from twilio.rest import Client  # noqa: PLC0415 — lazy: optional dep, not in the Space

    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    msg = client.messages.create(
        to=to,
        from_=os.environ["FF_SEND_FROM"],
        body=body,
        media_url=[media_url] if media_url else None,
    )
    return {"sid": msg.sid}


def handle_recording(
    *,
    recording_url: str,
    from_number: str,
    download: Callable[[str], str] | None = None,
    transcribe: Callable[[str], dict] | None = None,
    sms: Callable | None = None,
    base_url: str | None = None,
) -> dict:
    """Transcribe the recording, forge + save a draft estimate, and text it.

    Returns ``{"estimate": <dict|None>, "twiml": <spoken summary>, "transcript": str}``.
    Side-effects (download / SMS) are injectable so tests need no network or twilio.
    """
    from quillwright.api.estimate import estimate_store, forge_estimate
    from quillwright.api.pdf_links import public_pdf_url, register_pdf
    from quillwright.api.send import _render_pdf_bytes
    from quillwright.api.transcribe import transcribe_audio

    download = download or _download_recording
    transcribe = transcribe or (lambda path: transcribe_audio(path))
    sms = sms or _send_sms
    base = (base_url if base_url is not None else public_base_url()).rstrip("/")

    path = download(recording_url)
    transcript = (transcribe(path) or {}).get("transcript", "").strip()
    if not transcript:
        return {
            "estimate": None,
            "transcript": "",
            "twiml": _say_response(
                "Sorry, I couldn't make out the job from that recording. "
                "Please call back and describe the parts and labor after the beep."
            ),
        }

    forged = forge_estimate(transcript, trade="hvac")
    est = forged.get("estimate")
    if est is None or not est.get("line_items"):
        return {
            "estimate": None,
            "transcript": transcript,
            "twiml": _say_response(
                "I heard the job but couldn't build an estimate from it. "
                "I've made a note — please call back with the parts and labor."
            ),
        }

    # Save as a DRAFT (the call never finalizes; a human approves later — ADR-0013).
    # forge_estimate already auto-saved it; this is the same store the desktop reads.
    n = len(est["line_items"])
    items = "item" if n == 1 else "items"
    spoken = (
        f"Done. I forged an estimate with {n} {items}, totaling "
        f"{est['total']:.2f} dollars. It's a draft — I'll text it to you to review and approve."
    )

    # Text the PDF (reuse S10's renderer + tokenized public link). Best-effort: a send
    # failure must not break the spoken reply (the draft is already saved on the desktop).
    if from_number:
        try:
            rows = [
                {
                    "description": li["description"],
                    "quantity": li["quantity"],
                    "unit": li["unit"],
                    "rate": li["rate"],
                }
                for li in est["line_items"]
            ]
            pdf_bytes = _render_pdf_bytes(
                rows, job_title=est["job_title"], tax_rate=est["tax_rate"]
            )
            token = register_pdf(pdf_bytes)
            media_url = public_pdf_url(token, base_url=base or "")
            sms(
                to=from_number,
                body=(
                    f"Your Quillwright estimate: {n} {items}, total ${est['total']:.2f}. "
                    "AI-generated draft — review before accepting."
                ),
                media_url=media_url,
            )
        except Exception:  # noqa: BLE001 — texting is best-effort; the draft is saved
            spoken += " I couldn't text it just now, but it's saved on your dashboard."

    # Touch estimate_store so a misconfigured store surfaces in logs (no-op otherwise).
    estimate_store()
    return {"estimate": est, "transcript": transcript, "twiml": _say_response(spoken)}
