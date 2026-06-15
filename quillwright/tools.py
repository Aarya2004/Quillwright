import ast
import json
import operator

from pydantic import ValidationError

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


def _extract_json_array(raw: str):
    """Pull a JSON array out of a model reply, or return None.

    Vision models (MiniCPM-V) routinely wrap the array in a ```json fence with a prose
    preamble ("Based on my analysis, here is …") instead of replying with ONLY the array
    as asked. Parsing `raw` directly then fails and we'd silently see 0 observations. So:
    try the whole string first, then the first balanced [...] slice we can find.
    """
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        pass
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def perceive(image_path: str, model: Model) -> list[Observation]:
    # Vision-capable backends accept image_path; text stubs ignore the kwarg.
    try:
        raw = model.generate(_PERCEIVE_PROMPT, image_path=image_path)
    except TypeError:
        raw = model.generate(f"List observations as JSON for image: {image_path}")
    data = _extract_json_array(raw)
    if data is None:
        return []
    # Skip rows that don't validate (e.g. a kind outside the allowed set) rather than
    # letting one bad row drop the whole estimate to zero observations.
    obs = []
    for o in data:
        try:
            obs.append(Observation(**o))
        except (TypeError, ValidationError):
            continue
    return obs


def draft_line_item(
    description: str, qty: float, unit: str, rate: float, source: str = "catalog"
) -> LineItem:
    return LineItem(
        description=description, quantity=qty, unit=unit, rate=rate, price_source=source
    )


def flag_for_human(reason: str) -> dict:
    return {"pause": True, "reason": reason}
