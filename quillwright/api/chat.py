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
from quillwright.thread import append_turn, compact

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


def _to_dollar_amount(text: str) -> float | None:
    """A user-stated price -> float, or None. Matches an explicit `$30` OR a spoken
    `30 dollars` / `30 bucks` (voice transcripts have no `$`). A bare number with no
    money cue is NOT treated as a price (it stays a possible quantity)."""
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:dollars?|bucks)\b", text)
    return float(m.group(1)) if m else None


def _finish(
    rows: list[dict],
    tax_rate: float,
    reply: str,
    needs_price: bool = False,
    changed: str | None = None,
    thread: list[dict] | None = None,
    message: str = "",
    op: str = "",
    pending: dict | None = None,
) -> dict:
    est = recalc_estimate(rows, job_title="Estimate", tax_rate=tax_rate)
    # `changed` names the line whose rate just changed, so the UI can pulse that cell.
    # The Refinement Thread (ADR-0013) records the human message + a dollar-free op,
    # so resuming can never feed a stale number back to the model (Facts-from-Tools).
    new_thread = append_turn(thread or [], message=message, op=op) if op else (thread or [])
    # `pending` carries a rate change awaiting a scope answer ("this estimate"/"the catalog")
    # to the next turn — the user's stated number, deferred one turn, not the model's.
    return {
        "estimate": est,
        "reply": reply,
        "needs_price": needs_price,
        "changed": changed,
        "thread": new_thread,
        "pending": pending,
    }


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
            "op": "tried to add an unknown part",
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
        "reply": (
            f"Done — added {qty:g} × {priced['description']} at the catalog rate of "
            f"${priced['rate']:.2f}. I've updated the total."
        ),
        "op": f"added {priced['description']}",
    }


def _op_remove(rows: list[dict], item: str) -> dict:
    i = _find_row(rows, item)
    if i is None:
        return {
            "reply": "I couldn't tell which line to remove — which item did you mean?",
            "op": "tried to remove an unmatched item",
        }
    removed = rows.pop(i)
    return {
        "reply": f"Got it — took {removed['description']} off the estimate and recalculated the total.",
        "op": f"removed {removed['description']}",
    }


def _op_change_qty(rows: list[dict], item: str, quantity: float | None) -> dict:
    i = _find_row(rows, item)
    if i is None or quantity is None:
        return {
            "reply": "Tell me which item and the new quantity — e.g. “change labor to 2 hours”.",
            "op": "asked to change a quantity (unclear)",
        }
    rows[i]["quantity"] = quantity
    return {
        "reply": f"Sure — {rows[i]['description']} is now {quantity:g}. Total's updated.",
        "op": f"set {rows[i]['description']} to {quantity:g}",
    }


def _op_change_rate(rows: list[dict], item: str, rate: float | None, scope: str | None) -> dict:
    """Set a line's rate to a USER-SUPPLIED number (Facts-from-Tools: the number is
    the user's, never the model's). Asks estimate-vs-catalog before applying when the
    scope is unspecified.

    scope="estimate" -> this row only (price_source="user").
    scope="catalog"  -> also writes the in-session catalog so later adds use it.
    """
    i = _find_row(rows, item)
    if i is None or rate is None:
        return {
            "reply": "Tell me which line and the exact rate — e.g. “set the capacitor rate to $30”.",
            "op": "asked to change a rate (unclear)",
        }
    if scope not in ("estimate", "catalog"):
        # Numbers are user-confirmed, but we still ask WHERE it applies before changing.
        # Stash the change as `pending` so the next turn's scope answer can apply it.
        return {
            "reply": (
                f"Should ${rate:.2f} for {rows[i]['description']} apply to just this "
                "estimate, or update the catalog price for future jobs too? "
                "Say “this estimate” or “the catalog”."
            ),
            "op": "asked where a rate applies",
            "pending": {"item": rows[i]["description"], "rate": rate},
        }
    rows[i]["rate"] = rate
    rows[i]["price_source"] = "user"  # a human-confirmed price, not catalog/computed
    desc = rows[i]["description"]
    if scope == "catalog":
        # Update the in-session catalog so a later add of the same part picks it up.
        existing = CATALOG.lookup(desc) or {}
        CATALOG.add(
            key=existing.get("key", desc.lower().replace(" ", "_")),
            description=desc,
            unit=rows[i].get("unit", existing.get("unit", "ea")),
            rate=rate,
        )
        where = "this estimate and the catalog"
    else:
        where = "this estimate"
    return {
        "reply": f"Done — {desc} is now ${rate:.2f} for {where}, and the total's updated.",
        "changed": desc,
        # Op is dollar-free by construction (Facts-from-Tools holds in the thread too).
        "op": f"set the rate for {desc} ({where})",
    }


