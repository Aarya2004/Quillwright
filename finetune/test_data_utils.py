"""Tests for data_utils — the GPU-free, modal-free shared utilities for prepare/train/eval.

Each TDD cycle adds ONE test first, watches it fail, then the implementation is added.
Fixtures use realistic CORD-v2 ground_truth shapes.

Run: pytest finetune/test_data_utils.py -v
"""

import json


# ---------------------------------------------------------------------------
# Slice 1: to_target — basic happy path (menu list, total dict)
# ---------------------------------------------------------------------------


def test_to_target_basic_happy_path():
    """Realistic CORD row: menu is a list, total is a dict."""
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "menu": [
                    {"nm": "Americano", "cnt": "1", "price": "4,500"},
                    {"nm": "Latte", "cnt": "2", "price": "5,000"},
                ],
                "total": {"total_price": "14,500"},
                "sub_total": {"subtotal_price": "14,500"},
            }
        }
    )
    result = to_target(gt)
    assert result is not None
    assert set(result.keys()) == {"menu", "total"}
    assert len(result["menu"]) == 2
    assert result["menu"][0]["nm"] == "Americano"
    # sub_total must be stripped — only KEEP_KEYS survive
    assert "sub_total" not in result


# ---------------------------------------------------------------------------
# Slice 2: menu-as-dict normalization
# ---------------------------------------------------------------------------


def test_to_target_menu_as_dict_normalized_to_list():
    """CORD quirk: a single-item receipt sometimes has menu as a plain dict."""
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "menu": {"nm": "Coffee", "cnt": "1", "price": "3,000"},
                "total": {"total_price": "3,000"},
            }
        }
    )
    result = to_target(gt)
    assert result is not None
    assert isinstance(result["menu"], list)
    assert result["menu"] == [{"nm": "Coffee", "cnt": "1", "price": "3,000"}]


# ---------------------------------------------------------------------------
# Slice 3: unparseable / missing gt_parse / empty result -> None
# ---------------------------------------------------------------------------


def test_to_target_broken_json_returns_none():
    from data_utils import to_target

    assert to_target("not json at all {{{") is None


def test_to_target_missing_gt_parse_returns_none():
    """gt_parse key absent — nothing useful to train on."""
    from data_utils import to_target

    gt = json.dumps({"something_else": {}})
    assert to_target(gt) is None


def test_to_target_empty_result_returns_none():
    """gt_parse exists but has none of the KEEP_KEYS."""
    from data_utils import to_target

    gt = json.dumps({"gt_parse": {"sub_total": {"subtotal_price": "0"}}})
    assert to_target(gt) is None


def test_to_target_missing_total_still_returns_menu():
    """total is optional — if menu is present we still emit a useful target."""
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "menu": [{"nm": "Tea", "cnt": "1", "price": "2,500"}],
            }
        }
    )
    result = to_target(gt)
    assert result is not None
    assert "menu" in result
    assert "total" not in result


# ---------------------------------------------------------------------------
# Slice 4: serialization is deterministic (sort_keys, ensure_ascii=False)
# ---------------------------------------------------------------------------


def test_to_target_serialization_is_deterministic():
    """Same input -> same json.dumps output regardless of dict insertion order."""
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "total": {"total_price": "3,000"},
                "menu": [{"nm": "Coffee", "cnt": "1", "price": "3,000"}],
            }
        }
    )
    result = to_target(gt)
    assert result is not None
    s1 = json.dumps(result, ensure_ascii=False, sort_keys=True)
    s2 = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert s1 == s2


# ---------------------------------------------------------------------------
# Slice 5: PROMPT constant exists and is a non-empty string
# ---------------------------------------------------------------------------


def test_prompt_constant_exists():
    from data_utils import PROMPT

    assert isinstance(PROMPT, str) and len(PROMPT) > 20


# ---------------------------------------------------------------------------
# Slice 6: manifest_rows reads a JSONL file
# ---------------------------------------------------------------------------


def test_manifest_rows(tmp_path):
    from data_utils import manifest_rows

    lines = [
        {
            "id": "train-0000",
            "image": "/cache/cord/images/train/0000.png",
            "prompt": "p",
            "target": "{}",
        },
        {
            "id": "train-0001",
            "image": "/cache/cord/images/train/0001.png",
            "prompt": "p",
            "target": "{}",
        },
    ]
    p = tmp_path / "train.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in lines) + "\n")
    rows = manifest_rows(str(p))
    assert len(rows) == 2
    assert rows[0]["id"] == "train-0000"
    assert rows[1]["id"] == "train-0001"


# ---------------------------------------------------------------------------
# Slice 7: CONTRACT TEST — to_target output round-trips through scorer.parse_items
# ---------------------------------------------------------------------------


