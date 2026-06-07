"""The LLM-driven brain loop: the model decides which items to add and when done.

Pure and Ollama-free for testing — takes any model with a .chat(messages, tools)
method (real OllamaModel or a scripted StubModel). Pricing/math stay in the
deterministic tools (Facts-from-Tools). A missing price is RETURNED as a pause
signal; the graph node turns that into a LangGraph interrupt.
"""

from fieldforge.brain_tools import BRAIN_TOOLS, dispatch
from fieldforge.catalog import Catalog
from fieldforge.models import LineItem, TraceStep

SYSTEM = (
    "You are a field-service estimator. You are given the parts and labor observed on a "
    "job. Add EACH distinct item to the estimate by calling add_priced_item(item) exactly "
    "once. Do not invent prices — the tool applies the catalog price. When every item has "
    "been added, call finish(). Use the exact item names given."
)


def run_brain(
    model,
    catalog: Catalog,
    observations_text: str,
    transcript: str,
    max_steps: int = 12,
):
    """Drive the model to build line items. Returns (line_items, trace, pause-or-None)."""
    line_items: list[LineItem] = []
    trace: list[TraceStep] = []
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": f"Observed items: {observations_text}\nTech's note: {transcript}",
        },
    ]

    for _ in range(max_steps):
        msg = model.chat(messages, BRAIN_TOOLS)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            break  # model produced plain text -> treat as done
        messages.append(msg)

        done = False
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {}) or {}
            result = dispatch(name, args, catalog)

            if result["status"] == "need_price":
                # Surface a pause for the graph to turn into an interrupt.
                return line_items, trace, {"item": result["item"]}
            if result["status"] == "done":
                done = True
                trace.append(TraceStep(action="finish", model="brain", detail="estimate complete"))
                break
            if result["status"] == "added":
                line_items.append(result["line_item"])
                trace.append(
                    TraceStep(
                        action="add_priced_item",
                        model="brain",
                        detail=f"{result['line_item'].description} "
                        f"-> {result['line_item'].rate}",
                    )
                )
                _tool_reply(messages, call, f"added {result['line_item'].description}")
            else:  # unknown tool -> corrective message (validate/repair)
                _tool_reply(messages, call, f"error: unknown tool '{name}'")

        if done:
            break

    return line_items, trace, None


def _tool_reply(messages: list[dict], call: dict, content: str) -> None:
    messages.append({"role": "tool", "content": content})
