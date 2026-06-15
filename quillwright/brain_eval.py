"""Score the brain against an eval set: did it pick the right items + quantities?

Used to measure brain accuracy and as the dataset for prompt optimization (GEPA).
"""

import json


def load_cases(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)["cases"]


def _by_desc(items: list[dict]) -> dict[str, float]:
    return {i["description"].strip().lower(): float(i.get("quantity", 1)) for i in items}


def score_case(produced: list[dict], expected: list[dict]) -> dict:
    """Item-set F1 + quantity accuracy over matched items."""
    p = _by_desc(produced)
    e = _by_desc(expected)
    matched = set(p) & set(e)
    precision = len(matched) / len(p) if p else 0.0
    recall = len(matched) / len(e) if e else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    if matched:
        correct_qty = sum(1 for k in matched if p[k] == e[k])
        qty_accuracy = correct_qty / len(matched)
    else:
        qty_accuracy = 0.0

    return {
        "item_f1": round(f1, 3),
        "qty_accuracy": round(qty_accuracy, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }
