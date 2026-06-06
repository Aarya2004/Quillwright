from langgraph.checkpoint.memory import InMemorySaver
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent
from fieldforge.pdf import estimate_to_pdf


def test_capture_to_pdf_end_to_end(tmp_path):
    perception = StubModel(responses=['[{"kind":"part","text":"capacitor","confidence":0.9}]'])
    agent = build_agent(perception, Catalog.from_file("data/sample_catalog.json"), InMemorySaver())
    cfg = {"configurable": {"thread_id": "e2e"}}
    out = agent.invoke(
        {
            "capture": Capture(image_paths=["a.jpg"], transcript="cap", trade_hint="hvac"),
            "observations": [],
            "line_items": [],
            "trace": [],
            "estimate": None,
        },
        cfg,
    )
    est = out["estimate"]
    assert est is not None and est.total > 0
    pdf = tmp_path / "e2e.pdf"
    estimate_to_pdf(est, str(pdf))
    assert pdf.read_bytes()[:4] == b"%PDF"
