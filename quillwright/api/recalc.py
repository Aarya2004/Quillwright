"""Recompute an estimate from user-edited rows. Math goes through the Estimate
model's computed fields (qty*rate, tax, total) — Facts-from-Tools holds even for
human edits; the UI never computes its own authoritative totals.
"""

from quillwright.models import Estimate, LineItem

# Provenances a client row may carry through a recalc. "document" marks a confirmed
# Document Capture price (ADR-0011); anything unrecognized falls back to "user" so
# arbitrary client strings never enter the model.
_CLIENT_SOURCES = {"document", "user", "catalog", "computed"}


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _source(value) -> str:
    return value if value in _CLIENT_SOURCES else "user"


def recalc_estimate(rows: list[dict], job_title: str, tax_rate: float) -> dict:
    items = [
        LineItem(
            description=str(r.get("description", "")),
            quantity=_num(r.get("quantity", 1)),
            unit=str(r.get("unit", "ea")),
            rate=_num(r.get("rate", 0)),
            price_source=_source(r.get("price_source")),
        )
        for r in rows
    ]
    est = Estimate(job_title=job_title, line_items=items, tax_rate=tax_rate)
    return {
        "job_title": est.job_title,
        "line_items": [
            {
                "description": li.description,
                "quantity": li.quantity,
                "unit": li.unit,
                "rate": li.rate,
                "subtotal": li.subtotal,
                "price_source": li.price_source,
            }
            for li in est.line_items
        ],
        "subtotal": est.subtotal,
        "tax_rate": est.tax_rate,
        "tax": est.tax,
        "total": est.total,
    }
