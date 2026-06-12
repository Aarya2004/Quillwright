"""LoRA SFT of MiniCPM-V-2_6 on CORD line-item extraction, on Modal (ADR-0006).

Recipe (the de-risked one — see finetune/RESEARCH.md, the authoritative spec):
**OpenBMB's own `finetune.py` + custom `CPMTrainer`, single GPU, NO DeepSpeed,
bf16 LoRA (NOT 4-bit), on L40S 48GB.** The vendored scripts live in
`finetune/vendor/` (SHA + Apache-2.0 attribution in their headers and
`vendor/README.md`). This file is just the Modal driver: it builds the pinned
V-2_6 image, materializes the training JSON from the prepared manifest, then
shells out to `finetune.py` as a single process.

Why NOT TRL / 4-bit (one line): no working MiniCPM-V + TRL `SFTTrainer` exists,
the model's `forward` needs OpenBMB's custom collator (`data=<dict>` call shape),
and `--q_lora` is effectively broken on 2_6 — full reasoning in RESEARCH.md §2/§1.

Pinned env (RESEARCH.md "Pinned environment", primary): python 3.10, torch 2.1.2,
transformers 4.40.0, accelerate 0.30.1, peft 0.11.1, timm 0.9.10, sentencepiece
0.1.99, Pillow 10.1.0. NO trl / bitsandbytes / flash-attn / deepspeed / datasets
at train time.

DE-RISK FIRST — never launch a full (paid) run blind. Smoke first:
    modal run finetune/train_modal.py --smoke
~8 images, max_steps=2, on the target GPU. It asserts the RESEARCH.md smoke
contract (trainable params > 0 and < 5% of total; finite loss; logs peak VRAM)
AND the bonus guard (loads the 2-step adapter via PeftModel + one model.chat()
round trip) so training AND inference contracts are proven in one cheap run.
Only once smoke is green:
    modal run finetune/train_modal.py

Prereqs:
    - prepare_data.py has run (volume has /cache/cord/{train,test}.jsonl + images)
    - the `huggingface-secret` Modal secret exists (HF_TOKEN, WRITE scope for the
      Hub push) — same secret the inference apps use.
"""

import os

import modal

_HERE = os.path.dirname(os.path.abspath(__file__))

MODEL = "openbmb/MiniCPM-V-2_6"
LLM_TYPE = "qwen2"  # 2_6's LLM is Qwen2 (finetune_lora.sh at the vendored SHA).
HUB_MODEL_ID_DEFAULT = "Aarya2004/minicpmv-cord-lora"  # adapter repo to push to

# Paths inside the container.
MANIFEST = "/cache/cord/train.jsonl"
TRAIN_JSON = "/cache/cord/openbmb_train.json"  # converted, what finetune.py reads
OUTPUT_DIR = "/cache/ft-out/minicpmv-cord"

# LoRA target regex — the finetune_lora.sh form WITH o_proj, scoped to the LLM
# (`llm.` prefix) so the vision tower + resampler stay frozen (RESEARCH.md §3).
LORA_TARGET = r"llm\..*layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)"

# RESEARCH.md "Pinned environment" — primary, single-GPU bf16 LoRA, V-2_6 stack.
# python 3.10 + torch 2.1.2 wheels are cu121, so the CUDA base is 12.1.1-devel.
image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.10")
    .pip_install(
        "numpy<2",  # torch 2.1.2 is built against NumPy 1.x; NumPy 2 crashes its init.
        "torch==2.1.2",
        "torchvision==0.16.2",
        "transformers==4.40.0",  # V-2_6 "tested" pin; NOT 4.46/4.47/5.x
        "accelerate==0.30.1",
        "peft==0.11.1",  # era-matched to 4.40.0 (RESEARCH.md: peft~=0.11.x)
        "sentencepiece==0.1.99",
        "Pillow==10.1.0",
        "timm==0.9.10",
        "huggingface_hub",
        # NO trl, NO bitsandbytes, NO flash-attn, NO deepspeed, NO datasets:
        # the vendored finetune path uses a custom JSON loader + SDPA attention.
    )
    .env({"HF_HOME": "/cache"})
    # data_utils.py (the converter + PROMPT) and the vendored OpenBMB scripts
    # must be importable / runnable inside the container.
    .add_local_python_source("data_utils", "flash_patch")
    .add_local_dir(
        # vendor/ holds finetune.py, dataset.py, trainer.py — copied to /root/vendor
        # so we can `python /root/vendor/finetune.py ...` as a single process.
        os.path.join(_HERE, "vendor"),
        remote_path="/root/vendor",
    )
)

vol = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)
app = modal.App("quillwright-ft-train")


