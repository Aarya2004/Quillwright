"""Transcribe a spoken voice note into the text the agent works from (ADR-0009).

Thin adapter over the Audio role: file path in, {transcript} out. The model is
injectable for tests; in production it resolves to Cohere Transcribe on-device.
"""

import os


def _resolve_audio():
    """The Audio role, by env: hosted Omni (Best Stack) when its Modal URL is
    configured, on-device STT when FF_REAL_MODELS=1, else None (typed note)."""
    from quillwright.resolver import modal_resolver_if_configured

    modal = modal_resolver_if_configured("audio")
    if modal is not None:
        return modal.for_role("audio")
    if os.environ.get("FF_REAL_MODELS") == "1":
        from quillwright.resolver import ModelResolver

        return ModelResolver(mode="private", backend="ollama").for_role("audio")
    return None


def transcribe_audio(path: str, model=None) -> dict:
    """Transcribe the audio at `path`. Returns {"transcript": str}.

    `model` is injectable (tests); otherwise resolves the Audio role. The transcript
    is whitespace-normalized so it drops cleanly into the note field.
    """
    asr = model if model is not None else _resolve_audio()
    if asr is None:
        return {"transcript": ""}
    text = (asr.transcribe(path) or "").strip()
    return {"transcript": text}
