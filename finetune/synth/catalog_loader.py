"""Load + validate the grounded trade-pricing catalog (Facts-from-Tools source).

catalog/catalog.json is the single source of every price in the synthetic invoices:
each row is {trade, kind, description, unit, price_low, price_high, source}, hand-
validated against public 2025-2026 pricing (see catalog/ provenance + eval_set/SOURCES.md).
This module is pure and Pydantic-free — it reads the file, filters by trade, and asserts
the row shape + price invariants so a malformed catalog fails loudly here, not silently
downstream as a nonsense invoice.
"""

import json

# The 5 trades the catalog (and the fine-tune task) covers. Any other trade is a bug.
ALLOWED_TRADES = {"carpentry", "electrical", "hvac", "plumbing", "roofing"}

REQUIRED_FIELDS = ("trade", "kind", "description", "unit", "price_low", "price_high", "source")


def load_catalog(path: str) -> list[dict]:
    """Read the catalog JSON file into a list of row dicts."""
    with open(path) as fh:
        return json.load(fh)


def by_trade(catalog: list[dict], trade: str) -> list[dict]:
    """All rows whose `trade` matches; empty list for an unknown trade."""
    return [row for row in catalog if row.get("trade") == trade]


def validate_catalog(catalog: list[dict]) -> None:
    """Assert every row has the required fields, a known trade, and 0 < low < high.

    Raises ValueError on the first offending row (with a message naming the problem
    field) so the caller sees exactly what's wrong. Returns None on success.
    """
    for i, row in enumerate(catalog):
        for field in REQUIRED_FIELDS:
            if field not in row:
                raise ValueError(f"row {i} missing required field {field!r}: {row}")
        if row["trade"] not in ALLOWED_TRADES:
            raise ValueError(
                f"row {i} has unknown trade {row['trade']!r} (allowed: {sorted(ALLOWED_TRADES)})"
            )
        low, high = row["price_low"], row["price_high"]
        if not (isinstance(low, (int, float)) and isinstance(high, (int, float))):
            raise ValueError(f"row {i} price_low/price_high must be numbers: {row}")
        if low <= 0:
            raise ValueError(f"row {i} price_low must be > 0, got {low}: {row}")
        if high <= 0:
            raise ValueError(f"row {i} price_high must be > 0, got {high}: {row}")
        if not (low < high):
            raise ValueError(f"row {i} requires price_low < price_high, got {low} >= {high}: {row}")
