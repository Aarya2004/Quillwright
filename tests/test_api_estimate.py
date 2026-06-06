from fieldforge.api.estimate import forge_estimate


def test_forge_estimate_returns_trace_and_estimate_json():
    out = forge_estimate("replaced capacitor, 1h labor", "hvac")
    assert "trace" in out and "estimate" in out
    est = out["estimate"]
    assert est is not None
    # estimate is plain JSON-serializable dicts, not pydantic objects
    assert isinstance(est["total"], float)
    descs = [li["description"].lower() for li in est["line_items"]]
    assert any("capacitor" in d for d in descs)
    # trace is a list of step dicts with the expected keys
    assert out["trace"] and set(out["trace"][0]) == {"action", "model", "detail", "status"}
