"""Read-models for the secondary pages (ADR-0010): Dashboard, Active Jobs, Inventory.

Dashboard + Active Jobs aggregate the SAME on-device memory store the agent already
writes to — so every number on those pages is real, derived from past Runs (no
invented revenue/technicians/CRM fields). Inventory is a read-only view over a
seeded JSON joined with the real catalog price; low-stock flags are computed, not
hardcoded. Live decrement is an explicit stretch and is NOT implemented here.
"""

import json

from quillwright.catalog import Catalog
from quillwright.memory import Memory

MEMORY_PATH = "/tmp/quillwright_memory.json"
INVENTORY_PATH = "data/sample_inventory.json"
CATALOG_PATH = "data/sample_catalog.json"


def _memory() -> Memory:
    # A fresh handle each call so the page always reflects the latest recorded runs.
    return Memory(MEMORY_PATH)


def _items_summary(line_items: list[str], limit: int = 3) -> str:
    shown = line_items[:limit]
    extra = len(line_items) - len(shown)
    text = ", ".join(shown)
    return f"{text} +{extra} more" if extra > 0 else text


def dashboard_data() -> dict:
    """KPI cards + recent activity, aggregated over real past Runs."""
    mem = _memory()
    prof = mem.profile()
    recent = mem.recent(limit=6)
    return {
        "job_count": prof["job_count"],
        "revenue_total": prof["revenue_total"],
        "top_items": prof["common_items"][:5],
        "recent": [
            {
                "id": r["id"],
                "transcript": r["transcript"],
                "items": _items_summary(r["line_items"]),
                "total": r["total"],
            }
            for r in recent
        ],
    }


def jobs_data() -> dict:
    """Every past Run as a table row, newest first."""
    mem = _memory()
    return {
        "jobs": [
            {
                "id": r["id"],
                "transcript": r["transcript"],
                "items": _items_summary(r["line_items"], limit=4),
                "total": r["total"],
            }
            for r in mem.recent()
        ]
    }


def inventory_data() -> dict:
    """Read-only stock view: seeded levels joined with the real catalog price."""
    with open(INVENTORY_PATH) as f:
        seeded = json.load(f)["parts"]
    catalog = Catalog.from_file(CATALOG_PATH)
    parts = []
    for p in seeded:
        cat = catalog.lookup(p["key"])
        rate = cat["rate"] if cat else None
        low = p["reorder_at"] > 0 and p["stock"] <= p["reorder_at"]
        parts.append(
            {
                "description": p["description"],
                "category": p["category"],
                "unit": p["unit"],
                "stock": p["stock"],
                "reorder_at": p["reorder_at"],
                "rate": rate,
                "low": low,
            }
        )
    return {
        "parts": parts,
        "total_skus": len(parts),
        "low_stock_count": sum(1 for p in parts if p["low"]),
    }
