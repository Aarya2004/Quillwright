# Vendored OpenBMB MiniCPM-V finetune scripts (V-2_6 era)

These three files are copied **verbatim** (modulo the marked edits below) from
OpenBMB's official MiniCPM-V finetune scripts. They are the primary training
recipe per `finetune/RESEARCH.md` §2(b): drive `finetune.py` + the custom
`CPMTrainer` single-GPU, **no DeepSpeed**, bf16 LoRA (not 4-bit). `train_modal.py`
shells out to `finetune.py` inside a Modal L40S container.

## Provenance

| Field            | Value                                                                                                             |
| ---------------- | ----------------------------------------------------------------------------------------------------------------- |
| Repo             | https://github.com/OpenBMB/MiniCPM-V                                                                              |
| **Commit (SHA)** | `cd64150b5122f8ee8c677d481c97918485129b52`                                                                        |
| Commit msg       | "update finetuen for multi images sft (#462)" (2024-08-15)                                                        |
| License          | Apache-2.0 — https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/cd64150b5122f8ee8c677d481c97918485129b52/LICENSE |

Raw source URLs (fetched at that SHA):

- `finetune.py` — https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/cd64150b5122f8ee8c677d481c97918485129b52/finetune/finetune.py
- `dataset.py` — https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/cd64150b5122f8ee8c677d481c97918485129b52/finetune/dataset.py
- `trainer.py` — https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/cd64150b5122f8ee8c677d481c97918485129b52/finetune/trainer.py

## Why this exact SHA (the "repo drift" trap, RESEARCH.md §1)

`OpenBMB/MiniCPM-V` `main` has been re-pointed to the unified MiniCPM-o-2.6 / V-4
codebase, whose `finetune/requirements.txt` now pins `transformers==4.51.2` — the
**wrong** environment for MiniCPM-V-2_6.

The `finetune/requirements.txt` path did **not exist** in the V-2_6 era (the four
commits that ever touched it all start at the o-2.6 landing, `53c0174`, and pin
`transformers==4.44.2`+, never 4.40.0). In the V-2_6 era the deps lived in the
**repo-root** `requirements.txt`. At the chosen SHA `cd64150`:

- root `requirements.txt` pins **`transformers==4.40.0`**, `torch==2.1.2`,
  `torchvision==0.16.2`, `accelerate==0.30.1`, `sentencepiece==0.1.99`,
  `Pillow==10.1.0`, `timm==0.9.10` — the V-2_6 "tested" stack (model card).
- `finetune/requirements.txt` is `404` (confirming it post-dates this era).

`cd64150` is the **last** finetune-touching commit before `53c0174` ("Update to
MiniCPM-o 2.6", 2025-01-14) drifted the repo. It is V-2_6 + V-2_5 + V-2 era and
includes multi-image SFT support. `finetune_lora.sh` at this SHA already defaults
`MODEL="openbmb/MiniCPM-V-2_6"` and `LLM_TYPE="qwen2"` — exactly our target.

## Modifications from upstream

Each edit is marked inline with a `# QUILLWRIGHT EDIT:` comment. They are the
minimal changes to run **single-GPU without DeepSpeed**:

- **`finetune.py`** — the top-level `from deepspeed import zero` /
  `from deepspeed.runtime.zero.partition_parameters import ZeroParamStatus` and
  `from transformers.integrations import deepspeed` imports are wrapped in
  `try/except` (set to `None` on failure). `zero`/`ZeroParamStatus` are imported
  by upstream but never referenced; `deepspeed.is_deepspeed_zero3_enabled()` is
  only reached inside the `q_lora` branch, which we never enter (`--q_lora false`).
  This lets the image omit the heavy `deepspeed` dependency.
- **`trainer.py`** — the top-level `import deepspeed` and
  `from transformers.integrations import is_deepspeed_zero3_enabled` are wrapped
  in `try/except`. Neither symbol is referenced anywhere in `CPMTrainer`'s body.

No other lines were changed. The `init_vision` / `init_audio` / `init_tts`
kwargs that RESEARCH.md flagged as UNVERIFIED are **absent** at this SHA —
`from_pretrained` here takes only `trust_remote_code`, `torch_dtype`,
`device_map` — so no guard for them was needed (this closes that risk).

Every file carries a `# ruff: noqa` header so our lint/format pass does not
rewrite third-party style.

## How `train_modal.py` drives these

`train_modal.py` builds a Modal image with the RESEARCH.md "Pinned environment"
primary stack, adds this `vendor/` dir + `data_utils.py`, then runs
`python finetune.py --model_name_or_path openbmb/MiniCPM-V-2_6 --llm_type qwen2
--use_lora true --tune_vision false --tune_llm false ...` as a single process
(no `torchrun`, no `--deepspeed`). The training data JSON is produced by
`data_utils.to_openbmb_examples`, whose output format matches what
`dataset.py::SupervisedDataset.__getitem__` parses (`{"image": <path str>,
"conversations": [{"role","content"}, ...]}` with a literal `<image>` token in
the first user turn).
