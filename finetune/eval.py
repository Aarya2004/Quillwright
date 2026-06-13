"""Baseline-vs-tuned eval on the CORD held-out test split (ADR-0006) — the target artifact.

Runs un-tuned MiniCPM-V-2_6 AND the LoRA-tuned model over the SAME test manifest
(written by prepare_data.py), scores both with finetune/scorer.py, and writes
results.json + a printed table. That delta (baseline F1 -> tuned F1) is the quest
evidence and the Field-Notes graph.

Runs on Modal so it shares the volume + cached weights with training; the scorer
runs in-process (pure Python, no GPU). Scoring is deterministic — same outputs in,
same numbers out — so the reported gain is reproducible.

Recommended dry-run ladder (validate the whole pipeline before paying for a full run):

  Step 1 — validate eval path + chat contract, no adapter needed:
      modal run finetune/eval.py --baseline-only --limit 5

  Step 2 — quick subset with adapter (after training exists):
      modal run finetune/eval.py --limit 20

  Step 3 — full held-out eval:
      modal run finetune/eval.py
      modal run finetune/eval.py --adapter Aarya2004/minicpmv-cord-lora

With --baseline-only, results.json gets "tuned": null and no delta field — useful for
verifying the base model + chat contract work before training finishes.

The generation prompt is imported from data_utils.PROMPT (no modal dep) — single source
of truth for train/eval parity. Do not hardcode or duplicate it here.
"""

import os

import modal

MODEL = "openbmb/MiniCPM-V-2_6"

# Dataset-selectable like train_modal.py (FF_FT_DATASET=cord|synth) so the same eval
# scores either the CORD test split or the held-out synth/trade test split. Default cord.
DATASET = os.environ.get("FF_FT_DATASET", "cord")
_ADAPTERS = {
    "cord": "Aarya2004/minicpmv-cord-lora",
    "synth": "Aarya2004/minicpmv-trade-lora",
}
# Prefer the LOCAL adapter saved by an unpushed train run (gate-then-publish workflow:
# train --no-push -> eval the local adapter -> push only if better). Falls back to the
# Hub id if no local adapter exists on the volume. (PeftModel.from_pretrained accepts
# either a local dir or a Hub id, so this is a default-resolution convenience.)
LOCAL_ADAPTER_DIR = f"/cache/ft-out/minicpmv-{DATASET}"
ADAPTER_DEFAULT = _ADAPTERS.get(DATASET, f"Aarya2004/minicpmv-{DATASET}-lora")
TEST_MANIFEST = f"/cache/{DATASET}/test.jsonl"
RESULTS_PATH = f"/cache/{DATASET}/results.json"
# Honest label in results.json + printed headers (so synth runs don't say "CORD").
DATASET_LABEL = {
    "cord": "naver-clova-ix/cord-v2",
    "synth": "grounded-synthetic trade invoices",
}.get(DATASET, DATASET)

# Pin environment to MATCH training (RESEARCH.md pinned env):
# cuda 12.1.1 base + python 3.10, same torch/transformers/peft stack used in train_modal.py.
# Mismatched train/eval transformers versions is a silent-skew risk; same pin everywhere.
image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.10")
    .pip_install(
        "numpy<2",  # torch 2.1.2 is built against NumPy 1.x; NumPy 2 crashes its init.
        "torch==2.1.2",
        "torchvision==0.16.2",
        "transformers==4.40.0",
        "accelerate==0.30.1",
        "peft~=0.11.0",
        "sentencepiece==0.1.99",
        "Pillow==10.1.0",
        "timm==0.9.10",
        "huggingface_hub",
    )
    .env({"HF_HOME": "/cache"})
    # Bring the scorer + shared PROMPT + the flash_attn import patch into the image.
    # All three are modal-free; safer to bundle than prepare_data.
    .add_local_python_source("scorer", "data_utils", "flash_patch")
)

vol = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)
app = modal.App("quillwright-ft-eval")


def score_row(answer: str, target: str) -> dict:
    """Pure function: answer string + target JSON string -> per-case score dict.

    Isolated at module scope so it can be unit-tested without torch or modal.
    On any exception, returns a zero-score case (scorer.score([], [])).
    """
    import scorer  # local import keeps torch out of module-level scope

    produced = scorer.parse_items(answer if isinstance(answer, str) else str(answer))
    expected = scorer.parse_items(target)
    return scorer.score(produced, expected)


