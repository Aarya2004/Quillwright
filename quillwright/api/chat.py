"""Conversational refinement of the current estimate — talk to the Digital
Apprentice about the draft ("add a contactor", "change labor to 3 hours",
"drop the refrigerant").

It is the SAME supervised agent, just conversational. Two paths share ONE set of
operations (add/remove/change), so Facts-from-Tools (ADR-0004) holds either way —
the catalog supplies every price; neither the keywords nor the model invent a number:

- FF_REAL_MODELS=1  -> Nemotron (tool-calling) picks the operation + item, the
  deterministic ops below execute it (catalog owns the price).
- otherwise         -> a keyword intent parser picks the operation (so the hosted
  stub Space + tests run with zero models).

Totals are always recomputed server-authoritatively via recalc_estimate.
"""

import os
import re

from quillwright.api.recalc import recalc_estimate
from quillwright.catalog import Catalog

CATALOG = Catalog.from_file("data/sample_catalog.json")
REAL_MODELS = os.environ.get("FF_REAL_MODELS") == "1"

_NUM_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "half": 0.5,
    "both": 2,
    "pair": 2,
}


def _to_qty(text: str) -> float | None:
    """First number-like token in `text` -> a quantity, or None."""
    m = re.search(r"\d+(?:\.\d+)?", text)
    if m:
        return float(m.group())
    for word, val in _NUM_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return val
    return None


def _finish(rows: list[dict], tax_rate: float, reply: str, needs_price: bool = False) -> dict:
    est = recalc_estimate(rows, job_title="Estimate", tax_rate=tax_rate)
    return {"estimate": est, "reply": reply, "needs_price": needs_price}


