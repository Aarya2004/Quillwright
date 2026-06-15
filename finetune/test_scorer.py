"""Unit tests for the CORD fine-tune scorer (the GPU-free, deterministic piece).

The training/eval scripts can only be validated on Modal GPUs, but the SCORER — which
turns model outputs into the headline baseline-vs-tuned number — must be correct and is
testable here. If the scorer is wrong, the 🎯 deliverable is wrong regardless of the model.

Run: pytest finetune/test_scorer.py -v
"""

from scorer import aggregate, parse_items, score


def test_parse_items_reads_cord_menu_shape():
    raw = '{"menu": [{"nm": "Latte", "cnt": 2, "price": "5,000"}], "total": "10,000"}'
    items = parse_items(raw)
    assert items == [{"name": "latte", "qty": 2, "price": 5000.0}]


def test_parse_items_strips_markdown_fence_and_prose():
    raw = 'Here is the JSON:\n```json\n{"menu": [{"nm": "Tea", "cnt": 1, "price": 3000}]}\n```'
    items = parse_items(raw)
    assert items == [{"name": "tea", "qty": 1, "price": 3000}]


def test_parse_items_bad_json_returns_empty():
    assert parse_items("the model rambled with no json") == []
    assert parse_items("") == []


def test_score_perfect_match():
    items = [{"name": "latte", "qty": 2, "price": 5000.0}]
    s = score(items, items)
    assert s["item_f1"] == 1.0
    assert s["qty_accuracy"] == 1.0
    assert s["price_accuracy"] == 1.0


def test_score_partial_item_overlap():
    produced = [{"name": "latte", "qty": 1, "price": 5000.0}]
    expected = [
        {"name": "latte", "qty": 1, "price": 5000.0},
        {"name": "tea", "qty": 1, "price": 3000.0},
    ]
    s = score(produced, expected)
    assert s["precision"] == 1.0  # the one produced item is correct
    assert s["recall"] == 0.5  # but it missed half the expected items
    assert s["item_f1"] == round(2 * 1.0 * 0.5 / 1.5, 3)


def test_score_qty_and_price_only_over_matched_items():
    produced = [{"name": "latte", "qty": 9, "price": 9999.0}]  # matched name, wrong nums
    expected = [{"name": "latte", "qty": 2, "price": 5000.0}]
    s = score(produced, expected)
    assert s["item_f1"] == 1.0  # name matches
    assert s["qty_accuracy"] == 0.0  # qty wrong
    assert s["price_accuracy"] == 0.0  # price wrong


def test_score_price_tolerance():
    produced = [{"name": "latte", "qty": 1, "price": 5005.0}]
    expected = [{"name": "latte", "qty": 1, "price": 5000.0}]
    assert score(produced, expected, price_tol=10.0)["price_accuracy"] == 1.0
    assert score(produced, expected, price_tol=0.0)["price_accuracy"] == 0.0


def test_aggregate_means_across_cases():
    cases = [
        {
            "item_f1": 1.0,
            "qty_accuracy": 1.0,
            "price_accuracy": 1.0,
            "precision": 1.0,
            "recall": 1.0,
        },
        {
            "item_f1": 0.0,
            "qty_accuracy": 0.0,
            "price_accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
        },
    ]
    agg = aggregate(cases)
    assert agg["item_f1"] == 0.5
    assert agg["n"] == 2


def test_aggregate_empty_is_safe():
    assert aggregate([])["n"] == 0