@app.function(
    image=image,
    gpu="A10G",
    volumes={"/cache": vol},
    secrets=[modal.Secret.from_name("huggingface-secret")],
    timeout=3600,
)
def evaluate(
    adapter: str = ADAPTER_DEFAULT,
    limit: int = 0,
    baseline_only: bool = False,
) -> dict:
    import json
    from unittest.mock import patch

    import torch
    from PIL import Image
    from transformers import AutoModel, AutoTokenizer
    from transformers.dynamic_module_utils import get_imports

    import scorer
    from data_utils import PROMPT  # single source of truth for the instruction
    from flash_patch import make_patched_get_imports

    # MiniCPM-V-2_6's remote code hard-imports flash_attn at load (check_imports), even
    # though we use SDPA. Strip it so the modeling file loads; SDPA handles attention.
    _patched_imports = make_patched_get_imports(get_imports)

    rows = [json.loads(line) for line in open(TEST_MANIFEST)]
    if limit:
        rows = rows[:limit]
    print(f"evaluating on {len(rows)} held-out test rows")

    # --- Load tokenizer (AutoTokenizer, NOT AutoProcessor; chat API wants a tokenizer) ---
    tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)

    # --- Load base model per RESEARCH.md §5 inference contract ---
    # attn_implementation='sdpa' (never 'eager'); torch_dtype=bfloat16 on from_pretrained
    # then .eval().cuda() separately (NOT .to("cuda") with dtype arg).
    with patch("transformers.dynamic_module_utils.get_imports", _patched_imports):
        base = (
            AutoModel.from_pretrained(
                MODEL,
                trust_remote_code=True,
                attn_implementation="sdpa",
                torch_dtype=torch.bfloat16,
            )
            .eval()
            .cuda()
        )

    def _run(model) -> tuple[list[dict], int]:
        """Run inference over all rows; returns (per_case list, failure_count)."""
        per_case = []
        failures = 0
        for r in rows:
            try:
                img = Image.open(r["image"]).convert("RGB")
                # image is FIRST element of content list; image=None as positional kwarg.
                # sampling=False for deterministic greedy output (§5 inference contract).
                msgs = [{"role": "user", "content": [img, PROMPT]}]
                answer = model.chat(image=None, msgs=msgs, tokenizer=tokenizer, sampling=False)
                case = score_row(answer, r["target"])
            except Exception as exc:
                print(f"  [WARN] generation failed for row {r.get('id', '?')}: {exc!r}")
                case = scorer.score([], scorer.parse_items(r["target"]))
                failures += 1
            per_case.append(case)
        return per_case, failures

    # --- baseline: un-tuned MiniCPM-V ----------------------------------------
    baseline_cases, baseline_failures = _run(base)
    baseline = scorer.aggregate(baseline_cases)
    print(f"baseline: {baseline}  (generation_failures={baseline_failures})")

    if baseline_only:
        results = {
            "model": MODEL,
            "adapter": None,
            "dataset": DATASET_LABEL,
            "split": "test",
            "n": baseline["n"],
            "baseline": baseline,
            "tuned": None,
            "generation_failures": baseline_failures,
        }
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2)
        vol.commit()
        print(f"\n=== {DATASET_LABEL} line-item extraction: baseline only ===")
        for k in ("item_f1", "qty_accuracy", "price_accuracy"):
            print(f"{k:<16}{baseline[k]:>12}")
        return results

    # --- tuned: wrap base with LoRA adapter; re-use the already-loaded base weights ---
    # PeftModel.from_pretrained(base, adapter_path, trust_remote_code=True) is the
    # documented pattern (RESEARCH.md §5 + finetune readme). .eval().cuda() after.
    # If the caller didn't override --adapter and a LOCAL (unpushed) adapter exists on
    # the volume, prefer it — that's the gate-then-publish path (eval before pushing).
    if adapter == ADAPTER_DEFAULT and os.path.exists(
        os.path.join(LOCAL_ADAPTER_DIR, "adapter_config.json")
    ):
        adapter = LOCAL_ADAPTER_DIR
        print(f"using local (unpushed) adapter: {adapter}")
    from peft import PeftModel

    tuned_model = PeftModel.from_pretrained(base, adapter, trust_remote_code=True).eval().cuda()
    tuned_cases, tuned_failures = _run(tuned_model)
    tuned = scorer.aggregate(tuned_cases)
    print(f"tuned: {tuned}  (generation_failures={tuned_failures})")

    results = {
        "model": MODEL,
        "adapter": adapter,
        "dataset": DATASET_LABEL,
        "split": "test",
        "n": baseline["n"],
        "baseline": baseline,
        "tuned": tuned,
        "delta_item_f1": round(tuned["item_f1"] - baseline["item_f1"], 3),
        "generation_failures": baseline_failures + tuned_failures,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    vol.commit()

    print(f"\n=== {DATASET_LABEL} line-item extraction: baseline vs tuned ===")
    print(f"{'metric':<16}{'baseline':>12}{'tuned':>12}")
    for k in ("item_f1", "qty_accuracy", "price_accuracy"):
        print(f"{k:<16}{baseline[k]:>12}{tuned[k]:>12}")
    print(f"\ndelta_item_f1: +{results['delta_item_f1']}  (n={results['n']})")
    return results


@app.local_entrypoint()
def main(
    adapter: str = ADAPTER_DEFAULT,
    limit: int = 0,
    baseline_only: bool = False,
):
    evaluate.remote(adapter=adapter, limit=limit, baseline_only=baseline_only)
