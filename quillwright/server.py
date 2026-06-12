"""Quillwright frontend served by gradio.Server (a FastAPI app with Gradio's API engine).

Serves the bespoke web/ frontend at / and exposes the agent as endpoints. Glue only:
all business logic lives in quillwright.agent and is adapted in quillwright.api.
"""

import json
import os
from pathlib import Path

from fastapi import Body
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from gradio import Server

from quillwright.api.estimate import (
    forge_estimate,
    forge_estimate_stream,
    resume_estimate_stream,
)
from quillwright.api.chat import chat_about_estimate
from quillwright.api.document import parse_document_capture
from quillwright.api.export import estimate_to_json_payload
from quillwright.api.pages import dashboard_data, inventory_data, jobs_data
from quillwright.api.recalc import recalc_estimate
from quillwright.api.transcribe import transcribe_audio
from quillwright.api.translate import translate_estimate
from quillwright.api.upload import save_upload
from quillwright.models import Estimate, LineItem
from quillwright.pdf import estimate_to_pdf
from quillwright.resolver import ModelResolver

REAL_MODELS = os.environ.get("FF_REAL_MODELS") == "1"

WEB = Path(__file__).parent / "web"

app = Server()


def _announce_mode() -> None:
    """Print which model mode the server booted in — so 'is a model being hit?'
    is answerable at a glance instead of a silent guess."""
    from quillwright.resolver import OLLAMA_TAGS

    line = "=" * 60
    if not REAL_MODELS:
        print(f"\n{line}\n[quillwright] STUB MODE — no models hit (deterministic / keyword).")
        print("  Set FF_REAL_MODELS=1 to run the real local models via Ollama.")
        print(f"{line}\n", flush=True)
        return

    # Real mode: name the models and check Ollama is actually reachable.
    import requests

    tags = ", ".join(f"{role}={tag}" for role, tag in OLLAMA_TAGS.items())
    print(f"\n{line}\n[quillwright] REAL MODELS via Ollama — {tags}")
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        have = {m["name"].split(":")[0] for m in r.json().get("models", [])}
        missing = [t for t in OLLAMA_TAGS.values() if t.split(":")[0] not in have]
        if missing:
            print(f"  ⚠️  Ollama is up but these tags are NOT pulled: {missing}")
        else:
            print("  ✓ Ollama reachable; all role models are pulled.")
    except Exception as exc:  # noqa: BLE001 — startup banner, surface any failure
        print(f"  ⚠️  FF_REAL_MODELS=1 but Ollama is NOT reachable ({exc}).")
        print("     The brain will ERROR (not silently stub) on the first real call.")
    print(f"{line}\n", flush=True)


_announce_mode()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB / "index.html").read_text()


@app.post("/api/forge_estimate")
def api_forge_estimate(payload: dict = Body(...)) -> dict:
    return forge_estimate(payload.get("transcript", ""), payload.get("trade", "hvac"))


def _sse(events):
    for event in events:
        yield f"data: {json.dumps(event)}\n\n"


@app.post("/api/upload")
def api_upload(payload: dict = Body(...)) -> dict:
    """Save a base64 image; returns its server path for the next forge call."""
    path = save_upload(payload["data"], payload.get("filename", "photo.png"))
    return {"path": path}


@app.post("/api/parse_document")
def api_parse_document(payload: dict = Body(...)) -> dict:
    """Document Capture (ADR-0011): read a handed-over document (supplier quote,
    spec sheet) into Proposed Line Items the human confirms before they enter
    the estimate."""
    path = save_upload(payload["data"], payload.get("filename", "document.png"))
    return parse_document_capture(path)


@app.post("/api/transcribe")
def api_transcribe(payload: dict = Body(...)) -> dict:
    """Transcribe a base64 voice note into text (Cohere Transcribe, on-device)."""
    path = save_upload(payload["data"], payload.get("filename", "note.wav"))
    return transcribe_audio(path)


@app.post("/api/recalc")
def api_recalc(payload: dict = Body(...)) -> dict:
    """Recompute totals from edited rows (server-authoritative math)."""
    return recalc_estimate(
        payload.get("rows", []),
        job_title=payload.get("job_title", "Job"),
        tax_rate=payload.get("tax_rate", 0.13),
    )


