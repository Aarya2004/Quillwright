"""Conversational refinement of the current estimate — talk to the Digital
Apprentice about the draft ("add a contactor", "change labor to 3 hours",
"drop the refrigerant").

It is the SAME supervised agent, just conversational: every price still comes
from the catalog via lookup_price (Facts-from-Tools, ADR-0004) — the chat never
invents a number. Totals are recomputed server-authoritatively after each edit.

This deterministic intent layer runs with zero models (so the hosted stub Space
works and tests need no Ollama). When FF_REAL_MODELS=1, the same edits can be
driven by the tool-calling brain over the same dispatch surface (wiring point
noted below) — the contract (rows in, rows + reply out) is identical.
"""

import re

from quillwright.api.recalc import recalc_estimate
from quillwright.catalog import Catalog

CATALOG = Catalog.from_file("data/sample_catalog.json")

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


def _find_row(rows: list[dict], message: str) -> int | None:
    """Index of the row whose description best matches words in the message."""
    words = set(re.findall(r"[a-z0-9]+", message.lower()))
    best_i, best_overlap = None, 0
    for i, r in enumerate(rows):
        desc_words = set(re.findall(r"[a-z0-9]+", r["description"].lower()))
        overlap = len(words & desc_words)
        if overlap > best_overlap:
            best_i, best_overlap = i, overlap
    return best_i if best_overlap else None


def chat_about_estimate(message: str, rows: list[dict], tax_rate: float = 0.13) -> dict:
    """Apply a conversational edit to the estimate. Returns {estimate, reply, needs_price}."""
    rows = [dict(r) for r in rows]  # don't mutate caller's list
    msg = message.strip().lower()
    if not msg:
        return _finish(
            rows, tax_rate, "Tell me what to change — add a part, drop one, or adjust a quantity."
        )

    # --- remove ---
    if re.search(r"\b(remove|delete|drop|take off|get rid of)\b", msg):
        i = _find_row(rows, msg)
        if i is None:
            return _finish(
                rows, tax_rate, "I couldn't tell which line to remove — which item did you mean?"
            )
        removed = rows.pop(i)
        return _finish(
            rows, tax_rate, f"Removed {removed['description']}. Updated the total for you."
        )

    # --- change quantity ---
    if re.search(r"\b(change|set|make|update)\b", msg) or re.search(
        r"\bto\b.*\b(hour|hr|unit|lb|pound)", msg
    ):
        i = _find_row(rows, msg)
        qty = _to_qty(msg)
        if i is not None and qty is not None:
            rows[i]["quantity"] = qty
            return _finish(
                rows, tax_rate, f"Set {rows[i]['description']} to {qty:g}. Recalculated the total."
            )

    # --- add ---
    if re.search(r"\b(add|include|put in|need|another|more)\b", msg):
        priced = CATALOG.lookup(msg)
        if not priced:
            return _finish(
                rows,
                tax_rate,
                "I couldn't find that part in the catalog, so I won't guess a price. "
                "Add it manually with a rate and I'll keep the math straight.",
                needs_price=True,
            )
        qty = _to_qty(msg) or 1
        rows.append(
            {
                "description": priced["description"],
                "quantity": qty,
                "unit": priced["unit"],
                "rate": priced["rate"],
            }
        )
        return _finish(
            rows,
            tax_rate,
            f"Added {qty:g} × {priced['description']} at ${priced['rate']:.2f} from the catalog.",
        )

    # --- fallback: didn't match an intent ---
    return _finish(
        rows,
        tax_rate,
        "I can add a part, remove one, or change a quantity — e.g. “add a contactor” or "
        "“change labor to 2 hours”. What would you like to adjust?",
    )
