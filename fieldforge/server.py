"""FieldForge frontend served by gradio.Server (a FastAPI app with Gradio's API engine).

Serves the bespoke web/ frontend at / and exposes the agent as endpoints. Glue only:
all business logic lives in fieldforge.agent and is adapted in fieldforge.api.
"""

import json
from pathlib import Path

from fastapi import Body
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from gradio import Server

from fieldforge.api.estimate import (
    forge_estimate,
    forge_estimate_stream,
    resume_estimate_stream,
)
from fieldforge.api.recalc import recalc_estimate
from fieldforge.api.upload import save_upload
from fieldforge.models import Estimate, LineItem
from fieldforge.pdf import estimate_to_pdf

WEB = Path(__file__).parent / "web"

app = Server()


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


@app.post("/api/recalc")
def api_recalc(payload: dict = Body(...)) -> dict:
    """Recompute totals from edited rows (server-authoritative math)."""
    return recalc_estimate(
        payload.get("rows", []),
        job_title=payload.get("job_title", "Job"),
        tax_rate=payload.get("tax_rate", 0.13),
    )


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
    path = "/tmp/fieldforge_estimate.pdf"
    estimate_to_pdf(est, path)
    return FileResponse(path, media_type="application/pdf", filename="estimate.pdf")


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


@app.get("/web/{path:path}")
def static_files(path: str):
    target = (WEB / path).resolve()
    if WEB.resolve() in target.parents and target.is_file():
        return FileResponse(target)
    return HTMLResponse("not found", status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7860)