def _find_row(rows: list[dict], text: str) -> int | None:
    """Index of the row whose description best matches words in `text`."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    best_i, best_overlap = None, 0
    for i, r in enumerate(rows):
        desc_words = set(re.findall(r"[a-z0-9]+", r["description"].lower()))
        overlap = len(words & desc_words)
        if overlap > best_overlap:
            best_i, best_overlap = i, overlap
    return best_i if best_overlap else None


# --- The shared operations. Each mutates `rows` in place and returns a reply dict
#     fragment {"reply": str, "needs_price"?: bool}. Both paths call these, so the
#     catalog-owns-the-price guarantee lives in exactly one place. ---


def _op_add(rows: list[dict], item: str, quantity: float | None) -> dict:
    priced = CATALOG.lookup(item)
    if not priced:
        return {
            "reply": (
                "I couldn't find that part in the catalog, so I won't guess a price. "
                "Add it manually with a rate and I'll keep the math straight."
            ),
            "needs_price": True,
        }
    qty = quantity if (quantity and quantity > 0) else 1
    rows.append(
        {
            "description": priced["description"],
            "quantity": qty,
            "unit": priced["unit"],
            "rate": priced["rate"],  # Facts-from-Tools: catalog price, never the model.
        }
    )
    return {
        "reply": f"Added {qty:g} × {priced['description']} at ${priced['rate']:.2f} from the catalog."
    }


def _op_remove(rows: list[dict], item: str) -> dict:
    i = _find_row(rows, item)
    if i is None:
        return {"reply": "I couldn't tell which line to remove — which item did you mean?"}
    removed = rows.pop(i)
    return {"reply": f"Removed {removed['description']}. Updated the total for you."}


def _op_change_qty(rows: list[dict], item: str, quantity: float | None) -> dict:
    i = _find_row(rows, item)
    if i is None or quantity is None:
        return {
            "reply": "Tell me which item and the new quantity — e.g. “change labor to 2 hours”."
        }
    rows[i]["quantity"] = quantity
    return {"reply": f"Set {rows[i]['description']} to {quantity:g}. Recalculated the total."}


# --- LLM tool surface: the model only PICKS the operation + item (+ quantity);
#     execution + pricing stay in the deterministic ops above. ---

CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add a part or labor to the estimate. The catalog price is applied automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "part or labor name"},
                    "quantity": {"type": "number", "description": "units/hours (default 1)"},
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": "Remove a line item from the estimate.",
            "parameters": {
                "type": "object",
                "properties": {"item": {"type": "string", "description": "the item to remove"}},
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_quantity",
            "description": "Change the quantity (units or hours) of an existing line item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "the item to adjust"},
                    "quantity": {"type": "number", "description": "the new quantity"},
                },
                "required": ["item", "quantity"],
            },
        },
    },
]

_CHAT_SYSTEM = (
    "You are a field-service estimator's assistant. The user wants to refine the current "
    "estimate. Decide the single edit they're asking for and call ONE tool: add_item, "
    "remove_item, or change_quantity. Never invent prices — the tool applies the catalog price. "
    "If they're only asking a question (not requesting an edit), answer briefly in plain text "
    "and call no tool."
)


def _apply_model_call(name: str, args: dict, rows: list[dict]) -> dict:
    item = str(args.get("item", "")).strip()
    qty = args.get("quantity")
    qty = float(qty) if isinstance(qty, (int, float)) else _to_qty(item)
    if name == "add_item":
        return _op_add(rows, item, qty)
    if name == "remove_item":
        return _op_remove(rows, item)
    if name == "change_quantity":
        return _op_change_qty(rows, item, qty)
    return {"reply": "I'm not sure how to do that — try add, remove, or change a quantity."}


def _model_chat(message: str, rows: list[dict], tax_rate: float, model) -> dict:
    """Let the tool-calling model pick the edit; execute it through the shared ops."""
    rows_summary = (
        ", ".join(f"{r['description']} (qty {r['quantity']:g})" for r in rows) or "(empty)"
    )
    messages = [
        {"role": "system", "content": _CHAT_SYSTEM},
        {"role": "user", "content": f"Current estimate: {rows_summary}\nRequest: {message}"},
    ]
    msg = model.chat(messages, CHAT_TOOLS)
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        # No edit — the model answered a question. Estimate stays untouched.
        text = (msg.get("content") or "").strip()
        return _finish(rows, tax_rate, text or "Let me know what you'd like to change.")

    fn = tool_calls[0].get("function", {})
    result = _apply_model_call(fn.get("name", ""), fn.get("arguments", {}) or {}, rows)
    return _finish(rows, tax_rate, result["reply"], needs_price=result.get("needs_price", False))


def _keyword_chat(message: str, rows: list[dict], tax_rate: float) -> dict:
    """Zero-model fallback: a keyword intent parser drives the same shared ops."""
    msg = message.strip().lower()
    if not msg:
        return _finish(
            rows, tax_rate, "Tell me what to change — add a part, drop one, or adjust a quantity."
        )

    if re.search(r"\b(remove|delete|drop|take off|get rid of)\b", msg):
        result = _op_remove(rows, msg)
        return _finish(rows, tax_rate, result["reply"])

    if re.search(r"\b(change|set|make|update)\b", msg) or re.search(
        r"\bto\b.*\b(hour|hr|unit|lb|pound)", msg
    ):
        i = _find_row(rows, msg)
        qty = _to_qty(msg)
        if i is not None and qty is not None:
            result = _op_change_qty(rows, rows[i]["description"], qty)
            return _finish(rows, tax_rate, result["reply"])

    if re.search(r"\b(add|include|put in|need|another|more)\b", msg):
        result = _op_add(rows, msg, _to_qty(msg))
        return _finish(
            rows, tax_rate, result["reply"], needs_price=result.get("needs_price", False)
        )

    return _finish(
        rows,
        tax_rate,
        "I can add a part, remove one, or change a quantity — e.g. “add a contactor” or "
        "“change labor to 2 hours”. What would you like to adjust?",
    )


def _resolve_brain():
    """Real tool-calling model when enabled (local Ollama or hosted Modal); else None."""
    if REAL_MODELS or os.environ.get("FF_BACKEND") == "modal":
        from quillwright.resolver import brain_resolver

        return brain_resolver().for_role("brain")
    return None


def chat_about_estimate(message: str, rows: list[dict], tax_rate: float = 0.13, model=None) -> dict:
    """Apply a conversational edit to the estimate. Returns {estimate, reply, needs_price}.

    `model` is injectable for tests; in production it's resolved from FF_REAL_MODELS.
    """
    rows = [dict(r) for r in rows]  # don't mutate the caller's list
    brain = model if model is not None else _resolve_brain()
    if brain is not None:
        return _model_chat(message, rows, tax_rate, brain)
    return _keyword_chat(message, rows, tax_rate)
