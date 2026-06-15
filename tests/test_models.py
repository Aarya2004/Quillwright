from quillwright.models import Capture, Observation, LineItem, Estimate, TraceStep


def test_line_item_subtotal_is_qty_times_rate():
    item = LineItem(description="Capacitor", quantity=2, unit="ea", rate=24.0)
    assert item.subtotal == 48.0


def test_estimate_total_sums_subtotals_with_tax():
    est = Estimate(
        job_title="AC repair",
        line_items=[
            LineItem(description="Capacitor", quantity=1, unit="ea", rate=24.0),
            LineItem(description="Labor", quantity=2, unit="hr", rate=90.0),
        ],
        tax_rate=0.13,
    )
    assert est.subtotal == 204.0
    assert round(est.tax, 2) == 26.52
    assert round(est.total, 2) == 230.52


def test_observation_and_capture_and_tracestep_construct():
    obs = Observation(kind="part", text="dual run capacitor 45/5 uF", confidence=0.82)
    cap = Capture(
        image_paths=["/tmp/a.jpg"], transcript="replaced the capacitor", trade_hint="hvac"
    )
    step = TraceStep(action="perceive", model="StubModel", detail="found 1 part", confidence=0.82)
    assert obs.kind == "part" and cap.trade_hint == "hvac" and step.action == "perceive"
