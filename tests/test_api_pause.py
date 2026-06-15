from quillwright.api.estimate import forge_estimate_stream, resume_estimate_stream


def test_stream_emits_pause_when_price_missing():
    # 'unobtainium' is not in the sample catalog -> the agent pauses for a price.
    events = list(forge_estimate_stream("installed unobtainium", "hvac", thread_id="pause-1"))
    kinds = [e["type"] for e in events]
    assert "pause" in kinds
    pause = next(e for e in events if e["type"] == "pause")
    assert "unobtainium" in pause["reason"].lower()
    # the stream stops at the pause (no estimate yet)
    assert kinds[-1] == "pause"


def test_resume_continues_to_estimate_with_user_price():
    list(forge_estimate_stream("installed unobtainium", "hvac", thread_id="pause-2"))
    events = list(resume_estimate_stream(55.0, thread_id="pause-2"))
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "estimate"
    est = events[-1]["estimate"]
    assert est is not None
    # the user-supplied price made it into a line item
    assert any(li["rate"] == 55.0 for li in est["line_items"])
