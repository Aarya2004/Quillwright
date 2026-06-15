"""Inbound voice-call capture (S12) — call a number, the agent forges an estimate.

Flow (all reuse; no new business logic):

  1. Twilio routes an inbound call to ``POST /api/voice/incoming``. We answer with
     TwiML: a short greeting then ``<Record>``, which posts the ``RecordingUrl`` to
     ``POST /api/voice/recording`` when the caller hangs up.
  2. The recording webhook downloads the ``.wav``/``.mp3``, transcribes it (Audio role
     — Nemotron Omni on the Best Stack, Cohere Transcribe on the Private Stack, same
     ``transcribe_audio`` resolution as the mic button), forges an estimate, and saves
     it as a **DRAFT** under ``account_id="demo"`` (ADR-0013). It then ``<Say>``s the
     spoken total and ``<Gather>``s the caller's reply (Tier A — a conversation).
  3. Each reply hits ``POST /api/voice/refine`` with Twilio's own ``SpeechResult``
     transcript. "Done/no" → recalc, persist, text the PDF, end the call. Otherwise the
     spoken edit runs through the SAME ``chat_about_estimate`` ops (add / remove / change)
     the desktop chat uses, the new total is read back, and we ``<Gather>`` again. Per-call
     state is held under the Twilio ``CallSid`` (in-process, demo-scoped).

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

# Spoken voice for every <Say>. Amazon Polly Neural voices (rendered by Twilio at no extra
# cost beyond standard call rates) sound far more natural than the default. Override with
# FF_VOICE if you prefer another (e.g. Polly.Joanna-Neural, Polly.Stephen-Neural).
VOICE = os.environ.get("FF_VOICE", "Polly.Matthew-Neural")


def _say(message: str) -> str:
    """A <Say> with the configured natural voice."""
    return f'<Say voice="{escape(VOICE)}">{escape(message)}</Say>'


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
        + _say(
            "Welcome to Quillwright. After the beep, describe the job — the parts you "
            "used and the labor — then stop talking. I'll forge an estimate, read it back, "
            "and you can tell me what to change."
        )
        + f'<Record action="{escape(action)}" method="POST" maxLength="120" '
        'playBeep="true" timeout="5" />'
        + _say("I didn't catch a recording. Goodbye.")
        + "</Response>"
    )


def _say_response(message: str) -> str:
    """A bare spoken TwiML response (no recording)."""
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{_say(message)}</Response>'


# --- Conversational refine loop (Tier A): after forging, the agent reads the total and
#     keeps the call open, asking "anything else?" via <Gather input="speech">. Each reply
#     is a new /api/voice/refine turn that runs the SAME chat_about_estimate ops (add /
#     remove / change), so Facts-from-Tools holds — the agent only READS totals that recalc
#     produced. State is held per Twilio CallSid (in-process, demo-scoped, like pairing). ---

# call_sid -> {"rows": list[dict], "job_title": str, "tax_rate": float, "from_number": str}
_CALLS: dict[str, dict] = {}

# Phrases that end the conversation (caller says they're done).
_DONE_WORDS = (
    "no",
    "nope",
    "nothing",
    "that's it",
    "thats it",
    "done",
    "all set",
    "good",
    "send it",
)


def _call_state(call_sid: str) -> dict | None:
    return _CALLS.get(call_sid)


def reset_calls() -> None:
    """Drop all in-flight call + job state (tests)."""
    _CALLS.clear()
    _JOBS.clear()


def _is_done(speech: str) -> bool:
    s = (speech or "").strip().lower()
    if not s:
        return False
    return any(w in s for w in _DONE_WORDS)


def _ask_twiml(message: str, base_url: str | None = None) -> str:
    """Speak `message`, then <Gather> the caller's spoken reply to /api/voice/refine.
    If they stay silent, end politely (the Gather falls through to the closing Say)."""
    action = _action_url("/api/voice/refine", base_url)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>" + f'<Gather input="speech" method="POST" action="{escape(action)}" '
        'speechTimeout="auto" timeout="6">'
        + _say(message)
        + "</Gather>"
        + _say("I didn't catch that — I'll text you what I have. Goodbye.")
        + "</Response>"
    )


def _download_recording(url: str) -> str:
    """Fetch a Twilio RecordingUrl to a local temp file. Twilio serves the media at
    ``<url>.wav`` (a safer container for Omni than the browser's webm). Auth with the
    standard Twilio creds when present (recordings on a real account are protected)."""
    import tempfile
    import time

    import requests  # already a core dep

    media_url = url if url.endswith((".wav", ".mp3")) else f"{url}.wav"
    auth = None
    sid, token = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    if sid and token:
        auth = (sid, token)
    # Twilio posts the recording webhook the instant recording ends, but the media file
    # is often not encoded/available for a beat — an immediate GET 404s/403s. Retry a few
    # times with a short backoff so the not-ready race doesn't fail the call.
    last = None
    for attempt in range(5):
        resp = requests.get(media_url, auth=auth, timeout=20)
        if resp.status_code == 200 and resp.content:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(resp.content)
                return tmp.name
        last = resp
        if resp.status_code not in (404, 403, 401):
            break  # a different error won't fix itself by waiting
        time.sleep(1.5)
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"could not fetch recording at {media_url}")


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


def _rows_from_est(est: dict) -> list[dict]:
    """The editable rows (no subtotal/source) the chat ops + PDF renderer expect."""
    return [
        {
            "description": li["description"],
            "quantity": li["quantity"],
            "unit": li["unit"],
            "rate": li["rate"],
        }
        for li in est["line_items"]
    ]


def _summary(est: dict) -> str:
    n = len(est["line_items"])
    items = "item" if n == 1 else "items"
    return f"{n} {items}, totaling {est['total']:.2f} dollars"


def _text_pdf(*, rows, job_title, tax_rate, total, n, from_number, base, sms) -> bool:
    """Render + register the PDF and text it to the caller. Best-effort: returns True on
    a send, False on any failure (the draft is already saved either way)."""
    from quillwright.api.pdf_links import public_pdf_url, register_pdf
    from quillwright.api.send import _render_pdf_bytes

    if not from_number:
        return False
    try:
        pdf_bytes = _render_pdf_bytes(rows, job_title=job_title, tax_rate=tax_rate)
        token = register_pdf(pdf_bytes)
        media_url = public_pdf_url(token, base_url=base or "")
        items = "item" if n == 1 else "items"
        sms(
            to=from_number,
            body=(
                f"Your Quillwright estimate: {n} {items}, total ${total:.2f}. "
                "AI-generated draft — review before accepting."
            ),
            media_url=media_url,
        )
        return True
    except Exception:  # noqa: BLE001 — texting is best-effort; the draft is saved
        return False


def handle_recording(
    *,
    recording_url: str,
    from_number: str,
    call_sid: str = "default",
    download: Callable[[str], str] | None = None,
    transcribe: Callable[[str], dict] | None = None,
    sms: Callable | None = None,
    base_url: str | None = None,
) -> dict:
    """Transcribe the recording, forge + save a draft estimate, then ASK the caller if
    they want to change anything (the conversational refine loop — Tier A).

    Returns ``{"estimate": <dict|None>, "twiml": <spoken+gather>, "transcript": str}``.
    The PDF is NOT texted here — it goes out when the caller says they're done (see
    ``handle_refine``). Per-call state is held under ``call_sid``. Side-effects
    (download / SMS) are injectable so tests need no network or twilio.
    """
    from quillwright.api.estimate import estimate_store, forge_estimate
    from quillwright.api.transcribe import transcribe_audio

    download = download or _download_recording
    transcribe = transcribe or (lambda path: transcribe_audio(path))
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

    # Hold the rows for this call so refine turns edit the same estimate (forge_estimate
    # already auto-saved a DRAFT — ADR-0013; this is the same store the desktop reads).
    _CALLS[call_sid] = {
        "rows": _rows_from_est(est),
        "job_title": est["job_title"],
        "tax_rate": est["tax_rate"],
        "from_number": from_number,
    }
    estimate_store()  # touch so a misconfigured store surfaces in logs
    spoken = (
        f"Done. I forged an estimate with {_summary(est)}. "
        "Want to add or change anything, or should I text it to you?"
    )
    return {"estimate": est, "transcript": transcript, "twiml": _ask_twiml(spoken, base)}


# --- Async job pattern: forge+transcribe take ~tens of seconds (model load + brain),
#     far over Twilio's ~15s webhook timeout. So the recording webhook kicks the work off
#     on a background thread and returns a holding response immediately; Twilio is parked on
#     a <Pause>+<Redirect> to /api/voice/status, which polls until the job finishes. Each
#     webhook response stays well under the timeout. ---

# call_sid -> {"status": "working"|"done"|"error", "twiml": <ask TwiML once done>}
_JOBS: dict[str, dict] = {}


def _hold_twiml(message: str, base_url: str | None = None) -> str:
    """Speak a short status line, pause, then redirect to /api/voice/status to poll again."""
    action = _action_url("/api/voice/status", base_url)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>"
        + _say(message)
        + '<Pause length="3" />'
        + f'<Redirect method="POST">{escape(action)}</Redirect>'
        + "</Response>"
    )


def start_recording_job(
    *, recording_url: str, from_number: str, call_sid: str, base_url: str | None = None
) -> str:
    """Kick the forge off on a background thread; return holding TwiML immediately.
    The webhook never blocks on the slow work (model load + brain)."""
    import threading

    base = (base_url if base_url is not None else public_base_url()).rstrip("/")
    _JOBS[call_sid] = {"status": "working", "twiml": None}

    def _work():
        try:
            result = handle_recording(
                recording_url=recording_url,
                from_number=from_number,
                call_sid=call_sid,
                base_url=base,
            )
            _JOBS[call_sid] = {"status": "done", "twiml": result["twiml"]}
        except Exception as exc:  # noqa: BLE001 — surface as an error status, not a crash
            print(f"[quillwright] voice forge job failed: {exc}", flush=True)
            _JOBS[call_sid] = {
                "status": "error",
                "twiml": _say_response(
                    "Sorry, I couldn't build that estimate. Please call back and try again."
                ),
            }

    threading.Thread(target=_work, daemon=True).start()
    return _hold_twiml("Got it. I'm forging your estimate now — this takes a moment.", base)


def handle_status(*, call_sid: str, base_url: str | None = None) -> str:
    """Poll the background forge: still working → hold + redirect again; done → the ask
    (or error) TwiML the job produced. Unknown call → polite fallback."""
    base = (base_url if base_url is not None else public_base_url()).rstrip("/")
    job = _JOBS.get(call_sid)
    if job is None:
        return _say_response(
            "Sorry, I lost track of that estimate. Please call back to start again."
        )
    if job["status"] == "working":
        return _hold_twiml("Still working on it — just a few more seconds.", base)
    # done or error: hand back the prepared TwiML and clear the job marker.
    _JOBS.pop(call_sid, None)
    return job["twiml"]


def handle_refine(
    *,
    call_sid: str,
    speech_result: str,
    base_url: str | None = None,
    sms: Callable | None = None,
) -> dict:
    """One caller turn in the refine loop. If they're done, text the PDF and end; else
    apply the spoken edit through the SAME chat_about_estimate ops (Facts-from-Tools —
    the catalog owns every price) and ask again.

    Returns ``{"estimate": <dict|None>, "twiml": str}``. ``sms`` is injectable for tests.
    """
    from quillwright.api.chat import chat_about_estimate
    from quillwright.api.estimate import save_estimate_record

    sms = sms or _send_sms
    base = (base_url if base_url is not None else public_base_url()).rstrip("/")
    state = _CALLS.get(call_sid)
    if state is None:
        # Lost the thread (server restart / stale call) — fail politely, don't crash.
        return {
            "estimate": None,
            "twiml": _say_response(
                "Sorry, I lost track of that estimate. Please call back to start again."
            ),
        }

    rows = state["rows"]
    job_title, tax_rate = state["job_title"], state["tax_rate"]

    # Caller signalled they're finished → recalc to authoritative numbers, persist the
    # final draft, text the PDF, and end the call.
    if _is_done(speech_result):
        from quillwright.api.recalc import recalc_estimate

        est = recalc_estimate(rows, job_title=job_title, tax_rate=tax_rate)
        save_estimate_record(rows, job_title, tax_rate, thread=[])  # update the saved draft
        n = len(est["line_items"])
        sent = _text_pdf(
            rows=rows,
            job_title=job_title,
            tax_rate=tax_rate,
            total=est["total"],
            n=n,
            from_number=state.get("from_number", ""),
            base=base,
            sms=sms,
        )
        _CALLS.pop(call_sid, None)
        tail = (
            "I've texted you the PDF. It's a draft — review before sending it on. Goodbye."
            if sent
            else "It's saved as a draft on your dashboard. Goodbye."
        )
        return {"estimate": est, "twiml": _say_response(f"Got it. {tail}")}

    # Otherwise it's an edit: run it through the shared chat ops (catalog owns the price).
    out = chat_about_estimate(speech_result, rows, tax_rate=tax_rate)
    est = out["estimate"]
    state["rows"] = _rows_from_est(est)  # carry the edit forward to the next turn
    save_estimate_record(state["rows"], job_title, tax_rate, thread=[])  # keep the draft current
    spoken = f"{out['reply']} That's now {est['total']:.2f} dollars. Anything else?"
    return {"estimate": est, "twiml": _ask_twiml(spoken, base)}
