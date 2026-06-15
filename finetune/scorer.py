"""Field-level scoring for the CORD line-item extraction fine-tune (ADR-0006).

Mirrors `quillwright/brain_eval.py`'s item-set F1 + quantity-accuracy approach, but
over a document's extracted line items rather than the brain's tool calls. The same
scorer runs the baseline (un-tuned MiniCPM-V) and the LoRA-tuned model so the gain is
apples-to-apples — that gain IS the 🎯 deliverable and the 📓 Field-Notes graph.

No GPU / model deps here on purpose: this is pure, deterministic, unit-testable
scoring. `eval.py` produces the model outputs; this file judges them.
"""

import json
import re


def parse_items(raw: str) -> list[dict]:
    """Best-effort parse of a model's JSON answer into a flat list of line items.

    The model is trained to emit CORD-shaped JSON; real generations drift (extra
    prose, trailing commas, a ```json fence). We extract the first JSON object and
    normalize CORD's `menu[].{nm,cnt,price}` into our `{name, qty, price}` rows.
    A parse failure returns [] — the model gets no credit, which is the honest score.
    """
    obj = _extract_json(raw)
    if obj is None:
        return []
    menu = obj.get("menu", obj.get("items", []))
    if isinstance(menu, dict):  # CORD sometimes encodes a single item as a dict
        menu = [menu]
    items = []
    for m in menu or []:
        if not isinstance(m, dict):
            continue
        items.append(
            {
                "name": _norm(m.get("nm", m.get("name", ""))),
                "qty": _to_num(m.get("cnt", m.get("qty", 1)), default=1),
                "price": _to_num(m.get("price", m.get("rate")), default=None),
            }
        )
    return [i for i in items if i["name"]]


def score(produced: list[dict], expected: list[dict], price_tol: float = 0.0) -> dict:
    """Item-name F1 + qty accuracy + price accuracy over name-matched items.

    `price_tol` is an absolute tolerance for the price match (0.0 = exact). Prices in
    CORD are strings with separators ("12,000") — `parse_items` already numericizes.
    """
    p = {i["name"]: i for i in produced}
    e = {i["name"]: i for i in expected}
    matched = set(p) & set(e)

    precision = len(matched) / len(p) if p else 0.0
    recall = len(matched) / len(e) if e else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    if matched:
        qty_ok = sum(1 for k in matched if p[k]["qty"] == e[k]["qty"])
        price_ok = sum(1 for k in matched if _price_match(p[k]["price"], e[k]["price"], price_tol))
        qty_accuracy = qty_ok / len(matched)
        price_accuracy = price_ok / len(matched)
    else:
        qty_accuracy = price_accuracy = 0.0

    return {
        "item_f1": round(f1, 3),
        "qty_accuracy": round(qty_accuracy, 3),
        "price_accuracy": round(price_accuracy, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }


def aggregate(per_case: list[dict]) -> dict:
    """Mean of each metric across cases — the headline baseline-vs-tuned numbers."""
    if not per_case:
        return {"item_f1": 0.0, "qty_accuracy": 0.0, "price_accuracy": 0.0, "n": 0}
    keys = ("item_f1", "qty_accuracy", "price_accuracy", "precision", "recall")
    out = {k: round(sum(c[k] for c in per_case) / len(per_case), 3) for k in keys}
    out["n"] = len(per_case)
    return out


# --- helpers -------------------------------------------------------------------


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    # Strip a markdown fence if present, then grab the outermost {...}.
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else raw
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _to_num(v, default):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return v
    cleaned = re.sub(r"[^\d.]", "", str(v))  # drop currency symbols + thousands seps
    try:
        num = float(cleaned)
        return int(num) if num.is_integer() else num
    except ValueError:
        return default


def _price_match(a, b, tol: float) -> bool:
    if a is None or b is None:
        return a is b  # both None = vacuously fine; one None = miss
    return abs(float(a) - float(b)) <= tol
