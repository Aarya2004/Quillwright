from fieldforge.brain_eval import load_cases, score_case


def test_load_cases_reads_evalset():
    cases = load_cases("data/brain_evalset.json")
    assert len(cases) >= 10
    assert "transcript" in cases[0] and "expected" in cases[0]


def test_score_perfect_match():
    expected = [
        {"description": "Dual run capacitor", "quantity": 1},
        {"description": "Labor", "quantity": 3},
    ]
    produced = [
        {"description": "Dual run capacitor", "quantity": 1},
        {"description": "Labor", "quantity": 3},
    ]
    s = score_case(produced, expected)
    assert s["item_f1"] == 1.0 and s["qty_accuracy"] == 1.0


def test_score_missing_item_lowers_recall():
    expected = [
        {"description": "Dual run capacitor", "quantity": 1},
        {"description": "Labor", "quantity": 1},
    ]
    produced = [{"description": "Dual run capacitor", "quantity": 1}]
    s = score_case(produced, expected)
    assert s["item_f1"] < 1.0


def test_score_wrong_quantity_penalizes_qty_only():
    expected = [{"description": "Labor", "quantity": 3}]
    produced = [{"description": "Labor", "quantity": 1}]
    s = score_case(produced, expected)
    assert s["item_f1"] == 1.0 and s["qty_accuracy"] == 0.0