def test_to_target_round_trips_through_scorer():
    """Core contract: what prepare_data writes as target, scorer can read back.

    This proves that training targets and eval scoring agree on the same JSON shape —
    the fundamental correctness property of the fine-tune pipeline.
    """
    import sys
    import os

    sys.path.insert(0, os.path.dirname(__file__))
    import scorer
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "menu": [
                    {"nm": "Americano", "cnt": "1", "price": "4,500"},
                    {"nm": "Latte", "cnt": "2", "price": "5,000"},
                ],
                "total": {"total_price": "14,500"},
            }
        }
    )
    target = to_target(gt)
    assert target is not None

    # Serialize as prepare_data would, then parse as eval/scorer would.
    serialized = json.dumps(target, ensure_ascii=False, sort_keys=True)
    items = scorer.parse_items(serialized)

    assert len(items) == 2
    names = {i["name"] for i in items}
    assert "americano" in names
    assert "latte" in names
    # Prices survive the round-trip numerically (scorer._to_num strips comma separators)
    prices = {i["name"]: i["price"] for i in items}
    assert prices["americano"] == 4500.0
    assert prices["latte"] == 5000.0


def test_to_target_menu_as_dict_round_trips_through_scorer():
    """menu-as-dict case also round-trips cleanly."""
    import sys
    import os

    sys.path.insert(0, os.path.dirname(__file__))
    import scorer
    from data_utils import to_target

    gt = json.dumps(
        {
            "gt_parse": {
                "menu": {"nm": "Coffee", "cnt": "1", "price": "3,000"},
                "total": {"total_price": "3,000"},
            }
        }
    )
    target = to_target(gt)
    serialized = json.dumps(target, ensure_ascii=False, sort_keys=True)
    items = scorer.parse_items(serialized)
    assert len(items) == 1
    assert items[0]["name"] == "coffee"
    assert items[0]["price"] == 3000.0


# ---------------------------------------------------------------------------
# Slice 8: to_openbmb_examples — manifest rows -> OpenBMB SupervisedDataset JSON
#
# Format verified against the VENDORED finetune/vendor/dataset.py at SHA
# cd64150b... :
#   - SupervisedDataset.__getitem__ reads row["image"] as a *str* path
#     (line 54: `if isinstance(self.raw_data[i]["image"], str)`) and
#     row["conversations"] (line 62: passed to preprocess()).
#   - each conversation turn is parsed by conversation_to_ids_qwen2 /
#     _minicpm which read msg["role"] and msg["content"] and assert
#     role in ["user", "assistant"] (dataset.py lines 277-278, 204-206) —
#     i.e. "role"/"content", NOT "from"/"value".
#   - preprocess() (dataset.py line 377) replaces the literal substring
#     "<image>" inside conversations[0]["content"] with the image placeholder,
#     so the first user turn's content must contain "<image>".
# ---------------------------------------------------------------------------


def test_to_openbmb_examples_single_row_shape():
    """One manifest row -> one OpenBMB example with image path + 2-turn convo."""
    from data_utils import to_openbmb_examples

    rows = [
        {
            "id": "train-0000",
            "image": "/cache/cord/images/train/0000.png",
            "prompt": "Extract the receipt.",
            "target": '{"menu": [{"nm": "Tea"}]}',
        }
    ]
    out = to_openbmb_examples(rows)
    assert isinstance(out, list) and len(out) == 1
    ex = out[0]
    # image is a single path STRING (dataset.py __getitem__ line 54 branch).
    assert ex["image"] == "/cache/cord/images/train/0000.png"
    assert isinstance(ex["image"], str)
    # id carried through.
    assert ex["id"] == "train-0000"


def test_to_openbmb_examples_conversation_roles_and_content():
    """Two turns: user (with <image>\\n + prompt) then assistant (= target)."""
    from data_utils import to_openbmb_examples

    rows = [
        {
            "id": "train-0001",
            "image": "/img/1.png",
            "prompt": "Extract the receipt.",
            "target": '{"menu": []}',
        }
    ]
    convo = to_openbmb_examples(rows)[0]["conversations"]
    assert len(convo) == 2
    # role/content keys (NOT from/value) — dataset.py conversation_to_ids_qwen2.
    assert convo[0] == {"role": "user", "content": "<image>\nExtract the receipt."}
    assert convo[1] == {"role": "assistant", "content": '{"menu": []}'}


def test_to_openbmb_examples_image_placeholder_present():
    """The first user turn MUST contain the literal '<image>' (preprocess replaces it)."""
    from data_utils import to_openbmb_examples

    rows = [{"id": "x", "image": "/i.png", "prompt": "P", "target": "T"}]
    user_content = to_openbmb_examples(rows)[0]["conversations"][0]["content"]
    assert "<image>" in user_content
    # placeholder is at the very start, followed by newline then prompt.
    assert user_content.startswith("<image>\n")


def test_to_openbmb_examples_multiple_rows_order_preserved():
    from data_utils import to_openbmb_examples

    rows = [
        {"id": "a", "image": "/a.png", "prompt": "P", "target": "TA"},
        {"id": "b", "image": "/b.png", "prompt": "P", "target": "TB"},
    ]
    out = to_openbmb_examples(rows)
    assert [e["id"] for e in out] == ["a", "b"]
    assert out[0]["conversations"][1]["content"] == "TA"
    assert out[1]["conversations"][1]["content"] == "TB"


def test_to_openbmb_examples_empty_input():
    from data_utils import to_openbmb_examples

    assert to_openbmb_examples([]) == []
