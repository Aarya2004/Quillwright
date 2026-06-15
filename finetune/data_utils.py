"""Shared, GPU-free, modal-free utilities for the CORD fine-tune pipeline.

This module is the single source of truth for constants and pure data transforms
that must be identical across prepare_data.py, train_modal.py, and eval.py.
Having one copy prevents train/eval prompt drift — the most common silent failure
mode in fine-tune pipelines (the model learns to answer one prompt; eval scores
a slightly different one; the delta is noise, not signal).

No modal import: safe to bundle into a Modal image via add_local_python_source and
to import in local unit tests without a Modal environment.
"""

import json

# The exact instruction shown to the model at BOTH train and eval time.  If you edit
# this, you must retrain — baseline and tuned are only comparable under one prompt.
PROMPT = (
    "Extract the line items from this receipt as JSON with this exact shape: "
    '{"menu": [{"nm": <item name>, "cnt": <quantity>, "price": <price>}], '
    '"total": <grand total>}. Output only the JSON.'
)

# CORD's gt_parse is rich (sub_total, discounts, change, …). We train on the slice
# the Quillwright line-item task actually needs: menu items + total.
# scorer.parse_items already reads this shape.
KEEP_KEYS = ("menu", "total")


def to_target(ground_truth: str) -> dict | None:
    """CORD ground_truth JSON-string -> trimmed {menu, total} target dict, or None.

    Handles two CORD quirks:
    - `menu` may be a single dict (single-item receipt) — normalised to a list.
    - Only KEEP_KEYS survive; all other gt_parse keys are dropped.

    Returns None on unparseable JSON, missing gt_parse, or when no KEEP_KEYS
    are present (nothing useful to train on).  Callers should skip None rows.
    """
    try:
        parsed = json.loads(ground_truth)
        gt = parsed.get("gt_parse", {})
    except (json.JSONDecodeError, AttributeError):
        return None

    result = {k: gt[k] for k in KEEP_KEYS if k in gt}
    if not result:
        return None

    # Normalize menu-as-dict to menu-as-list so every downstream consumer can
    # iterate unconditionally.  scorer.parse_items also does this defensively,
    # but doing it here means the stored target is always canonical.
    if "menu" in result and isinstance(result["menu"], dict):
        result["menu"] = [result["menu"]]

    return result


def to_openbmb_examples(rows: list[dict]) -> list[dict]:
    """Convert our manifest rows to OpenBMB's SupervisedDataset training JSON.

    Input rows are the {id, image, prompt, target} dicts written by
    prepare_data.py.  Output matches the shape that the VENDORED
    finetune/vendor/dataset.py parses (SHA cd64150b...):

      {
        "id": <id>,
        "image": <path str>,                       # __getitem__ reads a str path
        "conversations": [
          {"role": "user",      "content": "<image>\\n<prompt>"},
          {"role": "assistant", "content": <target>},
        ],
      }

    Why this exact shape (cited to the vendored dataset.py):
    - `image` is a single path STRING — `SupervisedDataset.__getitem__` does
      `if isinstance(self.raw_data[i]["image"], str)` (the single-image branch).
    - turns use "role"/"content" (NOT "from"/"value") — `conversation_to_ids_qwen2`
      reads `msg["role"]` / `msg["content"]` and asserts role in {user, assistant}.
    - the first user turn embeds the literal "<image>" token — `preprocess()`
      replaces that substring in `conversations[0]["content"]` with the model's
      image placeholder.  We place it as "<image>\\n<prompt>".
    """
    examples = []
    for r in rows:
        examples.append(
            {
                "id": r["id"],
                "image": r["image"],
                "conversations": [
                    {"role": "user", "content": f"<image>\n{r['prompt']}"},
                    {"role": "assistant", "content": r["target"]},
                ],
            }
        )
    return examples


def manifest_rows(path: str) -> list[dict]:
    """Read a JSONL manifest (one {id, image, prompt, target} per line) into a list."""
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
