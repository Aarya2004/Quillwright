from quillwright.api.estimate import forge_estimate_stream


def test_stream_yields_trace_events_then_estimate():
    events = list(forge_estimate_stream("replaced capacitor, 1h labor", "hvac"))
    # at least one trace event, then a final estimate event
    kinds = [e["type"] for e in events]
    assert "trace" in kinds
    assert kinds[-1] == "estimate"
    # trace events carry a single step dict
    trace_events = [e for e in events if e["type"] == "trace"]
    assert all(set(e["step"]) == {"action", "model", "detail", "status"} for e in trace_events)
    # the final estimate event carries the full estimate payload with a total
    est = events[-1]["estimate"]
    assert est is not None and isinstance(est["total"], float)


def test_stream_emits_steps_progressively_not_all_at_once():
    events = list(forge_estimate_stream("replaced capacitor, 1h labor", "hvac"))
    trace_events = [e for e in events if e["type"] == "trace"]
    # perceive + at least the pricing/assemble steps => more than one trace event
    assert len(trace_events) >= 2
