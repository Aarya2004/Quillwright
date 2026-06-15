"""Document Capture API adapter (ADR-0011): document image in -> JSON the web layer renders.

The endpoint half of "wire Parse to the UI": ParseModel produces Observations +
Proposed Line Items; this adapter shapes them for the frontend confirm card. The
model is injectable for tests; without FF_MODAL_PARSE_URL it falls back to a
deterministic demo parse (the stub Space runs zero models — same honest-scaffolding
pattern as _stub_perception), run through the REAL blocks_to_pipeline logic.
"""

from quillwright.api.document import parse_document_capture
from quillwright.models import Observation, ProposedLineItem


class FakeParse:
    name = "fake-parse"

    def parse_document(self, path):
        return (
            [Observation(kind="text", text="ACME HVAC Supply — Quote #1042")],
            [
                ProposedLineItem(
                    description="Dual run capacitor",
                    quantity=2.0,
                    rate=42.5,
                    source_text="Dual run capacitor 2 $42.50",
                )
            ],
        )


def test_injected_model_output_is_shaped_for_the_frontend(tmp_path):
    doc = tmp_path / "quote.png"
    doc.write_bytes(b"png")
    out = parse_document_capture(str(doc), model=FakeParse())
    assert out["model"] == "fake-parse"
    assert out["observations"] == [{"kind": "text", "text": "ACME HVAC Supply — Quote #1042"}]
    item = out["proposed_items"][0]
    assert item["description"] == "Dual run capacitor"
    assert item["quantity"] == 2.0
    assert item["unit"] == "ea"
    assert item["rate"] == 42.5
    # The raw row rides along so the human can spot an OCR slip before confirming.
    assert "$42.50" in item["source_text"]


def test_demo_parse_when_no_modal_url(monkeypatch, tmp_path):
    monkeypatch.delenv("FF_MODAL_PARSE_URL", raising=False)
    doc = tmp_path / "quote.png"
    doc.write_bytes(b"png")
    out = parse_document_capture(str(doc))
    # The demo never dead-ends: a canned supplier quote yields priced proposals...
    assert len(out["proposed_items"]) >= 2
    assert all(p["rate"] > 0 for p in out["proposed_items"])
    # ...and its non-priced parts still surface as observations.
    assert out["observations"]
    # Model honesty: the trace must not claim a real model ran.
    assert "stub" in out["model"]
