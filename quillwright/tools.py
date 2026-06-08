import ast
import json
import operator
from quillwright.models import Observation, LineItem
from quillwright.catalog import Catalog
from quillwright.resolver import Model

# Safe arithmetic evaluator — the ONLY place numbers are computed (Facts-from-Tools, ADR-0004).
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def compute(expr: str) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
        return round(float(_eval(tree.body)), 2)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"bad expression: {expr}") from e


def lookup_price(item_key: str, catalog: Catalog) -> dict:
    hit = catalog.lookup(item_key)
    if hit is None:
        return {"found": False, "item": item_key}
    return {
        "found": True,
        "description": hit["description"],
        "unit": hit["unit"],
        "rate": hit["rate"],
    }


_PERCEIVE_PROMPT = (
    "You are a field-service vision assistant. Look at the image and list the "
    "equipment, parts, and damage you see as a JSON array of objects with keys "
    '"kind" (one of equipment/part/damage/text/other), "text" (short name), and '
    '"confidence" (0-1). Respond with ONLY the JSON array.'
)


def perceive(image_path: str, model: Model) -> list[Observation]:
    # Vision-capable backends accept image_path; text stubs ignore the kwarg.
    try:
        raw = model.generate(_PERCEIVE_PROMPT, image_path=image_path)
    except TypeError:
        raw = model.generate(f"List observations as JSON for image: {image_path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [Observation(**o) for o in data]


def draft_line_item(
    description: str, qty: float, unit: str, rate: float, source: str = "catalog"
) -> LineItem:
    return LineItem(
        description=description, quantity=qty, unit=unit, rate=rate, price_source=source
    )


def flag_for_human(reason: str) -> dict:
    return {"pause": True, "reason": reason}
