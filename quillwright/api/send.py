"""Finalize & Send (S10) — deliver a finished estimate to the customer by SMS or
email, with the same honest framing as the rest of Quillwright (ADR-0005).

Three-state resolution, mirroring ``FF_REAL_MODELS``:

  - **real**  — ``FF_SEND_ENABLED=1`` AND provider creds present: the message is
    actually transmitted (Twilio MMS / SendGrid email). This is the local/demo
    path; the providers are heavy, optional, third-party deps that are NOT in the
    Space requirements (lazy-imported, like the ``[embed]``/``[audio]`` extras).
  - **mock**  — default / public Space: the estimate is *drafted* and a confirmation
    is returned, but nothing is transmitted (``transmitted=False``,
    ``status="drafted"``). Twilio creds can't live on a public Space, so the Space
    never sends — and it says so honestly rather than claiming a send it didn't do.

Facts-from-Tools (ADR-0004) holds: send introduces no numbers. The PDF and the
summary line both come from ``recalc_estimate`` — the same server-authoritative
totals the customer-facing PDF/JSON already show.

MMS cannot attach a local file, so the SMS path needs a *public* PDF URL
(``pdf_url``) to hand Twilio as the media URL; the server mints one via the
tokenized ``/api/estimate_pdf/{token}`` route. Email attaches the PDF bytes inline,
so it needs no public URL.
"""

import os
from collections.abc import Callable

from quillwright.api.recalc import recalc_estimate

CHANNELS = ("sms", "email")


class SendError(Exception):
    """Raised when a send is refused (bad input) or a provider fails. Loud by
    design — we never silently downgrade a requested send to a no-op."""


def resolve_send_mode() -> str:
    """'real' only when explicitly enabled; 'mock' otherwise (the Space default)."""
    return "real" if os.environ.get("FF_SEND_ENABLED") == "1" else "mock"


# Required creds per channel — checked up front in real mode so a missing var
# fails loud with a clean message (never leaking the raw key name to the client).
_REQUIRED_ENV = {
    "sms": ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "FF_SEND_FROM"),
    "email": ("SENDGRID_API_KEY", "FF_SEND_FROM_EMAIL"),
}


def _require_provider_config(channel: str) -> None:
    """Raise a SendError naming the CHANNEL (not the missing env var) if real-mode
    creds are absent — so an HTTP 400 reply never discloses internal config keys."""
    missing = [k for k in _REQUIRED_ENV.get(channel, ()) if not os.environ.get(k)]
    if missing:
        raise SendError(
            f"{channel} send is not configured on this machine. "
            f"Set FF_SEND_ENABLED + the {channel} provider credentials to enable it."
        )


def estimate_summary_line(rows: list[dict], job_title: str, tax_rate: float) -> str:
    """A one-line, customer-safe summary with the authoritative total
    (Facts-from-Tools — the total comes from recalc, never from free text)."""
    est = recalc_estimate(rows, job_title=job_title, tax_rate=tax_rate)
    n = len(est["line_items"])
    items = "item" if n == 1 else "items"
    return f"{job_title}: {n} {items}, total ${est['total']:.2f}"


def _render_pdf_bytes(rows: list[dict], job_title: str, tax_rate: float) -> bytes:
    """Render the (edited) estimate to PDF bytes via the same path as /api/pdf."""
    import tempfile

    from quillwright.models import Estimate, LineItem
    from quillwright.pdf import estimate_to_pdf

    est = Estimate(
        job_title=job_title,
        line_items=[
            LineItem(
                description=str(r.get("description", "")),
                quantity=float(r.get("quantity", 1) or 0),
                unit=str(r.get("unit", "ea")),
                rate=float(r.get("rate", 0) or 0),
                price_source="user",
            )
            for r in rows
        ],
        tax_rate=tax_rate,
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        path = tmp.name
    estimate_to_pdf(est, path)
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    return data


def _validate(channel: str, recipient: str) -> str:
    if channel not in CHANNELS:
        raise SendError(f"Unknown channel {channel!r}; expected one of {CHANNELS}.")
    recipient = (recipient or "").strip()
    if not recipient:
        raise SendError("Recipient is required.")
    if channel == "email" and "@" not in recipient:
        raise SendError(f"{recipient!r} is not a valid email address.")
    return recipient


# --- default real providers (lazy third-party imports) ---------------------


def _default_sms_provider(*, recipient: str, body: str, media_url: str, summary: str) -> dict:
    """Send an MMS via Twilio. Imported lazily so neither the Space nor stub mode
    needs the ``twilio`` package installed. Creds from the standard Twilio env vars
    (+ ``FF_SEND_FROM`` for the sending number)."""
    from twilio.rest import Client  # noqa: PLC0415 — lazy: optional dep, not in the Space

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["FF_SEND_FROM"]
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        to=recipient,
        from_=from_number,
        body=body,
        media_url=[media_url] if media_url else None,
    )
    return {"sid": msg.sid}