def _answer_about_estimate(rows: list[dict], tax_rate: float) -> str:
    """A spoken-friendly answer to 'what's the total / what's on it' — every number from
    recalc (Facts-from-Tools), never free-generated."""
    est = recalc_estimate(rows, job_title="Estimate", tax_rate=tax_rate)
    items = est["line_items"]
    if not items:
        return "The estimate is empty right now — tell me what to add."
    n = len(items)
    listed = ", ".join(f"{li['quantity']:g} {li['description'].lower()}" for li in items)
    return (
        f"You've got {n} item{'s' if n != 1 else ''}: {listed}. "
        f"The total comes to ${est['total']:.2f}."
    )


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
    {
        "type": "function",
        "function": {
            "name": "change_rate",
            "description": (
                "Set the rate (unit price) of an existing line item to a price the USER "
                "EXPLICITLY STATED. Only call this when the user gave an exact number — "
                "never choose or estimate a price yourself. `scope` says where it applies: "
                "'estimate' (this estimate only) or 'catalog' (also the catalog, for future "
                "jobs). If the user did not say which, OMIT scope — the assistant will ask."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "the item whose rate to set"},
                    "rate": {
                        "type": "number",
                        "description": "the exact unit price the user stated (e.g. 30 for $30)",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["estimate", "catalog"],
                        "description": "'estimate' = this estimate only; 'catalog' = also "
                        "the catalog. Omit if the user didn't specify.",
                    },
                },
                "required": ["item", "rate"],
            },
        },
    },
]

