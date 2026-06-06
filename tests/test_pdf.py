import os
from fieldforge.models import Estimate, LineItem
from fieldforge.pdf import estimate_to_pdf


def test_pdf_is_written_and_nonempty(tmp_path):
    est = Estimate(
        job_title="AC repair",
        line_items=[LineItem(description="Capacitor", quantity=1, unit="ea", rate=24.0)],
        tax_rate=0.13,
    )
    out = tmp_path / "est.pdf"
    estimate_to_pdf(est, str(out))
    assert os.path.exists(out) and os.path.getsize(out) > 500
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
