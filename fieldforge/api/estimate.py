"""Thin adapter: HTTP request -> the tested agent backend -> JSON.

Holds no business logic; it only drives fieldforge.agent and shapes the result
for the frontend. Kept testable without a running server.
"""

import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from fieldforge.agent import build_agent
from fieldforge.catalog import Catalog
from fieldforge.models import Capture
from fieldforge.resolver import StubModel

CATALOG = Catalog.from_file("data/sample_catalog.json")

# Demo-only keyword -> observation map. Honest scaffolding until a real vision
# model is wired via the resolver; lets the transcript drive what's "seen".
_DEMO_VOCAB = {
    "capacitor": {"kind": "part", "text": "capacitor", "confidence": 0.9},
    "contactor": {"kind": "part", "text": "contactor", "confidence": 0.9},
    "refrigerant": {"kind": "part", "text": "refrigerant_r410a", "confidence": 0.85},
    "labor": {"kind": "part", "text": "labor", "confidence": 0.95},
    "unobtainium": {"kind": "part", "text": "unobtainium", "confidence": 0.7},
}


def _demo_perception(transcript: str) -> StubModel:
    """Transcript-aware stub: returns observations for keywords found in the note.

    Demo scaffolding only; a real vision model replaces this via the resolver.
    """
    low = transcript.lower()
    obs = [v for k, v in _DEMO_VOCAB.items() if k in low]
    if not obs:  # always produce something so the demo never dead-ends
        obs = [_DEMO_VOCAB["capacitor"], _DEMO_VOCAB["labor"]]
    return StubModel(responses=[json.dumps(obs)])


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


def forge_estimate(transcript: str, trade: str = "hvac") -> dict:
    """Run the agent once (non-streaming) and return trace + estimate as JSON."""
    agent = build_agent(_demo_perception(transcript), CATALOG, InMemorySaver())
    cap = Capture(image_paths=["demo.jpg"], transcript=transcript, trade_hint=trade or "Job")
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

    yield {
        "type": "estimate",
        "estimate": _estimate_payload(estimate) if estimate is not None else None,
    }
    _RUNS.pop(thread_id, None)


def forge_estimate_stream(transcript: str, trade: str = "hvac", thread_id: str = "ui"):
    """Run the agent, yielding each new trace step, then a pause OR the estimate.

    Events: {"type":"trace",...} per step, then {"type":"pause",...} or {"type":"estimate",...}.
    """
    agent = build_agent(_demo_perception(transcript), CATALOG, InMemorySaver())
    _RUNS[thread_id] = {"agent": agent, "emitted": 0}
    cap = Capture(image_paths=["demo.jpg"], transcript=transcript, trade_hint=trade or "Job")
    init = {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None}
    yield from _drive(agent, init, thread_id)


def resume_estimate_stream(value, thread_id: str = "ui"):
    """Resume a paused run with the human-supplied value; continue streaming to completion."""
    run = _RUNS.get(thread_id)
    if run is None:
        yield {"type": "estimate", "estimate": None}
        return
    yield from _drive(run["agent"], Command(resume=value), thread_id)
