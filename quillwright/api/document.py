"""Document Capture: a handed-over document -> Observations + Proposed Line Items (ADR-0011).

Thin adapter over the Extraction role (Nemotron Parse on Modal): file path in, JSON
the frontend confirm card renders out. The model is injectable for tests. In
production it resolves to ParseModel when FF_MODAL_PARSE_URL is set; otherwise a
deterministic demo parse runs the REAL blocks_to_pipeline logic over a canned
supplier quote, so the stub Space demos the flow with zero models (the same
honest-scaffolding pattern as _stub_perception in api/estimate.py).
"""

import os

from quillwright.backends.parse import blocks_to_pipeline

# The canned supplier quote the demo "reads" when no Modal Parse endpoint is
# configured. Mirrors the test fixture in test_parse_backend.py.
_DEMO_BLOCKS = [
    {"class": "Title", "bbox": [], "text": "ACME HVAC Supply — Quote #1042"},
    {
        "class": "Table",
        "bbox": [],
        "text": (
            "| Item | Qty | Unit Price |\n"
            "| --- | --- | --- |\n"
            "| Dual run capacitor | 2 | $42.50 |\n"
            "| Compressor contactor | 1 | $28.00 |\n"
            "| R-410A refrigerant | 4 | $30.00 |\n"
        ),
    },
    {"class": "Text", "bbox": [], "text": "Net 30 terms. Prices valid 30 days."},
]


def _resolve_extraction():
    """Real Nemotron Parse when its Modal URL is configured; else None (demo parse)."""
    if os.environ.get("FF_MODAL_PARSE_URL"):
        from quillwright.resolver import ModelResolver

        return ModelResolver(mode="best", backend="modal").for_role("extraction")
    return None


def parse_document_capture(path: str, model=None) -> dict:
    """Parse the document at `path`; return {model, observations, proposed_items}.

    Every price stays *proposed* — the human confirms it in the UI before it becomes
    a LineItem with price_source="document" (Facts-from-Tools, ADR-0004/0011).
    """
    parser = model if model is not None else _resolve_extraction()
    if parser is None:
        observations, proposed = blocks_to_pipeline(_DEMO_BLOCKS)
        name = "parse-stub (demo quote)"
    else:
        observations, proposed = parser.parse_document(path)
        name = parser.name
    return {
        "model": name,
        "observations": [{"kind": o.kind, "text": o.text} for o in observations],
        "proposed_items": [
            {
                "description": p.description,
                "quantity": p.quantity,
                "unit": p.unit,
                "rate": p.rate,
                "source_text": p.source_text,
            }
            for p in proposed
        ],
    }
