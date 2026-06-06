"""Thin adapter: HTTP request -> the tested agent backend -> JSON.

Holds no business logic; it only drives fieldforge.agent and shapes the result
for the frontend. Kept testable without a running server.
"""

from langgraph.checkpoint.memory import InMemorySaver

from fieldforge.agent import build_agent
from fieldforge.catalog import Catalog
from fieldforge.models import Capture
from fieldforge.resolver import StubModel

CATALOG = Catalog.from_file("data/sample_catalog.json")


def _demo_perception() -> StubModel:
    """Stub perception for the core build; swapped for a real model via the resolver later."""
    return StubModel(
        responses=[
            '[{"kind":"part","text":"capacitor","confidence":0.9},'
            ' {"kind":"part","text":"labor","confidence":0.9}]'
        ]
    )


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
    agent = build_agent(_demo_perception(), CATALOG, InMemorySaver())
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


def forge_estimate_stream(transcript: str, trade: str = "hvac"):
    """Run the agent, yielding each new trace step as it happens, then the estimate.

    Events: {"type":"trace","step":{...}} per new step, then {"type":"estimate","estimate":{...}}.
    """
    agent = build_agent(_demo_perception(), CATALOG, InMemorySaver())
    cap = Capture(image_paths=["demo.jpg"], transcript=transcript, trade_hint=trade or "Job")
    init = {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None}
    cfg = {"configurable": {"thread_id": "ui"}}

    emitted = 0  # how many trace steps already sent
    estimate = None
    for chunk in agent.stream(init, cfg, stream_mode="updates"):
        for _node, update in chunk.items():
            trace = update.get("trace")
            if trace is not None:
                for step in trace[emitted:]:
                    yield {
                        "type": "trace",
                        "step": {
                            "action": step.action,
                            "model": step.model,
                            "detail": step.detail,
                            "status": step.status,
                        },
                    }
                emitted = len(trace)
            if update.get("estimate") is not None:
                estimate = update["estimate"]

    yield {
        "type": "estimate",
        "estimate": _estimate_payload(estimate) if estimate is not None else None,
    }
