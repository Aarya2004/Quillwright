from quillwright.recall_eval import keyword_recall_at_1, load_recall_cases, recall_at_1


def _seed():
    # (id, transcript, line_items) — a tiny corpus of past runs.
    return [
        {
            "id": 1,
            "transcript": "replaced the dual run capacitor",
            "line_items": ["Dual run capacitor"],
        },
        {"id": 2, "transcript": "topped up the refrigerant", "line_items": ["R-410A refrigerant"]},
        {
            "id": 3,
            "transcript": "swapped the compressor contactor",
            "line_items": ["Compressor contactor"],
        },
    ]


def test_recall_at_1_hits_when_ranker_puts_the_gold_run_first():
    corpus = _seed()

    # ranker that always returns run 2 first
    def ranker(query, runs):
        return sorted(runs, key=lambda r: r["id"] != 2)

    score = recall_at_1([{"query": "coolant", "gold_id": 2}], corpus, ranker)
    assert score == 1.0


def test_recall_at_1_misses_when_gold_run_is_not_first():
    corpus = _seed()

    def ranker(query, runs):
        return runs  # identity: run 1 first

    score = recall_at_1([{"query": "coolant", "gold_id": 2}], corpus, ranker)
    assert score == 0.0


def test_keyword_recall_finds_literal_overlap_but_misses_synonyms():
    corpus = _seed()
    # "contactor" is a literal token in run 3 -> keyword hits.
    assert keyword_recall_at_1([{"query": "contactor", "gold_id": 3}], corpus) == 1.0
    # "coolant" never appears literally (the run says "refrigerant") -> keyword misses.
    # This is exactly the gap semantic recall is meant to close (ADR-0003).
    assert keyword_recall_at_1([{"query": "coolant", "gold_id": 2}], corpus) == 0.0


def test_eval_set_loads_and_is_well_formed():
    data = load_recall_cases("data/recall_evalset.json")
    assert len(data["corpus"]) >= 15
    assert len(data["queries"]) >= 5
    corpus_ids = {r["id"] for r in data["corpus"]}
    for q in data["queries"]:
        assert q["gold_id"] in corpus_ids  # every query points at a real run
