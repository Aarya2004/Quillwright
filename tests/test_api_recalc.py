from quillwright.api.recalc import recalc_estimate


def test_recalc_computes_subtotals_and_totals():
    rows = [
        {"description": "Capacitor", "quantity": 2, "unit": "ea", "rate": 24.0},
        {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
    ]
    out = recalc_estimate(rows, job_title="AC repair", tax_rate=0.13)
    items = out["line_items"]
    assert items[0]["subtotal"] == 48.0  # 2 * 24
    assert out["subtotal"] == 138.0
    assert out["tax"] == round(138.0 * 0.13, 2)
    assert out["total"] == round(138.0 * 1.13, 2)


def test_recalc_coerces_bad_numbers_to_safe_values():
    rows = [{"description": "x", "quantity": "two", "unit": "ea", "rate": "abc"}]
    out = recalc_estimate(rows, job_title="j", tax_rate=0.13)
    # invalid qty/rate -> 0 so a typo never crashes the recalc
    assert out["line_items"][0]["subtotal"] == 0.0
