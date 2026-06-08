from quillwright.memory import Memory


def test_recorded_run_can_be_recalled(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("replaced the capacitor", ["Dual run capacitor", "Labor"])
    runs = mem.recall("capacitor")
    assert len(runs) == 1
    assert "Dual run capacitor" in runs[0]["line_items"]
    assert runs[0]["transcript"] == "replaced the capacitor"


def test_recall_matches_on_line_items_not_just_transcript(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("did the usual AC job", ["Compressor contactor", "Labor"])
    # the word "contactor" is only in the line items, not the transcript
    runs = mem.recall("contactor")
    assert len(runs) == 1


def test_memory_persists_across_instances(tmp_path):
    path = str(tmp_path / "mem.json")
    Memory(path).record_run("swapped a capacitor", ["Dual run capacitor"])
    # a fresh instance on the same file still sees the run
    reopened = Memory(path)
    assert len(reopened.recall("capacitor")) == 1


def test_profile_learns_common_items_by_frequency(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("job 1", ["Labor", "Dual run capacitor"])
    mem.record_run("job 2", ["Labor", "Compressor contactor"])
    mem.record_run("job 3", ["Labor"])
    common = mem.profile()["common_items"]
    # most frequent item first
    assert common[0] == "Labor"
    assert set(common) == {"Labor", "Dual run capacitor", "Compressor contactor"}


def test_recall_ranks_more_relevant_runs_first(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("quick capacitor swap", ["Dual run capacitor"])
    mem.record_run("capacitor job, also a spare capacitor", ["Dual run capacitor", "Labor"])
    runs = mem.recall("capacitor")
    # the run mentioning "capacitor" more times ranks first
    assert runs[0]["transcript"].startswith("capacitor job")
