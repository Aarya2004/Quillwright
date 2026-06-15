"""Unit tests for the Parse client's block → pipeline logic — no network needed.

The real logic in ParseModel is `blocks_to_pipeline`: turning Nemotron Parse's
structured blocks into Observations + Proposed Line Items (ADR-0011 decision C).
We test it directly against the block shape the Modal endpoint returns (the endpoint
runs the model's repo postprocessing, so blocks are [{class, bbox, text}] with
DocLayNet-style capitalized classes: "Table", "Text", "Title", ...).

The table fixture mirrors our mock supplier quote: Dual run capacitor $42.50 / qty 2,
Compressor contactor $28.00, R-410A refrigerant $30.00 / qty 4.
"""

from quillwright.backends.parse import blocks_to_pipeline
from quillwright.models import Observation, ProposedLineItem

# A markdown table as postprocess_text(cls="Table", table_format="markdown") emits it.
QUOTE_TABLE = (
    "| Item | Qty | Unit Price |\n"
    "| --- | --- | --- |\n"
    "| Dual run capacitor | 2 | $42.50 |\n"
    "| Compressor contactor | 1 | $28.00 |\n"
    "| R-410A refrigerant | 4 | $30.00 |\n"
)


def test_table_rows_become_proposed_line_items():
    obs, proposed = blocks_to_pipeline(
        [{"class": "Table", "bbox": [0, 0, 1, 1], "text": QUOTE_TABLE}]
    )
    assert len(proposed) == 3
    by_desc = {p.description: p for p in proposed}
    assert by_desc["Dual run capacitor"].rate == 42.50
    assert by_desc["Dual run capacitor"].quantity == 2.0
    assert by_desc["Compressor contactor"].rate == 28.00
    assert by_desc["R-410A refrigerant"].quantity == 4.0
    assert all(isinstance(p, ProposedLineItem) for p in proposed)


def test_proposed_item_keeps_source_text_for_human_review():
    # The human must be able to spot an OCR slip, so the raw row is carried along.
    _, proposed = blocks_to_pipeline([{"class": "Table", "bbox": [], "text": QUOTE_TABLE}])
    assert "$42.50" in proposed[0].source_text


def test_header_and_separator_rows_are_not_line_items():
    # The "| Item | Qty | Unit Price |" header has no money cell, and the |---| row
    # is a separator — neither should become a priced item.
    _, proposed = blocks_to_pipeline([{"class": "Table", "bbox": [], "text": QUOTE_TABLE}])
    descriptions = {p.description for p in proposed}
    assert "Item" not in descriptions
    assert all("---" not in p.description for p in proposed)


def test_non_table_blocks_become_text_observations():
    blocks = [
        {"class": "Title", "bbox": [], "text": "ACME HVAC Supply — Quote #1042"},
        {"class": "Text", "bbox": [], "text": "Net 30 terms. Prices valid 30 days."},
    ]
    obs, proposed = blocks_to_pipeline(blocks)
    assert proposed == []
    assert len(obs) == 2
    assert all(isinstance(o, Observation) and o.kind == "text" for o in obs)
    assert "ACME HVAC Supply" in obs[0].text


def test_priceless_table_row_falls_back_to_observation_not_dropped():
    # A row with no price must not silently vanish — it becomes an Observation.
    table = "| Note | |\n| Delivery included | |\n"
    obs, proposed = blocks_to_pipeline([{"class": "Table", "bbox": [], "text": table}])
    assert proposed == []
    assert any("Delivery included" in o.text for o in obs)


def test_price_with_thousands_comma_parses():
    table = "| Compressor unit | 1 | $1,250.00 |\n"
    _, proposed = blocks_to_pipeline([{"class": "Table", "bbox": [], "text": table}])
    assert proposed[0].rate == 1250.00


def test_empty_blocks_yield_nothing():
    obs, proposed = blocks_to_pipeline([])
    assert obs == []
    assert proposed == []


def test_whitespace_only_block_is_skipped():
    obs, proposed = blocks_to_pipeline([{"class": "Text", "bbox": [], "text": "   "}])
    assert obs == []
    assert proposed == []


def test_price_chosen_over_quantity_when_both_numeric():
    # Right-to-left scan must pick the price ($42.50), not the qty (2), as the rate.
    table = "| Dual run capacitor | 2 | $42.50 |\n"
    _, proposed = blocks_to_pipeline([{"class": "Table", "bbox": [], "text": table}])
    assert proposed[0].rate == 42.50
    assert proposed[0].quantity == 2.0
