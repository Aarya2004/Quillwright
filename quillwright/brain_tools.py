"""The narrow tool surface the LLM brain may call.

The brain decides WHICH items to add and WHEN it's done; pricing and math stay
in the deterministic tools (Facts-from-Tools, ADR-0004). The brain never emits
numbers itself.
"""

from quillwright.catalog import Catalog
from quillwright.tools import compute, draft_line_item, lookup_price

# JSON-schema tool definitions handed to the model.
BRAIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_priced_item",
            "description": (
                "Add one line item to the estimate. Provide the item name and how many "
                "units/hours (quantity); the catalog price is applied automatically. Call "
                "once per distinct item observed or mentioned (parts and labor)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "item or labor name"},
                    "quantity": {
                        "type": "number",
                        "description": "how many units or hours (default 1)",
                    },
                },
                "required": ["item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call when every observed/mentioned item has been added.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def dispatch(name: str, args: dict, catalog: Catalog) -> dict:
    """Execute a brain tool call. Returns a status dict the loop interprets."""
    if name == "finish":
        return {"status": "done"}
    if name == "add_priced_item":
        item = (args or {}).get("item", "")
        res = lookup_price(item, catalog)
        if not res["found"]:
            return {"status": "need_price", "item": item}
        qty = _coerce_qty((args or {}).get("quantity"))
        # Facts-from-Tools: compute owns the math; the model only supplies the count.
        compute(f"{qty} * {res['rate']}")
        line = draft_line_item(
            res["description"], qty=qty, unit=res["unit"], rate=res["rate"], source="catalog"
        )
        return {"status": "added", "line_item": line}
    return {"status": "error", "tool": name}


def _coerce_qty(value) -> float:
    """Quantity from possibly-noisy model output; fall back to 1 on anything invalid."""
    try:
        q = float(value)
        return q if q > 0 else 1
    except (TypeError, ValueError):
        return 1