_CHAT_SYSTEM = (
    "You are a field-service estimator's assistant. The user wants to refine the current "
    "estimate. Decide the single edit they're asking for and call ONE tool: add_item, "
    "remove_item, change_quantity, or change_rate. "
    "ALWAYS prefer calling a tool over replying in plain text. The user's intent is often "
    "phrased conversationally or buried mid-sentence — extract it and act. Map the request "
    "to the closest tool even when the wording is indirect. Examples:\n"
    "- 'it actually took more than one capacitor, could you make it 2?' → change_quantity("
    "item='capacitor', quantity=2)\n"
    "- 'I ended up using two contactors' → change_quantity(item='contactor', quantity=2)\n"
    "- 'throw in a refrigerant too' / 'I also needed refrigerant' → add_item(item='refrigerant')\n"
    "- 'scrap the labor line' / 'we didn't end up doing labor' → remove_item(item='labor')\n"
    "- 'bump labor to three hours' → change_quantity(item='labor', quantity=3)\n"
    "Never invent prices. For add_item the catalog supplies the price. "
    "change_rate is ONLY for a price the user STATED EXACTLY (e.g. “make it $30”): pass that "
    "exact number as `rate`. If the user asks to change a price WITHOUT giving a number "
    "(e.g. “make it cheaper”), do NOT call change_rate and do NOT pick a number — answer in "
    "plain text asking what rate they want. When you do call change_rate, include `scope` "
    "ONLY if the user said whether it applies to just this estimate or the catalog; if they "
    "did not say, omit `scope` and the assistant will ask. "
    "Only reply in plain text WITHOUT a tool when they're genuinely just asking a question "
    "(e.g. 'what's the total?') or when you truly cannot map the request to any edit."
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
    if name == "change_rate":
        rate = args.get("rate")
        rate = float(rate) if isinstance(rate, (int, float)) else None
        scope = args.get("scope")
        return _op_change_rate(rows, item, rate, scope)
    return {"reply": "I'm not sure how to do that — try add, remove, or change a quantity or rate."}


def _model_chat(message: str, rows: list[dict], tax_rate: float, model, thread: list[dict]) -> dict:
    """Let the tool-calling model pick the edit; execute it through the shared ops.

    The compacted, sanitized thread (ops only, no dollars — ADR-0013) is replayed for
    reference resolution ("make *it* 2 hours"); numbers always come from the current rows.
    """
    rows_summary = (
        ", ".join(f"{r['description']} (qty {r['quantity']:g})" for r in rows) or "(empty)"
    )
    history = compact(thread)
    user = (
        f"Earlier edits:\n{history}\n\n" if history else ""
    ) + f"Current estimate: {rows_summary}\nRequest: {message}"
    messages = [
        {"role": "system", "content": _CHAT_SYSTEM},
        {"role": "user", "content": user},
    ]
    msg = model.chat(messages, CHAT_TOOLS)
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        # No edit — the model answered a question. Estimate stays untouched. If it's a
        # total/contents question, answer it deterministically (the number must come from
        # recalc, never the model — Facts-from-Tools), else relay the model's plain text.
        text = (msg.get("content") or "").strip()
        if re.search(
            r"\b(total|how much|what'?s on|what is on|whats on|breakdown)\b", message.lower()
        ):
            text = _answer_about_estimate(rows, tax_rate)
        return _finish(
            rows,
            tax_rate,
            text or "Let me know what you'd like to change.",
            thread=thread,
            message=message,
            op="asked a question",
        )

    fn = tool_calls[0].get("function", {})
    result = _apply_model_call(fn.get("name", ""), fn.get("arguments", {}) or {}, rows)
    return _finish(
        rows,
        tax_rate,
        result["reply"],
        needs_price=result.get("needs_price", False),
        changed=result.get("changed"),
        thread=thread,
        message=message,
        op=result.get("op", ""),
        pending=result.get("pending"),
    )


def _keyword_chat(message: str, rows: list[dict], tax_rate: float, thread: list[dict]) -> dict:
    """Zero-model fallback: a keyword intent parser drives the same shared ops."""
    msg = message.strip().lower()
    if not msg:
        return _finish(
            rows,
            tax_rate,
            "Tell me what to change — add a part, drop one, or adjust a quantity.",
            thread=thread,
        )

    # A read-only question about the estimate ("what's the total", "what's on it",
    # "how much is it") — answer it instead of falling through to generic help. Checked
    # before the edit verbs, but only when no edit verb is present so "add ..." still adds.
    is_question = re.search(r"\b(total|how much|what'?s on|what is on|whats on|breakdown)\b", msg)
    has_edit_verb = re.search(r"\b(add|remove|delete|drop|set|change|make|update|include)\b", msg)
    if is_question and not has_edit_verb:
        return _finish(
            rows,
            tax_rate,
            _answer_about_estimate(rows, tax_rate),
            thread=thread,
            message=message,
            op="asked about the estimate",
        )

    if re.search(r"\b(remove|delete|drop|take off|get rid of)\b", msg):
        result = _op_remove(rows, msg)
        return _finish(
            rows, tax_rate, result["reply"], thread=thread, message=message, op=result.get("op", "")
        )

    # An explicit dollar amount ("set the capacitor rate to $30") is a user-confirmed
    # rate change. Checked BEFORE the quantity branch so the "$30" isn't read as a qty.
    # The keyword path can't hold a follow-up turn, so it takes the conservative
    # estimate-only scope (the model path is the one that asks catalog-vs-estimate).
    # _to_dollar_amount only returns a value when a money cue is present ($, "dollars",
    # "bucks"), so its non-None result is itself the signal this is a rate, not a quantity.
    rate_amount = _to_dollar_amount(msg)
    if rate_amount is not None:
        i = _find_row(rows, msg)
        if i is not None:
            result = _op_change_rate(rows, rows[i]["description"], rate_amount, scope="estimate")
            return _finish(
                rows,
                tax_rate,
                result["reply"],
                changed=result.get("changed"),
                thread=thread,
                message=message,
                op=result.get("op", ""),
            )

    if re.search(r"\b(change|set|make|update)\b", msg) or re.search(
        r"\bto\b.*\b(hour|hr|unit|lb|pound)", msg
    ):
        i = _find_row(rows, msg)
        qty = _to_qty(msg)
        if i is not None and qty is not None:
            result = _op_change_qty(rows, rows[i]["description"], qty)
            return _finish(
                rows,
                tax_rate,
                result["reply"],
                thread=thread,
                message=message,
                op=result.get("op", ""),
            )

    if re.search(r"\b(add|include|put in|need|another|more)\b", msg):
        result = _op_add(rows, msg, _to_qty(msg))
        return _finish(
            rows,
            tax_rate,
            result["reply"],
            needs_price=result.get("needs_price", False),
            thread=thread,
            message=message,
            op=result.get("op", ""),
        )

    return _finish(
        rows,
        tax_rate,
        "I can add a part, remove one, or change a quantity — e.g. “add a contactor” or "
        "“change labor to 2 hours”. What would you like to adjust?",
        thread=thread,
    )


def _resolve_brain():
    """Real tool-calling model when enabled (local Ollama or hosted Modal); else None."""
    if REAL_MODELS or os.environ.get("FF_BACKEND") == "modal":
        from quillwright.resolver import brain_resolver

        return brain_resolver().for_role("brain")
    return None


def _scope_answer(message: str) -> str | None:
    """Map a scope reply to 'estimate'/'catalog', or None if it isn't one."""
    m = message.strip().lower()
    if re.search(r"\bcatalog\b|\bboth\b|future job", m):
        return "catalog"
    if re.search(r"\b(this|just this|estimate only|only this|here|this one)\b", m):
        return "estimate"
    return None


def chat_about_estimate(
    message: str, rows: list[dict], tax_rate: float = 0.13, model=None, thread=None, pending=None
) -> dict:
    """Apply a conversational edit to the estimate. Returns
    {estimate, reply, needs_price, changed, thread, pending}.

    `model` is injectable for tests; in production it's resolved from FF_REAL_MODELS.
    `thread` is the Refinement Thread (ADR-0013): sanitized, dollar-free history.
    `pending` carries a rate change awaiting a scope answer from the previous turn — if it
    is set and this message answers "this estimate"/"the catalog", apply it directly (no
    model), so the two-turn rate change doesn't lose context.
    """
    rows = [dict(r) for r in rows]  # don't mutate the caller's list
    thread = list(thread or [])

    # Resolve a pending rate change first: "the catalog" / "this estimate" applies the
    # number the user stated last turn (Facts-from-Tools — it's the user's, just deferred).
    if pending and pending.get("item") and pending.get("rate") is not None:
        scope = _scope_answer(message)
        if scope is not None:
            result = _op_change_rate(rows, pending["item"], float(pending["rate"]), scope=scope)
            return _finish(
                rows,
                tax_rate,
                result["reply"],
                changed=result.get("changed"),
                thread=thread,
                message=message,
                op=result.get("op", ""),
            )
        # Not a scope answer — fall through to normal handling, dropping the pending change.

    brain = model if model is not None else _resolve_brain()
    if brain is not None:
        try:
            return _model_chat(message, rows, tax_rate, brain, thread)
        except Exception as exc:  # noqa: BLE001 — model down (e.g. Ollama 500): degrade
            # Fall back to the deterministic keyword path so a chat turn never 500s the UI.
            print(f"[quillwright] chat brain failed ({exc}); using keyword fallback.")
    return _keyword_chat(message, rows, tax_rate, thread)
