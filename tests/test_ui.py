from fieldforge.models import LineItem, Estimate, TraceStep
from fieldforge.ui import trace_html, estimate_rows, summary_text


def test_trace_html_marks_done_and_active_steps():
    steps = [
        TraceStep(action="perceive", model="MiniCPM-V-4.6", detail="found 2", status="ok"),
        TraceStep(action="price", model="lookup_price", detail="pricing…", status="active"),
    ]
    html = trace_html(steps)
    assert "check_circle" in html          # done step gets the check icon
    assert "terminal-cursor" in html       # active step gets the blinking cursor
    assert "MiniCPM-V-4.6" in html          # model badge surfaced inline


def test_trace_html_empty_shows_waiting():
    assert "Waiting" in trace_html([])


def test_estimate_rows_maps_line_items_to_table_rows():
    est = Estimate(job_title="AC repair", line_items=[
        LineItem(description="Capacitor", quantity=1, unit="ea", rate=42.5),
    ], tax_rate=0.09)
    rows = estimate_rows(est)
    assert rows == [["Capacitor", "1 ea", "$42.50", "$42.50"]]


def test_summary_text_formats_subtotal_tax_total():
    est = Estimate(job_title="x", line_items=[
        LineItem(description="a", quantity=1, unit="ea", rate=100.0),
    ], tax_rate=0.09)
    assert summary_text(est) == "Subtotal $100.00 · Tax (9%) $9.00 · Total $109.00"