@app.function(
    image=image,
    gpu="L40S",  # RESEARCH.md §4: 48GB removes single-GPU bf16-LoRA OOM as a
    # first-run failure mode (the 14GiB table number was DeepSpeed-Zero3-sharded).
    volumes={"/cache": vol},
    secrets=[modal.Secret.from_name("huggingface-secret")],
    timeout=14400,  # 4h ceiling: cold start + weight pull + train + Hub push.
)
def train(smoke: bool = False, hub_model_id: str = HUB_MODEL_ID_DEFAULT):
    import json
    import os
    import subprocess
    import sys

    sys.path.insert(0, "/root/vendor")  # so finetune.py can `import dataset/trainer`

    from data_utils import manifest_rows, to_openbmb_examples

    # --- materialize the OpenBMB-format training JSON ------------------------
    rows = manifest_rows(MANIFEST)
    if smoke:
        rows = rows[:8]
    examples = to_openbmb_examples(rows)
    os.makedirs(os.path.dirname(TRAIN_JSON), exist_ok=True)
    with open(TRAIN_JSON, "w") as f:
        json.dump(examples, f, ensure_ascii=False)
    print(f"wrote {len(examples)} OpenBMB examples -> {TRAIN_JSON} (smoke={smoke})")

    # --- drive the vendored finetune.py single-process (no torchrun, no DS) ---
    # Flags per RESEARCH.md §3: LLM-only bf16 LoRA, vision frozen, r=alpha=64,
    # dropout 0.05, lr 1e-5, model_max_length 2048, batch 1, grad-accum 8,
    # gradient checkpointing. NO --deepspeed.
    cmd = [
        sys.executable,
        "/root/vendor/finetune.py",
        "--model_name_or_path",
        MODEL,
        "--llm_type",
        LLM_TYPE,
        "--data_path",
        TRAIN_JSON,
        "--output_dir",
        OUTPUT_DIR,
        "--use_lora",
        "true",
        "--tune_vision",
        "false",
        "--tune_llm",
        "false",
        "--lora_target_modules",
        LORA_TARGET,
        "--lora_r",
        "64",
        "--lora_alpha",
        "64",
        "--lora_dropout",
        "0.05",
        "--model_max_length",
        "2048",
        "--max_slice_nums",
        "9",
        "--bf16",
        "true",
        "--bf16_full_eval",
        "true",
        "--fp16",
        "false",
        "--do_train",
        "--per_device_train_batch_size",
        "1",
        "--gradient_accumulation_steps",
        "8",
        "--gradient_checkpointing",
        "true",
        "--learning_rate",
        "1e-5",
        "--weight_decay",
        "0.1",
        "--adam_beta2",
        "0.95",
        "--warmup_ratio",
        "0.01",
        "--lr_scheduler_type",
        "cosine",
        "--logging_steps",
        "1",
        "--save_strategy",
        "no" if smoke else "epoch",
        "--report_to",
        "none",
        "--remove_unused_columns",
        "false",
        "--label_names",
        "labels",
    ]
    if smoke:
        cmd += ["--max_steps", "2"]
    else:
        cmd += ["--num_train_epochs", "3"]

    # finetune.py imports its sibling dataset/trainer by bare name -> run with
    # cwd=/root/vendor so those imports resolve, but keep data_utils importable
    # via PYTHONPATH (the local-source dir Modal injected).
    env = dict(os.environ)
    env["PYTHONPATH"] = "/root/vendor:" + env.get("PYTHONPATH", "")
    print("launching:", " ".join(cmd))
    subprocess.run(cmd, cwd="/root/vendor", env=env, check=True)
    vol.commit()

    if smoke:
        _smoke_assert_and_chat()
        print("SMOKE OK — training + inference contracts proven (see asserts above).")
        return

    # --- full run: push the adapter folder to the Hub -----------------------
    _push_adapter(hub_model_id)
    print(f"pushed adapter -> https://huggingface.co/{hub_model_id}")


def _adapter_dir() -> str:
    """Resolve the saved adapter dir (finetune.py saves to OUTPUT_DIR, possibly
    in a checkpoint-* subdir if save_strategy produced one)."""
    import glob
    import os

    if os.path.exists(os.path.join(OUTPUT_DIR, "adapter_config.json")):
        return OUTPUT_DIR
    cks = sorted(glob.glob(os.path.join(OUTPUT_DIR, "checkpoint-*")))
    for ck in reversed(cks):
        if os.path.exists(os.path.join(ck, "adapter_config.json")):
            return ck
    return OUTPUT_DIR


