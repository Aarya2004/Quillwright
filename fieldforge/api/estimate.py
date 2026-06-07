"""Thin adapter: HTTP request -> the tested agent backend -> JSON.

Holds no business logic; it only drives fieldforge.agent and shapes the result
for the frontend. Kept testable without a running server.
"""

import json
import os

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from fieldforge.agent import build_agent
from fieldforge.catalog import Catalog
from fieldforge.memory import Memory
from fieldforge.models import Capture
from fieldforge.resolver import ModelResolver, StubModel

CATALOG = Catalog.from_file("data/sample_catalog.json")

# On-device memory of past jobs (private JSON file).
MEMORY_PATH = "/tmp/fieldforge_memory.json"
_MEMORY: Memory | None = None


def _memory() -> Memory:
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = Memory(MEMORY_PATH)
    return _MEMORY


def reset_memory() -> None:
    """Drop the in-process memory (re-reads MEMORY_PATH next use). For tests."""
    global _MEMORY
    _MEMORY = None

# FF_REAL_MODELS=1 uses real local models via Ollama; otherwise the demo stub.
REAL_MODELS = os.environ.get("FF_REAL_MODELS") == "1"

# Demo-only keyword -> observation map. Honest scaffolding for when there is no
# photo (transcript only) or real models are off; lets the note drive what's "seen".
_DEMO_VOCAB = {
    "capacitor": {"kind": "part", "text": "capacitor", "confidence": 0.9},
    "contactor": {"kind": "part", "text": "contactor", "confidence": 0.9},
    "refrigerant": {"kind": "part", "text": "refrigerant_r410a", "confidence": 0.85},
    "labor": {"kind": "part", "text": "labor", "confidence": 0.95},
    "unobtainium": {"kind": "part", "text": "unobtainium", "confidence": 0.7},
}


def _stub_perception(transcript: str) -> StubModel:
    """Transcript-aware stub used when there's no real photo or real models are off."""
    low = transcript.lower()
    obs = [v for k, v in _DEMO_VOCAB.items() if k in low]
    if not obs:  # always produce something so the demo never dead-ends
        obs = [_DEMO_VOCAB["capacitor"], _DEMO_VOCAB["labor"]]
    return StubModel(responses=[json.dumps(obs)])


def _perception(transcript: str, has_real_image: bool):
    """Real MiniCPM-V via Ollama when enabled AND a real photo exists; else the stub."""
    if REAL_MODELS and has_real_image:
        return ModelResolver(mode="private", backend="ollama").for_role("perception")
    return _stub_perception(transcript)


def _brain():
    """Real Ollama tool-calling brain when FF_REAL_MODELS=1; else None (deterministic path)."""
    if REAL_MODELS:
        return ModelResolver(mode="private", backend="ollama").for_role("brain")
    return None


def _estimate_payload(est) -> dict:
    return {
        "job_title": est.job_title,
        "line_items": [
            {
                "description": li.description,
                "quantity": li.quantity,
                "unit": li.unit,
                "rate": li.rate,
                "subtotal": li.subtotal,
            }
            for li in est.line_items
        ],
        "subtotal": est.subtotal,
        "tax_rate": est.tax_rate,
        "tax": est.tax,
        "total": est.total,
    }


def _trace_payload(trace) -> list[dict]:
    return [
        {"action": s.action, "model": s.model, "detail": s.detail, "status": s.status}
        for s in trace
    ]


def forge_estimate(
    transcript: str, trade: str = "hvac", image_paths: list[str] | None = None
) -> dict:
    """Run the agent once (non-streaming) and return trace + estimate as JSON."""
    images = [p for p in (image_paths or []) if os.path.isfile(p)]
    agent = build_agent(
        _perception(transcript, bool(images)), CATALOG, InMemorySaver(), brain_model=_brain()
    )
    cap = Capture(
        image_paths=images or ["demo.jpg"], transcript=transcript, trade_hint=trade or "Job"
    )
    out = agent.invoke(
        {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None},
        {"configurable": {"thread_id": "ui"}},
    )
    est = out.get("estimate")
    return {
        "trace": _trace_payload(out["trace"]),
        "estimate": _estimate_payload(est) if est is not None else None,
    }


