"""Materialize CORD-v2 as MiniCPM-V fine-tune + eval data on a Modal volume (ADR-0006).

`naver-clova-ix/cord-v2` ships {image, ground_truth} where ground_truth is a JSON
string with `gt_parse` → {menu:[{nm,cnt,price}], sub_total, total}. We convert each
row into a chat-format SFT example (system + user-with-image → assistant JSON answer)
and persist images + a JSONL manifest into the SHARED `quillwright-hf-cache` volume,
so the training job (train_modal.py) and eval (eval.py) read the exact same prepared
split — no drift between prep, train, and score.

Why Modal and not local: keeps the heavy `datasets`/Pillow pull off the dev Mac and
lands the data on the same volume the GPU job mounts (one source of truth).

PROMPT and target logic live in data_utils.py (no modal import) — the single source of
truth shared by this script, train_modal.py, and eval.py.  Do NOT copy them here.

Run:
    modal run finetune/prepare_data.py
Outputs (in the volume, under /cache/cord/):
    images/<split>/<id>.png
    <split>.jsonl   # one {id, image, prompt, target} per line, split in {train,test}
"""

import modal

VOLUME_DATA_ROOT = "/cache/cord"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("datasets", "pillow", "huggingface_hub")
    .env({"HF_HOME": "/cache"})
    .add_local_python_source("data_utils")
)

# Reuse the same volume the inference apps cache weights in (backends/modal_*.py).
vol = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)

app = modal.App("quillwright-ft-prepare")


@app.function(image=image, volumes={"/cache": vol}, timeout=1800)
def prepare():
    """Download CORD, write images + JSONL manifests for train and test splits."""
    import json
    import os

    from data_utils import PROMPT, to_target
    from datasets import load_dataset

    os.makedirs(VOLUME_DATA_ROOT, exist_ok=True)

    # CORD: 800 train / 100 validation / 100 test. We train on `train`, score on `test`
    # (the held-out split — never seen in training), per ADR-0006's baseline-vs-tuned.
    for split in ("train", "test"):
        ds = load_dataset("naver-clova-ix/cord-v2", split=split)
        img_dir = os.path.join(VOLUME_DATA_ROOT, "images", split)
        os.makedirs(img_dir, exist_ok=True)
        manifest_path = os.path.join(VOLUME_DATA_ROOT, f"{split}.jsonl")

        n = 0
        with open(manifest_path, "w") as mf:
            for i, row in enumerate(ds):
                target = to_target(row["ground_truth"])
                if target is None:  # skip rows whose gt_parse won't parse
                    continue
                img_path = os.path.join(img_dir, f"{i:04d}.png")
                row["image"].convert("RGB").save(img_path)
                mf.write(
                    json.dumps(
                        {
                            "id": f"{split}-{i:04d}",
                            "image": img_path,
                            "prompt": PROMPT,
                            "target": json.dumps(target, ensure_ascii=False, sort_keys=True),
                        }
                    )
                    + "\n"
                )
                n += 1
        vol.commit()  # flush writes so the train/eval jobs see them
        print(f"[{split}] wrote {n} examples -> {manifest_path}")


@app.local_entrypoint()
def main():
    prepare.remote()
