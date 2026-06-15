"""Unit tests for eval.py's pure score_row() function.

These tests run WITHOUT torch, modal, or GPU dependencies — score_row() only
touches the scorer module (pure Python). If these break, the eval pipeline
will silently misreport results regardless of model quality.

Run: pytest finetune/test_eval_logic.py -v
"""

import sys
import os

# Make finetune/ importable without installing the package.
sys.path.insert(0, os.path.dirname(__file__))

from eval import score_row  # noqa: E402  (path insert must come first)


def test_score_row_normal_answer():
    """A well-formed model answer extracts items and matches the target correctly."""
    answer = '{"menu": [{"nm": "Latte", "cnt": 2, "price": "5,000"}]}'
    target = '{"menu": [{"nm": "Latte", "cnt": 2, "price": "5,000"}]}'
    result = score_row(answer, target)
    assert result["item_f1"] == 1.0
    assert result["qty_accuracy"] == 1.0
    assert result["price_accuracy"] == 1.0


def test_score_row_garbage_answer_scores_zero_and_does_not_raise():
    """A totally unparseable model output must score zero without raising."""
    answer = "Sorry, I cannot parse this receipt."
    target = '{"menu": [{"nm": "Tea", "cnt": 1, "price": "3,000"}]}'
    result = score_row(answer, target)
    # parse failure -> produced=[] -> no precision/recall -> f1=0
    assert result["item_f1"] == 0.0
    assert result["qty_accuracy"] == 0.0
    assert result["price_accuracy"] == 0.0
    # Must be a valid score dict — no exception raised
    assert "item_f1" in result
    assert "precision" in result


def test_score_row_markdown_fence_answer():
    """Answers wrapped in a markdown fence are still parsed correctly."""
    answer = '```json\n{"menu": [{"nm": "Espresso", "cnt": 1, "price": "4,500"}]}\n```'
    target = '{"menu": [{"nm": "Espresso", "cnt": 1, "price": "4,500"}]}'
    result = score_row(answer, target)
    assert result["item_f1"] == 1.0
    assert result["qty_accuracy"] == 1.0
    assert result["price_accuracy"] == 1.0