# Active runs by thread_id, so a paused run can be resumed with the same agent + checkpointer.
# {thread_id: {"agent": compiled_graph, "emitted": int}}
_RUNS: dict[str, dict] = {}


def _step_event(step) -> dict:
    return {
        "type": "trace",
        "step": {
            "action": step.action,
            "model": step.model,
            "detail": step.detail,
            "status": step.status,
        },
    }


def _drive(agent, payload, thread_id: str):
    """Stream a run (or resume) to completion or the next Agent Pause.

    Yields trace events, then either a pause event (and stops) or an estimate event.
    """
    run = _RUNS[thread_id]
    cfg = {"configurable": {"thread_id": thread_id}}
    estimate = None
    for chunk in agent.stream(payload, cfg, stream_mode="updates"):
        # An interrupt surfaces under the "__interrupt__" key rather than a node update.
        if "__interrupt__" in chunk:
            intr = chunk["__interrupt__"][0]
            data = intr.value if hasattr(intr, "value") else intr
            yield {
                "type": "pause",
                "reason": data.get("reason", "Need your input"),
                "item": data.get("item", ""),
            }
            return
        for _node, update in chunk.items():
            trace = update.get("trace")
            if trace is not None:
                for step in trace[run["emitted"] :]:
                    yield _step_event(step)
                run["emitted"] = len(trace)
            if update.get("estimate") is not None:
                estimate = update["estimate"]

    # Record the finished job to Episodic memory.
    if estimate is not None:
        _memory().record_run(
            run.get("transcript", ""),
            [li.description for li in estimate.line_items],
        )

    yield {
        "type": "estimate",
        "estimate": _estimate_payload(estimate) if estimate is not None else None,
    }
    _RUNS.pop(thread_id, None)


def forge_estimate_stream(
    transcript: str,
    trade: str = "hvac",
    thread_id: str = "ui",
    image_paths: list[str] | None = None,
):
    """Run the agent, yielding each new trace step, then a pause OR the estimate.

    Events: {"type":"trace",...} per step, then {"type":"pause",...} or {"type":"estimate",...}.
    """
    images = [p for p in (image_paths or []) if os.path.isfile(p)]
    agent = build_agent(
        _perception(transcript, bool(images)), CATALOG, InMemorySaver(), brain_model=_brain()
    )
    _RUNS[thread_id] = {"agent": agent, "emitted": 0, "transcript": transcript}
    cap = Capture(
        image_paths=images or ["demo.jpg"], transcript=transcript, trade_hint=trade or "Job"
    )

    # Surface a recall of similar past jobs before estimating ("it learns").
    recalled = _recall_similar(transcript)
    if recalled:
        yield {
            "type": "trace",
            "step": {
                "action": "recall",
                "model": "memory",
                "detail": recalled,
                "status": "ok",
            },
        }

    init = {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None}
    yield from _drive(agent, init, thread_id)


def _recall_similar(transcript: str) -> str:
    """Find the most relevant past job; return a short human description, or ''."""
    for word in sorted(set(transcript.lower().split()), key=len, reverse=True):
        if len(word) < 4:
            continue
        runs = _memory().recall(word)
        if runs:
            items = ", ".join(runs[0]["line_items"][:3])
            return f"Similar past job: “{runs[0]['transcript']}” ({items})"
    return ""


def resume_estimate_stream(value, thread_id: str = "ui"):
    """Resume a paused run with the human-supplied value; continue streaming to completion."""
    run = _RUNS.get(thread_id)
    if run is None:
        yield {"type": "estimate", "estimate": None}
        return
    yield from _drive(run["agent"], Command(resume=value), thread_id)
