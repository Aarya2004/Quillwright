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


@app.post("/api/forge_estimate_stream")
def api_forge_estimate_stream(payload: dict = Body(...)) -> StreamingResponse:
    transcript = payload.get("transcript", "")
    trade = payload.get("trade", "hvac")
    thread_id = payload.get("thread_id", "ui")
    return StreamingResponse(
        _sse(forge_estimate_stream(transcript, trade, thread_id)),
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
