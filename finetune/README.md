# Quillwright fine-tune — MiniCPM-V on CORD (🎯 Well-Tuned quest)

The one shipped fine-tune (ADR-0006 + ADR-0009): a small vision model that turns a
**document image → structured line-item JSON**, reported as **baseline-vs-tuned
field-level F1** on a held-out split of a public benchmark, with the tuned model
published to the Hub.

This directory is self-contained: dataset prep, the Modal training job, and the
eval harness. It does **not** import from `quillwright/` — the fine-tune is a
parallelizable artifact that doesn't block the app (ADR-0007 cut order).

## Decisions (researched + de-risked 2026-06-12 — full spec with sources in RESEARCH.md)

| Choice            | What                                                                           | Why                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Model**         | `openbmb/MiniCPM-V-2_6`                                                        | Honors ADR-0006; protects the OpenBMB $10k track (MiniCPM-V is the live Perception model)                                                                                                                                                                                        |
| **Recipe**        | **OpenBMB's official scripts (vendored), single-GPU, NO DeepSpeed, bf16 LoRA** | TRL `SFTTrainer` was researched and REJECTED — no working example exists; the model's custom `forward(data=dict)` + list-shaped `pixel_values`/`image_bound`/`tgt_sizes` cannot be produced by any generic collator (RESEARCH.md §2). 4-bit QLoRA is broken for this model (§1). |
| **Env pin**       | `transformers==4.40.0`, torch 2.1.2, py3.10 (full list in `train_modal.py`)    | The only first-party-"tested" stack for 2_6; 4.46/4.47/5.x break the remote code (§1)                                                                                                                                                                                            |
| **GPU**           | **L40S 48GB** (not A10G)                                                       | OpenBMB's 13–14 GiB table is DeepSpeed-Zero-3-sharded, not single-GPU; 48GB removes OOM risk (§4)                                                                                                                                                                                |
| **Dataset**       | `naver-clova-ix/cord-v2`                                                       | Loads via `load_dataset`; `gt_parse` is the structured target. 800 train / 100 test                                                                                                                                                                                              |
| **Infra**         | **Modal GPU** (mirrors `quillwright/backends/modal_*.py`)                      | Modal credits available; no HF Jobs credits                                                                                                                                                                                                                                      |
| **Vendored code** | `vendor/{finetune,dataset,trainer}.py` @ `cd64150b` (V-2_6 era, Apache-2.0)    | `main` drifted to the o-2.6/V-4 env; this SHA is the last V-2_6-era finetune state (vendor/README)                                                                                                                                                                               |

> **ADR-0006 amendment pending:** ADR-0006 names "OpenBMB's official LoRA recipe" —
> which we now follow more literally than first planned (vendored scripts), but
> single-GPU/no-DeepSpeed on **Modal** rather than their multi-A100 launch. Record
> this in an ADR update before claiming the quest in submission copy.

## The deliverable is the EVAL, not just the model

The 🎯 artifact is the **measured gain**: un-tuned MiniCPM-V vs the LoRA-tuned model
on the CORD **test** split, field-level F1 (item names + prices/quantities). That
number is also the 📓 Field-Notes graph. The eval is deterministic and scriptable
(ADR-0006): `eval.py` runs both models over the same held-out manifest; `scorer.py`
(pure, unit-tested) turns generations into the headline numbers.

## Files

```
finetune/
├── README.md            # this file
├── RESEARCH.md          # the sourced implementation spec (read before touching the recipe)
├── prepare_data.py      # Modal (CPU): CORD-v2 -> images + {train,test}.jsonl on the shared volume
├── train_modal.py       # Modal (L40S): drives vendor/finetune.py; --smoke first; pushes adapter to Hub
├── eval.py              # Modal (A10G): baseline vs tuned on the test split -> results.json + table
├── scorer.py            # field-level F1 / qty / price (pure, GPU-free)
├── data_utils.py        # PROMPT + target/manifest/OpenBMB-format transforms (single source of truth)
├── test_*.py            # 28 unit tests incl. the train-target <-> scorer round-trip contracts
├── vendor/              # OpenBMB finetune.py/dataset.py/trainer.py @ cd64150b (see vendor/README.md)
└── requirements.txt     # reference list; the AUTHORITATIVE pins live in train_modal.py's image
```

## The dry-run ladder (run in THIS order — each rung is cheap and catches a failure class)

1. **Local (free):** `pytest finetune/ -q` + the import-check — pure logic + Modal app construction.
2. **Prep (CPU, ~cents):** `modal run finetune/prepare_data.py` — materializes CORD; crashes here are
   data-shape bugs, not GPU spend. Inspect with `modal volume ls quillwright-hf-cache cord`.
3. **Baseline eval dry-run (~$0.20):** `modal run finetune/eval.py --baseline-only --limit 5` —
   proves the env pins import, the model loads, and the `chat()` contract works, BEFORE any training.
4. **Training smoke (~$0.50):** `modal run finetune/train_modal.py --smoke` — 2 steps on 8 images:
   asserts trainable-params sanity, finite loss, logs peak VRAM, then loads the 2-step adapter and
   runs one real `chat()` — training AND inference contracts proven in one cheap run.
5. **Full run (only after 1–4 are green):** `modal run finetune/train_modal.py` then
   `modal run finetune/eval.py` → `results.json` with the baseline-vs-tuned delta.

## Remaining unverified risks (closable only by rungs 3–4; see agents' notes + RESEARCH.md)

- `peft==0.11.1` with transformers 4.40.0 as an exact combo (rung 3/4 surfaces in seconds).
- `model.chat()` on the PeftModel-wrapped 2_6 (the rung-4 bonus guard exists for exactly this).
- Single-GPU peak VRAM (rung 4 logs `torch.cuda.max_memory_allocated()` — downgrade L40S→A10G only after reading it).
- Subprocess/image layout on Modal (`vendor/` dir + `data_utils` co-residency) — rung 4's first seconds.
