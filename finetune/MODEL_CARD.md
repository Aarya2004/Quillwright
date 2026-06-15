---
base_model: openbmb/MiniCPM-V-2_6
library_name: peft
license: cc-by-4.0
tags:
  - lora
  - minicpm-v
  - document-understanding
  - receipt-extraction
  - vision-language
datasets:
  - naver-clova-ix/cord-v2
language:
  - en
pipeline_tag: image-text-to-text
---

# MiniCPM-V-2_6 LoRA — CORD line-item extraction

A LoRA adapter for [`openbmb/MiniCPM-V-2_6`](https://huggingface.co/openbmb/MiniCPM-V-2_6)
that turns a **document/receipt image into structured line-item JSON**
(`{"menu": [{"nm", "cnt", "price"}], "total": ...}`). Built for the
[Quillwright](https://github.com/Aarya2004/Quillwright) project (a small-model agent that
drafts trade estimates) as the document-extraction skill behind its Document Capture path.

## Results — baseline vs. tuned (held-out CORD test split, n=100)

Field-level accuracy of the un-tuned base model vs. this LoRA adapter, scored on the
100-receipt held-out CORD-v2 **test** split. Deterministic greedy decoding; 0 generation
failures. Reproducible via the eval harness in the Quillwright repo (`finetune/eval.py`).

| Metric             | Baseline (un-tuned) | Tuned (this LoRA) | Δ      |
| ------------------ | ------------------- | ----------------- | ------ |
| **Item F1**        | 0.588               | **0.681**         | +0.093 |
| Quantity accuracy  | 0.715               | **0.782**         | +0.067 |
| **Price accuracy** | 0.575               | **0.726**         | +0.151 |
| Precision          | 0.567               | 0.666             | +0.099 |
| Recall             | 0.647               | 0.728             | +0.081 |

Every field improved; the largest gain is **price accuracy (+0.151)** — the field that
matters most for an estimate.

## Training

- **Base:** `openbmb/MiniCPM-V-2_6` (8B vision-language model)
- **Dataset:** [`naver-clova-ix/cord-v2`](https://huggingface.co/datasets/naver-clova-ix/cord-v2)
  (CC BY 4.0, © NAVER CLOVA) — 800-receipt train split; held-out 100-receipt test split for eval
- **Recipe:** OpenBMB's official `finetune.py` + `CPMTrainer`, single GPU (L40S), **no DeepSpeed**,
  **bf16 LoRA (not 4-bit)**. LoRA on the LLM self-attention projections (q/k/v/o) only;
  vision tower + resampler frozen (`embed_tokens` + `resampler` saved).
- **Hyperparameters:** r=64, α=64, dropout=0.05, lr=1e-5, model_max_length=2048,
  3 epochs, effective batch 8 (bs 1 × grad-accum 8), gradient checkpointing.
- **Final train loss:** ~0.31 (from ~0.85).
- **Attention:** SDPA (flash-attn not required).

## Inference

```python
from peft import PeftModel
from transformers import AutoModel, AutoTokenizer
from PIL import Image

PROMPT = ('Extract the line items from this receipt as JSON with this exact shape: '
          '{"menu": [{"nm": <item name>, "cnt": <quantity>, "price": <price>}], '
          '"total": <grand total>}. Output only the JSON.')

base = AutoModel.from_pretrained("openbmb/MiniCPM-V-2_6", trust_remote_code=True,
                                 attn_implementation="sdpa")
model = PeftModel.from_pretrained(base, "Aarya2004/minicpmv-cord-lora",
                                  trust_remote_code=True).eval().cuda()
tok = AutoTokenizer.from_pretrained("openbmb/MiniCPM-V-2_6", trust_remote_code=True)

img = Image.open("receipt.jpg").convert("RGB")
msgs = [{"role": "user", "content": [img, PROMPT]}]
print(model.chat(image=None, msgs=msgs, tokenizer=tok, sampling=False))
```

> MiniCPM-V-2_6's remote code hard-imports `flash_attn` at load even with SDPA; if you hit
> that ImportError, strip `flash_attn` from `transformers.dynamic_module_utils.get_imports`
> (see `finetune/flash_patch.py` in the Quillwright repo) — flash-attn is not required.

## Attribution

- Base model: MiniCPM-V-2_6 © OpenBMB.
- Training data: CORD (Consolidated Receipt Dataset) v2 © NAVER CLOVA, CC BY 4.0.
- Fine-tune recipe adapted from OpenBMB's official MiniCPM-V finetune scripts (Apache-2.0).
