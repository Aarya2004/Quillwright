from fieldforge.api import estimate as est_api


def test_run_is_recorded_and_recalled_next_time(tmp_path, monkeypatch):
    # point memory at a temp file so the test is isolated
    mem_path = str(tmp_path / "mem.json")
    monkeypatch.setattr(est_api, "MEMORY_PATH", mem_path)
    est_api.reset_memory()

    # first job: no history yet -> no recall step, but it gets recorded
    list(est_api.forge_estimate_stream("replaced the capacitor", thread_id="m1"))

    # second similar job: a recall step should appear, citing the prior job
    events = list(est_api.forge_estimate_stream("another capacitor job", thread_id="m2"))
    recalls = [e for e in events if e["type"] == "trace" and e["step"]["action"] == "recall"]
    assert recalls, "expected a recall trace step on the second similar job"

    # and the episodic store now holds both runs
    from fieldforge.memory import Memory

    assert len(Memory(mem_path).recall("capacitor")) == 2
