"""The narrow tool surface the LLM brain may call.

The brain decides WHICH items to add and WHEN it's done; pricing and math stay
in the deterministic tools (Facts-from-Tools, ADR-0004). The brain never emits
numbers itself.
"""

from fieldforge.catalog import Catalog
from fieldforge.tools import compute, draft_line_item, lookup_price

# JSON-schema tool definitions handed to the model.
BRAIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_priced_item",
            "description": (
                "Add one line item to the estimate. Provide the item name; the catalog "
                "price is applied automatically. Call once per distinct item observed or "
                "mentioned (parts and labor)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "item or labor name"}
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
        # Facts-from-Tools: qty defaults to 1 in the core; compute owns the math.
        compute(f"1 * {res['rate']}")
        line = draft_line_item(
            res["description"], qty=1, unit=res["unit"], rate=res["rate"], source="catalog"
        )
        return {"status": "added", "line_item": line}
    return {"status": "error", "tool": name}