def _default_email_provider(
    *, recipient: str, subject: str, body: str, pdf_bytes: bytes, filename: str
) -> dict:
    """Send an email with the PDF attached via SendGrid (Twilio's email product —
    keeps everything on the one Twilio account). Lazy-imported optional dep."""
    import base64  # noqa: PLC0415

    from sendgrid import SendGridAPIClient  # noqa: PLC0415 — lazy: optional dep
    from sendgrid.helpers.mail import (  # noqa: PLC0415
        Attachment,
        Disposition,
        FileContent,
        FileName,
        FileType,
        Mail,
    )

    message = Mail(
        from_email=os.environ["FF_SEND_FROM_EMAIL"],
        to_emails=recipient,
        subject=subject,
        plain_text_content=body,
    )
    message.attachment = Attachment(
        FileContent(base64.b64encode(pdf_bytes).decode()),
        FileName(filename),
        FileType("application/pdf"),
        Disposition("attachment"),
    )
    resp = SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(message)
    return {"id": resp.headers.get("X-Message-Id", "sendgrid-accepted")}


# --- the one entry point ---------------------------------------------------


def send_estimate(
    *,
    channel: str,
    recipient: str,
    rows: list[dict],
    job_title: str = "Estimate",
    tax_rate: float = 0.13,
    mode: str | None = None,
    pdf_url: str | None = None,
    sms_provider: Callable | None = None,
    email_provider: Callable | None = None,
) -> dict:
    """Send (or, in mock mode, draft) the finished estimate to ``recipient``.

    Returns a structured result the UI renders directly::

        {status: "sent"|"drafted", transmitted: bool, channel, recipient,
         summary, provider_id}

    Providers are injectable for tests; the defaults lazily import Twilio/SendGrid.
    """
    recipient = _validate(channel, recipient)
    mode = mode or resolve_send_mode()
    summary = estimate_summary_line(rows, job_title=job_title, tax_rate=tax_rate)

    base = {
        "channel": channel,
        "recipient": recipient,
        "summary": summary,
        "provider_id": None,
    }

    if mode != "real":
        # Space / disabled: draft only, transmit nothing — and say so.
        return {**base, "status": "drafted", "transmitted": False}

    body = f"Here is your estimate — {summary}. (AI-generated draft; review before accepting.)"
    try:
        if channel == "sms":
            if not pdf_url:
                raise SendError(
                    "SMS/MMS send requires a public pdf_url to attach (Twilio cannot "
                    "attach a local file). None was provided."
                )
            if sms_provider is None:  # only the real default provider needs creds
                _require_provider_config("sms")
            provider = sms_provider or _default_sms_provider
            result = provider(recipient=recipient, body=body, media_url=pdf_url, summary=summary)
            provider_id = result.get("sid")
        else:  # email
            if email_provider is None:
                _require_provider_config("email")
            provider = email_provider or _default_email_provider
            pdf_bytes = _render_pdf_bytes(rows, job_title=job_title, tax_rate=tax_rate)
            result = provider(
                recipient=recipient,
                subject=f"Your estimate — {job_title}",
                body=body,
                pdf_bytes=pdf_bytes,
                filename="estimate.pdf",
            )
            provider_id = result.get("id")
    except SendError:
        raise
    except Exception as exc:  # noqa: BLE001 — any provider failure becomes a loud SendError
        raise SendError(f"{channel} send failed: {exc}") from exc

    return {**base, "status": "sent", "transmitted": True, "provider_id": provider_id}
