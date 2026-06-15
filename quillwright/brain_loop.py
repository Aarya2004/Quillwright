"""The LLM-driven brain loop: the model decides which items to add and when done.

Pure and Ollama-free for testing — takes any model with a .chat(messages, tools)
method (real OllamaModel or a scripted StubModel). Pricing/math stay in the
deterministic tools (Facts-from-Tools). A missing price is RETURNED as a pause
signal; the graph node turns that into a LangGraph interrupt.
"""

from quillwright.brain_tools import BRAIN_TOOLS, dispatch
from quillwright.catalog import Catalog
from quillwright.models import LineItem, TraceStep

SYSTEM = (
    "You are a field-service estimator. You are given a tech's note about a job. Add EACH "
    "distinct part and the labor to the estimate by calling add_priced_item(item, quantity). "
    "Rules:\n"
    "- Call add_priced_item ONCE per distinct item. Do not repeat an item.\n"
    "- quantity = how many units or hours. Read it from the note: 'two hours'/'2 hrs' -> 2, "
    "'both'/'a pair' -> 2, '4 pounds' -> 4. If no count is stated, use 1.\n"
    "- Labor is an item too: add it with the number of hours as the quantity.\n"
    "- Never invent prices — the tool applies the catalog price.\n"
    "- When every part and the labor have been added, call finish().\n"
    "Examples:\n"
    "Note: 'replaced the capacitor and did 2 hours labor' -> add_priced_item('capacitor', 1), "
    "add_priced_item('labor', 2), finish()\n"
    "Note: 'replaced both contactors' -> add_priced_item('contactor', 2), finish()\n"
    "Note: 'added 4 lbs refrigerant' -> add_priced_item('refrigerant', 4), finish()"
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
    # The actual model name (e.g. "nemotron-3-nano:4b" or "StubModel") so the trace
    # truthfully shows which model answered — no guessing whether a model was hit.
    brain_name = getattr(model, "name", "brain")
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
                trace.append(
                    TraceStep(action="finish", model=brain_name, detail="estimate complete")
                )
                break
            if result["status"] == "added":
                line_items.append(result["line_item"])
                li = result["line_item"]
                trace.append(
                    TraceStep(
                        action="add_priced_item",
                        model=brain_name,
                        detail=f"{li.quantity:g} x {li.description} -> {li.subtotal}",
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
