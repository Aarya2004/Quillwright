from quillwright.api.export import estimate_to_json_payload


def _rows():
    return [
        {"description": "Capacitor", "quantity": 2, "unit": "ea", "rate": 24.0},
        {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
    ]


def test_export_round_trips_rows_with_server_authoritative_totals():
    out = estimate_to_json_payload(_rows(), job_title="AC repair", tax_rate=0.13)
    assert out["job_title"] == "AC repair"
    items = out["line_items"]
    assert items[0]["subtotal"] == 48.0  # 2 * 24, computed server-side
    assert out["subtotal"] == 138.0
    assert out["tax"] == round(138.0 * 0.13, 2)
    assert out["total"] == round(138.0 * 1.13, 2)


def test_export_is_machine_readable_and_labelled_as_a_draft():
    out = estimate_to_json_payload(_rows(), job_title="j", tax_rate=0.13)
    # honesty: the JSON carries the same draft/sample disclaimer as the PDF.
    assert "disclaimer" in out
    assert "draft" in out["disclaimer"].lower()
    # schema marker so an importing system can recognise the format.
    assert out["format"] == "quillwright.estimate.v1"


def test_export_coerces_bad_numbers_like_recalc():
    out = estimate_to_json_payload(
        [{"description": "x", "quantity": "two", "unit": "ea", "rate": "abc"}],
        job_title="j",
        tax_rate=0.13,
    )
    assert out["line_items"][0]["subtotal"] == 0.0
