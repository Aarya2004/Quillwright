from quillwright.thread import append_turn, compact, sanitized_history


def test_append_turn_records_message_and_op():
    thread = []
    out = append_turn(thread, message="add a contactor", op="added Compressor contactor")
    assert out == [{"message": "add a contactor", "op": "added Compressor contactor"}]
    # original not mutated (returns a new list)
    assert thread == []


def test_sanitized_history_uses_ops_only_no_dollars():
    thread = [
        {"message": "add a contactor", "op": "added Compressor contactor"},
        {"message": "make labor 2 hours", "op": "set Labor to 2"},
    ]
    hist = sanitized_history(thread)
    assert "added Compressor contactor" in hist
    assert "set Labor to 2" in hist
    assert "$" not in hist  # invariant: no dollar figures reach the model


def test_compact_keeps_last_k_verbatim_and_folds_the_rest():
    thread = [{"message": f"m{i}", "op": f"op{i}"} for i in range(6)]
    hist = compact(thread, keep_last=2)
    # old ops folded into ONE mechanical line; last 2 kept verbatim
    assert "earlier in this estimate" in hist.lower()
    assert "op0" in hist and "op3" in hist  # folded
    assert "op4" in hist and "op5" in hist  # verbatim tail
    # the fold is one line, not six
    assert hist.lower().count("earlier in this estimate") == 1


def test_compact_short_thread_no_fold():
    thread = [{"message": "m0", "op": "op0"}]
    hist = compact(thread, keep_last=2)
    assert "earlier in this estimate" not in hist.lower()
    assert "op0" in hist
