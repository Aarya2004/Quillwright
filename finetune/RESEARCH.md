# MiniCPM-V-2_6 LoRA Fine-tune — Implementation Research

> Deliverable for the downstream engineer who will write the training script. Every
> non-obvious claim has a source URL. Items I could not verify are marked **UNVERIFIED**
> — guard those in code (smoke test / try-except / explicit assert) rather than trusting them.
>
> Target: fine-tune `openbmb/MiniCPM-V-2_6` (8B VLM, custom remote code) with LoRA on
> CORD-v2 (image → structured JSON), on a **single Modal GPU**, first paid run must succeed.

---

## Decision: Mirror OpenBMB's official `finetune.py` + `CPMTrainer`, single-GPU, **no DeepSpeed, bf16 LoRA (NOT 4-bit), on L40S 48GB**

The current scaffold (`finetune/train_modal.py`) uses **TRL `SFTTrainer` + 4-bit QLoRA**. Research says this is the **highest-risk** path and should be abandoned for the first paid run. Three independent facts kill it:

1. **No working MiniCPM-V + TRL `SFTTrainer` example exists anywhere** (GitHub/blogs/HF forums searched — none found; the closest write-ups all fall back to OpenBMB's own scripts). TRL's VLM collator drives the model through `processor(...)` + `model(**inputs)`, but MiniCPM-V-2_6's remote code does **not** use a standard processor or a standard `forward(input_ids=..., pixel_values=...)` signature. OpenBMB wrote a **custom `CPMTrainer`** precisely because the default Trainer loss path does not work — its `compute_loss` calls `self.model(data=inputs, use_cache=False)` (note: a single `data=` dict, not `**inputs`) and computes cross-entropy by hand. TRL cannot produce that call shape. (Sources in §2.)
2. **The model's `forward` expects keys no standard collator produces** — `image_bound`, `tgt_sizes`, and a `pixel_values` that is a _list of variable-size patch tensors_, plus `position_ids`, built by OpenBMB's `conversation_to_ids` + image-slicing in `dataset.py`. A generic VLM collator emits `pixel_values` as a single padded `[B,3,H,W]` tensor — wrong shape, instant failure. (Sources in §2.)
3. **4-bit QLoRA on MiniCPM-V-2_6 is UNVERIFIED and the official `--q_lora` flag is effectively broken** — `finetune.py` never passes a `BitsAndBytesConfig`/`load_in_4bit` to `from_pretrained`, so `--q_lora true` runs `prepare_model_for_kbit_training` on a _non-quantized_ model. The one community QLoRA-on-2.6 attempt failed with `TypeError: device() received an invalid combination of arguments` and was never fixed. (§1, §4.) Don't gamble a paid run on it.

**Chosen recipe, lowest first-run risk:** copy OpenBMB's `finetune/{finetune.py, dataset.py, trainer.py}` into the Modal image, drive them with their `HfArgumentParser` CLI but **without DeepSpeed** (`finetune.py` only invokes DeepSpeed `if training_args.deepspeed` is set — it is not hard-required; `world_size` defaults to 1). Use **bf16 LoRA** (`--tune_llm false --tune_vision false`, LoRA on the LLM attention projections only — vision tower frozen). This is the only path with a first-party "tested" provenance.

**A strong, lower-effort fallback if the engineer prefers a packaged tool: LLaMA-Factory** (`pip install llamafactory`, official MiniCPM-V cookbook support, template `minicpm_v`, one-command `llamafactory-cli train config.yaml`). It is pip-installable, debuggable in a container, and the MiniCPM team documents it. It is a reasonable Plan B; the only reason it is not the primary pick is debuggability — when LLaMA-Factory breaks on a version mismatch, you debug _their_ abstraction layer, whereas the OpenBMB scripts are ~3 files you can read end-to-end. Either is far safer than TRL.

**GPU: use L40S 48GB, not A10G 24GB.** OpenBMB's own VRAM table (13–14 GiB LoRA) is measured **with DeepSpeed Zero-3 sharding optimizer/grad/param state across multiple GPUs** — it does **not** represent a single-GPU run, where optimizer + gradients + activations all sit on one card. With image slicing pushing sequences long and bf16 (no 4-bit), A10G 24GB is a real OOM risk. L40S 48GB removes that variable for the first run; drop to A10G later only after a measured single-GPU run shows headroom. (§4.)

---

## 1. Dependency versions (transformers pin, quant)

**Recommended transformers pin for MiniCPM-V-2_6: `transformers==4.40.0`.** This is the only version with a first-party _"tested"_ claim for this specific model.

- Model card "Requirements tested on python 3.10" block lists verbatim: `Pillow==10.1.0`, `torch==2.1.2`, `torchvision==0.16.2`, **`transformers==4.40.0`**, `sentencepiece==0.1.99`, `decord`. Source: https://huggingface.co/openbmb/MiniCPM-V-2_6
- Repo root requirements: `transformers==4.40.0`, `torch==2.1.2`, `torchvision==0.16.2`, `accelerate==0.30.1`, `Pillow==10.1.0`, `sentencepiece==0.1.99`, `timm==0.9.10`, `#flash_attn==2.3.4` (commented out). Source: https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/requirements.txt

**Trap — repo drift:** OpenBMB/MiniCPM-V `main` has been re-pointed to the unified **MiniCPM-o / V-4.0** codebase. Its _current_ `finetune/requirements.txt` now says `transformers==4.51.2`, `torch==2.2.0`, `peft==0.14.0` + audio deps — that is the **o-2.6 / V-4.5 environment, NOT V-2_6**. Do not copy it for 2_6. Source: https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/requirements.txt

- Corroborating cross-version fragility: Issue #969 — V-4_5 remote code fails on transformers 4.44.2 with `ImportError: cannot import name 'Qwen3Config'` (proves 2_6 and 4_5 need _different_ transformers; don't share envs). https://github.com/OpenBMB/MiniCPM-V/issues/969
- transformers **5.x breaks** the remote code (`MiniCPMVBatchFeature` incompatible with the v5 base class). Stay ≤ 4.4x. https://huggingface.co/openbmb/MiniCPM-o-2_6/discussions/30 (related family report; exact 2_6 issue number UNVERIFIED but the v5 break is consistently reported).

**Known-good / known-bad summary:**

- GOOD: **4.40.0** (first-party tested). 4.44.2 works for the _sibling_ o-2.6 but is not the 2_6 tested pin — prefer 4.40.0.
- BAD: 4.46.x / 4.47.x (multimodal template breakage — these are the versions LLaMA-Factory explicitly excludes, §2), and 5.x.

**Companion pins (4.40.0 stack):** `torch==2.1.2`, `torchvision==0.16.2`, `accelerate==0.30.1`, `sentencepiece==0.1.99`, `Pillow==10.1.0`, `timm==0.9.10`. **`peft`** is NOT pinned by any 2_6-era first-party file → use an era-matched `peft~=0.11.x` (**UNVERIFIED** exact pin; smoke-test it). **`datasets`** is NOT a dependency of OpenBMB's finetune path (it uses a custom JSON/JSONL loader, not HF `datasets`) — you only need `datasets` to _download CORD-v2_ in prep, any recent version is fine.

**Python: 3.10** ("Requirements tested on python 3.10" — model card). **flash-attn: OPTIONAL** — model card uses `attn_implementation='sdpa'` with comment "sdpa or flash_attention_2, no eager"; `flash_attn` is commented out in requirements. **Do not require flash-attn** (it needs a long CUDA build in-container); SDPA works. **eager is explicitly unsupported.** Source: https://huggingface.co/openbmb/MiniCPM-V-2_6

**Quant (bitsandbytes 4-bit):** Inference int4 works only via the _pre-quantized_ `openbmb/MiniCPM-V-2_6-int4` checkpoint (needs `bitsandbytes==0.43.1`), loaded plain (no `BitsAndBytesConfig`). https://huggingface.co/openbmb/MiniCPM-V-2_6-int4 . **Load-time QLoRA fine-tuning of the bf16 base is UNVERIFIED / broken** in the stock script (see §4 + Decision). Do not use 4-bit for the first run.

---

## 2. Trainer-path decision (the make-or-break)

### (a) TRL `SFTTrainer` — NO working example; do not use

Exhaustive search (GitHub code search, blogs, HF forums) found **zero** working MiniCPM-V + TRL `SFTTrainer` examples. Every MiniCPM-V finetune write-up routes back to OpenBMB's own scripts (e.g. the Medium "Mastering MiniCPM-V" series, the MiniCPM-o cookbook). The official readme states finetune uses transformers `Trainer` + DeepSpeed. Sources: https://github.com/OpenBMB/MiniCPM-V/blob/main/finetune/readme.md , https://minicpm-o.readthedocs.io/en/latest/finetune/fintune.html . **Plainly: no proven TRL path exists. The scaffold's TRL approach is unproven.**

### (b) OpenBMB official scripts — RECOMMENDED. What they actually do:

Read from `https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/{finetune.py,dataset.py,trainer.py,finetune_lora.sh}` (note repo drift caveat in §1 — the _training logic_ is stable across the family even though defaults now say o-2_6; set `--model_name_or_path openbmb/MiniCPM-V-2_6`).

- **Model load** (`finetune.py`):
  ```python
  model = AutoModel.from_pretrained(
      model_args.model_name_or_path, trust_remote_code=True,
      torch_dtype=compute_dtype, device_map=device_map,
      init_vision=True, init_audio=False, init_tts=False,
  )
  ```
  For 2_6 the `init_audio/init_tts` kwargs may not exist on the older remote code — **UNVERIFIED for 2_6; guard with try/except or drop them** (they exist on the o-2.6 / 4.0 remote code that `main` now targets).
- **Custom trainer** (`trainer.py`, `CPMTrainer`): overrides `compute_loss`. It pops `labels`, then calls **`outputs = self.model(data=inputs, use_cache=False)`** (LoRA: `self.model.base_model(data=inputs, ...)`), flattens logits to `[-1, vocab_size]`, and applies `nn.CrossEntropyLoss()` manually. **This single `data=<dict>` call shape is the reason TRL cannot drive this model.**
- **Collator output** (`dataset.py` → `SupervisedDataset.__getitem__` + `data_collator`): the dict fed to `model.forward` has keys
  ```
  input_ids        [B, L]
  position_ids     [B, L]
  labels           [B, L]   (-100 on context, token ids on assistant turns)
  attention_mask   [B, L]
  pixel_values     list of per-image patch tensors (variable size) — NOT a padded [B,3,H,W]
  tgt_sizes        list of [patches_h, patches_w] per image
  image_bound      list of tensors marking <image> placeholder spans
  ```
  Built by `conversation_to_ids` (produces `input_ids`, `target`, `image_bound`, `position_ids`, `raw_msg`) and `slice_image()` (dynamic grid tiling → `<im_start>...<im_end><slice_start>...` placeholders). A generic collator cannot reproduce `image_bound`/`tgt_sizes`/the list-shaped `pixel_values`.
- **DeepSpeed not hard-required:** `finetune.py` only branches into DeepSpeed when `training_args.deepspeed` is set; `world_size` defaults to 1 when the env var is absent. So `finetune.py` **can run single-GPU without DeepSpeed** — launch it as a plain `python finetune.py ...` (no `torchrun`, no `--deepspeed`). This is the key enabler for the single-GPU plan.

### (c) LLaMA-Factory — strong fallback, fully pip-installable

- **Supported:** YES. README "[25/01/14] We supported fine-tuning ... MiniCPM-V-2.6". Code registry `src/llamafactory/extras/constants.py`: `"MiniCPM-V-2.6" → DEFAULT "openbmb/MiniCPM-V-2_6"`, `template="minicpm_v"`. Sources: https://github.com/hiyouga/LLaMA-Factory/blob/main/README.md , https://raw.githubusercontent.com/hiyouga/LLaMA-Factory/main/src/llamafactory/extras/constants.py
- **Install:** `pip install llamafactory` (PyPI package `llamafactory`, latest **0.9.5**, Python ≥3.11). For MiniCPM-V the cookbook uses the editable+extra install: `pip install -e ".[torch,metrics,deepspeed,minicpm_v]"`. CLI is `llamafactory-cli`. Sources: https://pypi.org/pypi/llamafactory/json , https://raw.githubusercontent.com/OpenSQZ/MiniCPM-V-CookBook/main/finetune/llamafactory/finetune_llamafactory.md
- **Dataset format** (sharegpt-style, `images` field):
  ```json
  {
    "messages": [
      { "content": "<image>extract the receipt", "role": "user" },
      { "content": "{...json...}", "role": "assistant" }
    ],
    "images": ["data/img/0001.jpg"]
  }
  ```
  Rule: one `<image>` tag per entry in `images`.
- **`dataset_info.json` entry:**
  ```json
  "cord": {"file_name":"cord.json","formatting":"sharegpt",
           "columns":{"messages":"messages","images":"images"},
           "tags":{"role_tag":"role","content_tag":"content","user_tag":"user","assistant_tag":"assistant"}}
  ```
- **LoRA SFT YAML** (set `model_name_or_path: openbmb/MiniCPM-V-2_6`):
  ```yaml
  model_name_or_path: openbmb/MiniCPM-V-2_6
  trust_remote_code: true
  stage: sft
  do_train: true
  finetuning_type: lora
  lora_target: q_proj,v_proj
  dataset: cord
  template: minicpm_v # do not change
  cutoff_len: 3072
  output_dir: saves/minicpmv/lora/sft
  per_device_train_batch_size: 2
  gradient_accumulation_steps: 1
  learning_rate: 1.0e-5
  num_train_epochs: 3.0
  lr_scheduler_type: cosine
  warmup_ratio: 0.1
  bf16: true
  ```
  Single-GPU command: **`llamafactory-cli train config.yaml`**. Merge after: `llamafactory-cli export merge.yaml`.
- **Freezing:** defaults `freeze_vision_tower=True`, `freeze_multi_modal_projector=True`, `freeze_language_model=False` → LoRA lands on the LLM, vision frozen. `lora_target` default is `"all"` (LLM linears) but the cookbook pins `q_proj,v_proj`. (`train_mm_proj_only` is NOT a LLaMA-Factory flag.) Source: https://raw.githubusercontent.com/hiyouga/LLaMA-Factory/main/src/llamafactory/hparams/finetuning_args.py
- **Version coupling (the gotcha):** LLaMA-Factory's transformers range is version-specific. 0.9.5 pins `transformers>=4.55.0,<=5.6.0,!=4.52.0,!=4.57.0`; **0.9.3 pins `transformers>=4.45.0,<=4.52.4,!=4.46.*,!=4.47.*,!=4.48.0,!=4.52.0`**. The `!=4.46.*,!=4.47.*` exclusions exist because those releases broke multimodal templates (corroborates §1). Known breakage: Issue #6968 (VL template + transformers 4.49.0.dev0 `shard_checkpoint` import error), Issue #7678 (`minicpm_v` extra vs `sglang` extra transformers conflict), Issue #9364 (transformers 5.0 incompat). Sources: https://raw.githubusercontent.com/hiyouga/LLaMA-Factory/main/pyproject.toml , https://github.com/hiyouga/LLaMA-Factory/issues/6968 , https://github.com/hiyouga/LLaMA-Factory/issues/7678 , https://github.com/hiyouga/LLaMA-Factory/issues/9364
  - **UNVERIFIED:** no single issue states an exact "MiniCPM-V-2_6 + transformers X.Y.Z confirmed" tuple. If using LLaMA-Factory, pin **LLaMA-Factory 0.9.3 + transformers 4.49.0** (in-range, excludes the bad ones) and smoke-test.

**Recommendation:** primary = (b) OpenBMB scripts no-DeepSpeed bf16 LoRA. fallback = (c) LLaMA-Factory 0.9.3. **Never (a) TRL.**

---

## 3. LoRA target modules + hyperparameters (from OpenBMB)

From `finetune.py` + `finetune_lora.sh`:

- **`target_modules` (regex):** `r"llm\..*layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)"` — note the `finetune_lora.sh` regex includes **`o_proj`**; `finetune.py`'s in-code default regex shows `(q_proj|k_proj|v_proj)`. Use the shell-script form **with `o_proj`** (it is the documented launch config). The `llm\.` prefix is critical — it scopes LoRA to the **language model only**, leaving `vpm` (vision) + `resampler` untouched.
- **r / alpha / dropout:** `lora_r=64`, `lora_alpha=64`, `lora_dropout=0.05` (in-code defaults).
- **learning_rate:** `1e-6` (shell script). NOTE this is for `--tune_vision true`; for an LLM-only LoRA you can raise it (LLaMA-Factory cookbook uses `1e-5`). Pick **`1e-5`** for LLM-only LoRA.
- **model_max_length:** `2048`. **per_device_train_batch_size:** `1`. **gradient_accumulation_steps:** `1` (raise to 4–8 on single GPU to keep effective batch reasonable).
- **Vision/resampler freezing:** controlled by `--tune_vision` / `--tune_llm`. Under LoRA, `modules_to_save = ['embed_tokens','resampler']` and `model.vpm.requires_grad_(False)` when `tune_vision` is off; `'vpm'` is appended to `modules_to_save` only if `tune_vision` is on. **For lowest-risk single-GPU: `--tune_vision false`** → vision encoder frozen, LoRA on LLM attention, `embed_tokens`+`resampler` saved.

Sources: https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/finetune.py , https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/finetune_lora.sh

> **Caveat:** `finetune_lora.sh` defaults `MODEL="openbmb/MiniCPM-o-2_6"` (2_6 line commented) and `--deepspeed ds_config_zero2.json`, `nproc_per_node=8`. You must override: `model_name_or_path=openbmb/MiniCPM-V-2_6`, **drop `--deepspeed`**, launch as single-process `python finetune.py`.

---

## 4. VRAM reality → use L40S 48GB for the first run

- **OpenBMB README table** (max_length 2048, batch 1, **DeepSpeed Zero-3**): LoRA = **13.1–14.4 GiB** (8/4/2 GPUs); full = ~15.6–16.0 GiB. Source: https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/readme.md
- **Why that number does NOT mean "fits A10G 24GB single-GPU":** Zero-3 _shards optimizer state, gradients, and parameters across the GPUs_ — the per-GPU figure assumes that sharding. On **one** GPU with no DeepSpeed, optimizer + gradients + the full bf16 params + activations all sit on the single card. Real single-GPU bf16-LoRA footprint for an 8B model is materially higher than 14 GiB, and CORD image slicing lengthens sequences (more activation memory). External single-GPU 7–8B LoRA guidance puts you in the high-teens-to-20s GiB with bf16+grad-checkpoint, which is uncomfortably close to A10G's 24 GiB ceiling once a custom VLM collator and image patches are added.
- **4-bit/QLoRA path** that would shrink this is **UNVERIFIED/broken for 2_6** (§1) — not a safe lever for the first run.

**Verdict: provision L40S 48GB (`gpu="L40S"`) for the first paid run**, `per_device_train_batch_size=1`, `gradient_accumulation_steps=4–8`, `gradient_checkpointing=True`, `max_length=2048`. Rationale: budget is dominated by a _failed_ run, not by L40S-vs-A10G hourly delta; 48 GiB removes OOM as a first-run failure mode. After one successful measured run, read peak VRAM and downgrade to A10G only if it shows clear headroom. **UNVERIFIED:** exact single-GPU peak for 2_6 LoRA — measure it (the smoke test should log `torch.cuda.max_memory_allocated()`). Sources: https://willitrunai.com/models/minicpm-v-2.6-8b (8B size context) + reasoning above.

---

## 5. Eval inference contract

**Base-model chat** (from model card — https://huggingface.co/openbmb/MiniCPM-V-2_6):

```python
model = AutoModel.from_pretrained('openbmb/MiniCPM-V-2_6', trust_remote_code=True,
                                  attn_implementation='sdpa', torch_dtype=torch.bfloat16)
model = model.eval().cuda()
tokenizer = AutoTokenizer.from_pretrained('openbmb/MiniCPM-V-2_6', trust_remote_code=True)

image = Image.open('x.jpg').convert('RGB')
msgs = [{'role': 'user', 'content': [image, question]}]   # image is INSIDE content list
res = model.chat(image=None, msgs=msgs, tokenizer=tokenizer)
```

Key facts: the signature is **`model.chat(image=None, msgs=..., tokenizer=...)`** — pass `image=None` and put the PIL image as the **first element of the `content` list**. For deterministic JSON extraction use **`sampling=False`** (default greedy) and **`stream=False`** (returns a string; streaming requires `sampling=True, stream=True` and returns a generator). `attn_implementation` must be `'sdpa'` or `'flash_attention_2'`, never `'eager'`.

**Loading a trained LoRA adapter for inference** (from finetune readme — https://raw.githubusercontent.com/OpenBMB/MiniCPM-V/main/finetune/readme.md):

```python
from peft import PeftModel
from transformers import AutoModel
model = AutoModel.from_pretrained("openbmb/MiniCPM-V-2_6", trust_remote_code=True)
lora_model = PeftModel.from_pretrained(
    model, path_to_adapter, device_map="auto", trust_remote_code=True
).eval().cuda()
# then: lora_model.chat(image=None, msgs=msgs, tokenizer=tokenizer)
```

So **`PeftModel.from_pretrained(base_model, adapter_path)` + `.chat(...)` works** and is the documented path. (Alt: `AutoPeftModel.from_pretrained(path_to_adapter, trust_remote_code=True)`.) The readme warns: use an **absolute path** for the base model in the adapter's `adapter_config.json`. **UNVERIFIED for 2_6 specifically:** the readme example string says `openbmb/MiniCPM-o-2_6` (repo drift) — substitute `MiniCPM-V-2_6` and confirm the resampler/embed_tokens saved modules load (they are in `modules_to_save`, so PEFT restores them automatically).

---

## 6. Modal specifics (brief)

- **`import modal` inside a Modal container: YES, no pip-install needed.** Modal's image builder auto-injects the Modal client dependencies into every Image (changelog Image Builder `2025.06`: "Modal client dependencies are included in Modal Images"). A top-level `import modal` in a remotely-run file is fine. Source: https://modal.com/docs/reference/changelog , https://modal.com/docs/guide/images . (UNVERIFIED: no single doc sentence says "modal is preinstalled" verbatim — but the behavior is the documented norm.)
- **`Image.add_local_python_source` (modal 1.5.x) signature:** `add_local_python_source(self, *modules, copy=False, ignore=NON_PYTHON_FILES)`. Source: https://modal.com/docs/reference/modal.Image#add_local_python_source . Latest modal version on PyPI: **1.5.0** (https://pypi.org/pypi/modal/json).
- **GPU strings:** `gpu="L40S"` (48 GiB) and `gpu="A10"` (24 GiB) are the canonical forms; `gpu="A10G"` still works as a legacy alias (case-insensitive) but is no longer in the current GPU guide — the existing scaffold uses `"A10G"`, which is fine but **switch to `"L40S"`** per §4. Source: https://modal.com/docs/guide/gpu

---

## 7. CORD-v2 target sanity (data-prep must normalize)

Dataset: `naver-clova-ix/cord-v2`, field `gt_parse`. The format is _defined by_ Donut's `token2json` round-trip (`clovaai/donut` → `donut/model.py`), which is the authoritative source for the quirks. Source: https://huggingface.co/datasets/naver-clova-ix/cord-v2 , https://github.com/clovaai/donut/blob/master/donut/model.py

1. **`menu` can be a DICT (single item) instead of a LIST.** Confirmed: Donut's `token2json` collapses single-element lists (`if len(value)==1: value = value[0]`). A 1-line receipt → `menu` is a dict; multi-line → list. **Normalize: `if isinstance(menu, dict): menu = [menu]`.** Same collapse applies to nested `sub` and to `sub_total` rows.
2. **`cnt` / `price` are STRINGS with separators**, not numbers. Donut stringifies every leaf (`obj = str(obj)`). Real values: `"cnt":"1"`, `"price":"58,000"`, `"subtotal_price":"223,000"` (Indonesian receipts, comma thousands-separators; some have spaces). **Strip `,` and spaces before any numeric parse.**
3. **Nested sub-items exist:** each `menu` item may carry a `sub` field (modifier line, e.g. `"sub":{"nm":"WELL DONE"}`), itself subject to the dict/list collapse. `sub_total` is a separate top-level object (`subtotal_price`, `tax_price`, optional `service_price`/`discount_price`).
4. **Top-level `gt_parse` keys:** `menu`, `sub_total`, `total` (+ occasional `void_menu`). Example:
   ```json
   {
     "menu": [
       { "nm": "SPGTHY BOLOGNASE", "cnt": "1", "price": "58,000", "sub": { "nm": "WELL DONE" } },
       { "nm": "PEPPER AUS", "cnt": "1", "price": "165,000" }
     ],
     "sub_total": { "subtotal_price": "223,000", "tax_price": "22,300" },
     "total": { "total_price": "245,300", "cashprice": "250,000", "changeprice": "4,700" }
   }
   ```

**Data-prep checklist:** coerce `menu` (and nested `sub`, `sub_total` rows) dict→list; treat all `*price`/`cnt`/`unitprice` as strings; expect top-level `menu`/`sub_total`/`total`. Serialize the _normalized_ JSON as the training target so the model learns one consistent shape (and the scorer compares apples-to-apples).

---

## Pinned environment

**Primary (OpenBMB scripts, single-GPU bf16 LoRA) — training image:**

```
python==3.10
torch==2.1.2
torchvision==0.16.2
transformers==4.40.0          # DO NOT use 4.46/4.47/5.x
accelerate==0.30.1
peft~=0.11.0                   # UNVERIFIED exact pin for the 4.40.0 combo — smoke-test
sentencepiece==0.1.99
Pillow==10.1.0
timm==0.9.10
datasets                      # any recent; only for CORD download in prep, not training
huggingface_hub
# flash-attn: OMIT (optional; SDPA is default). bitsandbytes: OMIT (no 4-bit first run).
```

Note: this **diverges from the current scaffold** (`finetune/train_modal.py` / `finetune/requirements.txt`), which pins TRL + bitsandbytes 4-bit. Per the Decision, TRL and 4-bit should be dropped.

**Fallback (LLaMA-Factory):**

```
python==3.11
llamafactory==0.9.3           # pins transformers>=4.45,<=4.52.4 excl 4.46/4.47/4.48.0/4.52.0
transformers==4.49.0          # in-range; avoids the broken releases  (UNVERIFIED exact 2_6 combo)
torch>=2.1
# install: pip install -e ".[torch,metrics,minicpm_v]"  (or  pip install llamafactory==0.9.3)
```

---

## Known failure modes (top 5) + how the smoke test catches each

The smoke test = run the real recipe for **2 steps on ~8 CORD images on the target GPU**, logging `torch.cuda.max_memory_allocated()` and asserting loss is finite. Run it BEFORE any full paid run.

1. **transformers/remote-code import mismatch** (e.g. 4.46/4.47/5.x breaks `MiniCPMVBatchFeature`, or `init_audio`/`init_tts` kwargs don't exist on 2*6's older code). → `from_pretrained` raises at load. Smoke catches it in the first seconds. *Guard:* pin `transformers==4.40.0`; wrap the extra `init*\*` kwargs in try/except.
2. **Wrong trainer/collator path** (using TRL or a generic collator → `model.forward` gets a padded `pixel_values` tensor instead of the list + missing `image_bound`/`tgt_sizes`). → shape/key error in `compute_loss`. Smoke catches at step 1. _Guard:_ use OpenBMB's `CPMTrainer` + `dataset.py` collator (or LLaMA-Factory `minicpm_v` template) — do not hand-roll.
3. **OOM on single GPU** (the 14 GiB table number was Zero-3-sharded; single-GPU bf16 is higher). → CUDA OOM mid-step. Smoke surfaces it AND logs peak memory so you can size the full run. _Guard:_ provision L40S 48GB, batch 1 + grad-accum + gradient_checkpointing; only downgrade to A10G after a measured run.
4. **LoRA targets nothing / targets the vision tower** (wrong regex → 0 trainable params, or accidentally unfreezing `vpm` → OOM). → either "0 trainable params" log or OOM. Smoke catches via the `print_trainable_parameters()` assertion (must be >0 and a small % of total). _Guard:_ use the `r"llm\..*self_attn\.(q_proj|k_proj|v_proj|o_proj)"` regex, `--tune_vision false`.
5. **CORD target shape variance** (`menu` dict-vs-list, string prices) crashing the data-prep serializer or producing inconsistent targets. → KeyError/TypeError in prep, or garbage targets. Smoke (which runs on real CORD rows) catches a prep crash; a normalization unit test catches the silent-inconsistency case. _Guard:_ the §7 normalization (dict→list coercion, string handling) + assert the serialized target re-parses to a stable schema.

**Bonus guard:** after the smoke trains 2 steps, immediately run the §5 LoRA-load + `.chat()` path on the 2-step adapter to confirm the _inference contract_ round-trips before paying for a full run — a training success that can't be loaded for eval is still a wasted run.