def _smoke_assert_and_chat():
    """RESEARCH.md smoke contract + bonus guard, run after the 2-step subprocess.

    Re-runs the recipe's model-load path in-process to assert:
      1. trainable params > 0 and < 5% of total (LoRA hit the LLM, not nothing /
         not the whole vision tower) — RESEARCH.md failure mode #4.
      2. peak VRAM is logged (torch.cuda.max_memory_allocated) — failure mode #3.
      3. the saved 2-step adapter loads via PeftModel and a single model.chat()
         round-trips on a real test image — the inference contract (RESEARCH.md §5).
    Loss finiteness is asserted by the subprocess itself: finetune.py would raise
    on a non-finite loss path, and `check=True` propagates any non-zero exit.
    """
    import json
    from unittest.mock import patch

    import torch
    from peft import PeftModel
    from PIL import Image
    from transformers import AutoModel, AutoTokenizer
    from transformers.dynamic_module_utils import get_imports

    from data_utils import PROMPT
    from flash_patch import make_patched_get_imports

    adapter = _adapter_dir()
    print(f"[smoke] loading adapter from {adapter}")

    torch.cuda.reset_peak_memory_stats()
    # Same flash_attn import-check workaround as the training subprocess (vendor/finetune.py)
    # and eval.py — strip flash_attn so the remote modeling file loads; SDPA does attention.
    with patch(
        "transformers.dynamic_module_utils.get_imports",
        make_patched_get_imports(get_imports),
    ):
        base = AutoModel.from_pretrained(
            MODEL,
            trust_remote_code=True,
            attn_implementation="sdpa",  # RESEARCH.md §5: sdpa or fa2, never eager.
            torch_dtype=torch.bfloat16,
        )
    tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)

    lora_model = PeftModel.from_pretrained(base, adapter, trust_remote_code=True).eval().cuda()

    # --- trainable-param assertion (failure mode #4) ------------------------
    trainable = sum(p.numel() for p in lora_model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in lora_model.parameters())
    pct = 100.0 * trainable / total if total else 0.0
    print(f"[smoke] trainable={trainable:,} total={total:,} ({pct:.3f}%)")
    assert trainable > 0, "LoRA targeted nothing (0 trainable params)"
    assert pct < 5.0, f"trainable% too high ({pct:.2f}%) — vision tower likely unfrozen"

    # --- inference round trip (bonus guard, RESEARCH.md §5) -----------------
    rows = [json.loads(line) for line in open(MANIFEST)]
    img_path = rows[0]["image"]
    img = Image.open(img_path).convert("RGB")
    msgs = [{"role": "user", "content": [img, PROMPT]}]  # image INSIDE content list
    answer = lora_model.chat(image=None, msgs=msgs, tokenizer=tokenizer)
    print(f"[smoke] model.chat() round trip OK, answer[:120]={str(answer)[:120]!r}")

    peak = torch.cuda.max_memory_allocated() / (1024**3)
    print(f"[smoke] torch.cuda.max_memory_allocated = {peak:.2f} GiB")


def _push_adapter(hub_model_id: str):
    """Push the LoRA adapter folder + a minimal model card to the Hub."""
    import os

    from huggingface_hub import HfApi, upload_folder

    adapter = _adapter_dir()
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    card = f"""---
base_model: {MODEL}
library_name: peft
tags:
- lora
- minicpm-v
- document-understanding
- receipt-extraction
datasets:
- naver-clova-ix/cord-v2
---

# MiniCPM-V-2_6 LoRA — CORD line-item extraction

LoRA adapter for `{MODEL}`: receipt/document image -> structured line-item JSON
(`{{"menu": [{{"nm","cnt","price"}}], "total": ...}}`).

- **Base model:** `{MODEL}`
- **Dataset:** `naver-clova-ix/cord-v2` (train split; held-out test for eval)
- **Recipe:** OpenBMB official `finetune.py` + `CPMTrainer`, single-GPU,
  no DeepSpeed, bf16 LoRA (not 4-bit). LoRA on the LLM self-attention
  projections (q/k/v/o) only; vision tower + resampler frozen.
  r=64, alpha=64, dropout=0.05, lr=1e-5, model_max_length=2048.
- **Eval:** baseline-vs-tuned field-level F1 lives in the Quillwright repo
  (`finetune/eval.py` + `finetune/scorer.py`), not here.

## Inference

```python
from peft import PeftModel
from transformers import AutoModel, AutoTokenizer
base = AutoModel.from_pretrained("{MODEL}", trust_remote_code=True,
                                 attn_implementation="sdpa")
model = PeftModel.from_pretrained(base, "{hub_model_id}",
                                  trust_remote_code=True).eval().cuda()
tok = AutoTokenizer.from_pretrained("{MODEL}", trust_remote_code=True)
# model.chat(image=None, msgs=[{{"role":"user","content":[img, PROMPT]}}], tokenizer=tok)
```
"""
    card_path = os.path.join(adapter, "README.md")
    with open(card_path, "w") as f:
        f.write(card)

    HfApi(token=token).create_repo(hub_model_id, exist_ok=True)
    upload_folder(folder_path=adapter, repo_id=hub_model_id, token=token)


@app.local_entrypoint()
def main(smoke: bool = False, hub_model_id: str = HUB_MODEL_ID_DEFAULT):
    train.remote(smoke=smoke, hub_model_id=hub_model_id)
