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


def test_record_run_without_total_stays_backward_compatible(tmp_path):
    # the original 2-arg call still works; total defaults to None.
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("legacy call", ["Labor"])
    assert mem.recent()[0]["total"] is None


def test_record_run_stores_total_when_given(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("capacitor swap", ["Dual run capacitor", "Labor"], total=138.0)
    assert mem.recent()[0]["total"] == 138.0


def test_recent_returns_newest_first_with_a_stable_id(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("first", ["Labor"], total=90.0)
    mem.record_run("second", ["Dual run capacitor"], total=24.0)
    recent = mem.recent()
    assert [r["transcript"] for r in recent] == ["second", "first"]
    # each run carries a 1-based sequence id (no wall-clock; deterministic).
    assert recent[0]["id"] == 2
    assert recent[1]["id"] == 1


def test_recent_respects_a_limit(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    for i in range(5):
        mem.record_run(f"job {i}", ["Labor"], total=float(i))
    assert len(mem.recent(limit=3)) == 3


def test_profile_reports_revenue_total_over_recorded_runs(tmp_path):
    mem = Memory(str(tmp_path / "mem.json"))
    mem.record_run("a", ["Labor"], total=100.0)
    mem.record_run("b", ["Labor"], total=50.5)
    mem.record_run("c", ["Labor"])  # no total -> ignored in revenue
    prof = mem.profile()
    assert prof["job_count"] == 3
    assert prof["revenue_total"] == 150.5


class _FakeEmbedder:
    """Synonym-aware fake: 'coolant' ~ 'refrigerant', far from 'capacitor'."""

    name = "fake"
    _V = {"coolant": [1.0, 0.9], "refrigerant": [1.0, 1.0], "capacitor": [0.0, 1.0]}

    def encode(self, text):
        t = text.lower()
        for k, v in self._V.items():
            if k in t:
                return v
        return [0.2, 0.2]


def test_recall_without_embedder_is_keyword_only(tmp_path):
    # default behavior unchanged — no embedder, literal match required.
    mem = Memory(str(tmp_path / "m.json"))
    mem.record_run("topped up the refrigerant", ["R-410A refrigerant"])
    assert mem.recall("coolant") == []  # no literal overlap -> keyword miss


def test_recall_with_embedder_finds_synonym(tmp_path):
    emb = _FakeEmbedder()
    mem = Memory(str(tmp_path / "m.json"), embedder=emb)
    mem.record_run("topped up the refrigerant", ["R-410A refrigerant"])
    mem.record_run("replaced the capacitor", ["Dual run capacitor"])
    runs = mem.recall("coolant recharge")  # 'coolant' never literal; semantic hit
    assert runs and "refrigerant" in runs[0]["line_items"][0].lower()


def test_record_run_caches_embedding_in_json(tmp_path):
    path = str(tmp_path / "m.json")
    mem = Memory(path, embedder=_FakeEmbedder())
    mem.record_run("topped up the refrigerant", ["R-410A refrigerant"])
    import json

    saved = json.load(open(path))["runs"][0]
    assert "embedding" in saved and len(saved["embedding"]) == 2
