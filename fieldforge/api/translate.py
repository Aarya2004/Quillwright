"""Localize the customer-facing estimate via Cohere Aya (or any text model).

Only descriptions and labels are translated; every number (rate/subtotal/tax/
total) is left exactly as computed — money is never sent through the model.
"""

import copy


def _translate_text(text: str, language: str, model) -> str:
    prompt = (
        f"Translate the following field-service estimate line into {language}. "
        f"Return ONLY the translation, no quotes or notes.\n\n{text}"
    )
    out = model.generate(prompt).strip()
    return out or text


def translate_estimate(estimate: dict, language: str, model) -> dict:
    """Return a copy of the estimate with descriptions translated into `language`."""
    if not language or language.lower().startswith("english"):
        return estimate  # source is English; nothing to do
    out = copy.deepcopy(estimate)
    for li in out.get("line_items", []):
        li["description"] = _translate_text(li["description"], language, model)
    return out