@app.post("/api/translate")
def api_translate(payload: dict = Body(...)) -> dict:
    """Translate the customer-facing estimate copy into `language` (Cohere Aya)."""
    est = recalc_estimate(
        payload.get("rows", []),
        job_title=payload.get("job_title", "Job"),
        tax_rate=payload.get("tax_rate", 0.13),
    )
    language = payload.get("language", "English")
    if not language.lower().startswith("english"):
        from quillwright.resolver import modal_resolver_if_configured

        modal = modal_resolver_if_configured("multilingual")
        if modal is not None:  # Best-Stack Aya on Modal
            est = translate_estimate(est, language, modal.for_role("multilingual"))
        elif REAL_MODELS:  # Private-Stack Aya via local Ollama
            model = ModelResolver(mode="private", backend="ollama").for_role("multilingual")
            est = translate_estimate(est, language, model)
    return est


@app.post("/api/pdf")
def api_pdf(payload: dict = Body(...)) -> FileResponse:
    """Render the (possibly edited) estimate to a PDF and return it."""
    est = Estimate(
        job_title=payload.get("job_title", "Estimate"),
        line_items=[
            LineItem(
                description=str(r.get("description", "")),
                quantity=float(r.get("quantity", 1) or 0),
                unit=str(r.get("unit", "ea")),
                rate=float(r.get("rate", 0) or 0),
                price_source="user",
            )
            for r in payload.get("rows", [])
        ],
        tax_rate=payload.get("tax_rate", 0.13),
    )
    path = "/tmp/quillwright_estimate.pdf"
    estimate_to_pdf(est, path)
    return FileResponse(path, media_type="application/pdf", filename="estimate.pdf")


@app.post("/api/export_json")
def api_export_json(payload: dict = Body(...)) -> dict:
    """Machine-readable JSON of the (edited) estimate — the 'no lock-in' export."""
    return estimate_to_json_payload(
        payload.get("rows", []),
        job_title=payload.get("job_title", "Estimate"),
        tax_rate=payload.get("tax_rate", 0.13),
    )


@app.post("/api/chat")
def api_chat(payload: dict = Body(...)) -> dict:
    """Conversational refinement of the current estimate (Facts-from-Tools holds)."""
    return chat_about_estimate(
        payload.get("message", ""),
        payload.get("rows", []),
        tax_rate=payload.get("tax_rate", 0.13),
    )


@app.post("/api/forge_estimate_stream")
def api_forge_estimate_stream(payload: dict = Body(...)) -> StreamingResponse:
    transcript = payload.get("transcript", "")
    trade = payload.get("trade", "hvac")
    thread_id = payload.get("thread_id", "ui")
    image_paths = payload.get("image_paths", [])
    return StreamingResponse(
        _sse(forge_estimate_stream(transcript, trade, thread_id, image_paths)),
        media_type="text/event-stream",
    )


@app.post("/api/resume_estimate_stream")
def api_resume_estimate_stream(payload: dict = Body(...)) -> StreamingResponse:
    value = payload.get("value")
    thread_id = payload.get("thread_id", "ui")
    return StreamingResponse(
        _sse(resume_estimate_stream(value, thread_id)),
        media_type="text/event-stream",
    )


# --- Secondary pages (ADR-0010): demoable-first read-models over real data. ---


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> str:
    return (WEB / "dashboard.html").read_text()


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page() -> str:
    return (WEB / "jobs.html").read_text()


@app.get("/inventory", response_class=HTMLResponse)
def inventory_page() -> str:
    return (WEB / "inventory.html").read_text()


@app.get("/api/dashboard")
def api_dashboard() -> dict:
    """KPIs + recent jobs aggregated over the real on-device memory store."""
    return dashboard_data()


@app.get("/api/jobs")
def api_jobs() -> dict:
    """Past Runs from the real memory store, newest first."""
    return jobs_data()


@app.get("/api/inventory")
def api_inventory() -> dict:
    """Read-only stock view over the seeded inventory JSON (low-stock reads are real)."""
    return inventory_data()


@app.get("/web/{path:path}")
def static_files(path: str):
    target = (WEB / path).resolve()
    if WEB.resolve() in target.parents and target.is_file():
        return FileResponse(target)
    return HTMLResponse("not found", status_code=404)


if __name__ == "__main__":
    import uvicorn

    # Bind 0.0.0.0 in containers/Spaces (reachable from outside); honor $PORT (HF Spaces
    # set it). Defaults keep local dev on 127.0.0.1:7860 unchanged.
    host = os.environ.get("FF_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host=host, port=port)
