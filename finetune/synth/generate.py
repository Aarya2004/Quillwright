"""Modal driver: render grounded synthetic trade invoices -> images + train.jsonl.

Mirrors prepare_data.py / train_modal.py style. The number path is 100% code-owned
(Facts-from-Tools): for each example we pick a realistic job archetype with a long-tail
mix (jobs.realistic_job_mix), assemble it deterministically from the grounded catalog
(jobs.assemble_job), render it to a PNG via the OTHER agent's helper (render.render_invoice),
and append a manifest line {id, image, prompt, target} — the SAME shape prepare_data.py
writes — to /cache/synth/train.jsonl. The prompt is data_utils.PROMPT (one source of truth);
the target is json.dumps(jobs.to_target(job)), which round-trips through scorer.parse_items.

Volume gotcha honored: ONE /cache mount only (Modal forbids one volume at two mountpoints).

RENDERING IS NOT OURS. We call render.render_invoice(job, template_name) -> PNG bytes and
render.list_templates() -> list[str], owned by the other agent (finetune/synth/render.py).
That import happens INSIDE the remote function; if render.py is absent we fall back to a
placeholder PNG so this driver is importable/buildable and the LOCAL smoke (which never
renders) works for $0. Never `modal run`/`deploy` this — it costs money.

Local, $0 logic check (no Modal, no rendering):
    python finetune/synth/generate.py --local-smoke
Modal (DO NOT RUN without explicit go-ahead):
    modal run finetune/synth/generate.py --smoke      # ~10 images
    modal run finetune/synth/generate.py              # full (N=1000)
"""

import os
import sys

import modal

_HERE = os.path.dirname(os.path.abspath(__file__))
_FINETUNE = os.path.dirname(_HERE)

# Where rendered images + the manifest land inside the single /cache volume mount.
SYNTH_ROOT = "/cache/synth"
IMAGES_DIR = f"{SYNTH_ROOT}/images"
MANIFEST = f"{SYNTH_ROOT}/train.jsonl"

DEFAULT_FULL_N = 1000
DEFAULT_SMOKE_N = 10

# Render deps come straight from the OTHER agent's render.py, which exports the exact
# apt + pip lists for its WeasyPrint -> pdf2image -> Augraphy chain (the agreed coordination
# point — consuming them here means the image never drifts from what rendering needs). If
# render.py isn't importable yet we fall back to a minimal Pillow-only image so the placeholder
# path still builds; TODO(other-agent): once render.py is in, this just picks up its lists.
sys.path.insert(0, _HERE)  # so `import render` resolves at image-build (local) time
# data_utils lives in finetune/ (the PARENT), not finetune/synth/. add_local_python_source
# below resolves the module via sys.path at build time, so the parent must be on it — else
# Modal raises "data_utils has no spec - might not be installed?". (CORD's prepare_data.py
# dodges this only because it's run from finetune/; we run from the repo root.)
sys.path.insert(0, _FINETUNE)
try:
    from render import RENDER_APT_DEPS, RENDER_PIP_DEPS
except ImportError:
    RENDER_APT_DEPS = []
    RENDER_PIP_DEPS = ["pillow"]  # placeholder render only needs Pillow

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(*RENDER_APT_DEPS)
    .pip_install(*RENDER_PIP_DEPS)
    # Pure logic modules + data_utils (PROMPT/target source of truth, no modal import).
    .add_local_python_source("data_utils")
    .add_local_dir(
        _HERE, remote_path="/root/synth"
    )  # catalog_loader, jobs, catalog/, templates/, render.py
)

vol = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)
app = modal.App("quillwright-synth-generate")


@app.function(image=image, volumes={"/cache": vol}, timeout=7200)
def generate(n: int = DEFAULT_FULL_N, seed: int = 0, degrade: bool = False):
    """Render N synthetic invoices into /cache/synth and write the JSONL manifest.

    degrade=False (default) = CLEAN mode: WeasyPrint render only, no Augraphy. This is
    the reliable path — clean invoice PNGs are perfectly good training data. degrade=True
    opts into Augraphy scan/photo degradation (better transfer to photographed real docs)
    but Augraphy has finicky numpy/opencv pins; only enable once its deps are confirmed.
    """
    import json
    import random

    sys.path.insert(0, "/root/synth")  # catalog_loader, jobs, render importable by bare name

    from catalog_loader import load_catalog, validate_catalog
    from data_utils import PROMPT
    from jobs import assemble_job, realistic_job_mix, to_target

    render_invoice, list_templates = _resolve_render()

    catalog = load_catalog("/root/synth/catalog/catalog.json")
    validate_catalog(catalog)  # fail loudly on a bad catalog before spending render time

    templates = list_templates()
    if not templates:
        templates = ["__placeholder__"]

    os.makedirs(IMAGES_DIR, exist_ok=True)
    rng = random.Random(seed)
    degradation = 0.5 if degrade else 0.0  # 0.0 = clean (skip Augraphy)

    written = 0
    failures = 0
    with open(MANIFEST, "w") as mf:
        for i in range(n):
            trade, job_type = realistic_job_mix(rng)
            job = assemble_job(catalog, trade, job_type, rng)
            template = rng.choice(templates)

            # One bad render must not kill the whole run (and leave a half manifest).
            try:
                png_bytes = render_invoice(job, template, degradation=degradation, seed=i)
            except Exception as exc:  # noqa: BLE001 - log + skip, keep generating
                print(f"  [WARN] render failed for {i:05d} ({trade}/{job_type}): {exc!r}")
                failures += 1
                continue

            img_path = os.path.join(IMAGES_DIR, f"{i:05d}.png")
            with open(img_path, "wb") as imgf:
                imgf.write(png_bytes)

            mf.write(
                json.dumps(
                    {
                        "id": f"synth-{i:05d}",
                        "image": img_path,
                        "prompt": PROMPT,
                        "target": json.dumps(to_target(job), ensure_ascii=False, sort_keys=True),
                    }
                )
                + "\n"
            )
            written += 1

    vol.commit()  # flush so the training job sees images + manifest
    print(f"wrote {written}/{n} invoices to {MANIFEST} (render failures: {failures})")
    print(f"wrote {written} synthetic invoices -> {MANIFEST} (seed={seed})")


def _resolve_render():
    """Return (render_invoice, list_templates) from the other agent's render.py.

    render.py (finetune/synth/render.py) is owned by the OTHER agent with the agreed
    interface: render_invoice(job: dict, template_name: str) -> bytes (PNG), and
    list_templates() -> list[str]. If it's missing we fall back to a placeholder so this
    driver still builds + runs end-to-end (sans real rendering). TODO(other-agent):
    drop in render.py + templates/ and delete this fallback path.
    """
    try:
        from render import list_templates, render_invoice  # type: ignore

        return render_invoice, list_templates
    except ImportError:
        print(
            "WARNING: render.py not found — using placeholder PNG. (TODO: other agent's render.py)"
        )
        return _placeholder_render_invoice, (lambda: ["__placeholder__"])


def _placeholder_render_invoice(
    job: dict, template_name: str, degradation: float = 0.0, seed: int | None = None
) -> bytes:
    """Minimal valid PNG so the manifest + image-write path is exercisable without render.py.

    Accepts degradation/seed to match the real render_invoice signature (ignored here)."""
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), f"PLACEHOLDER {job['trade']}/{job['job_type']}", fill="black")
    y = 60
    for li in job["line_items"]:
        draw.text(
            (20, y),
            f"{li['description'][:60]}  {li['quantity']} x {li['rate']} = {li['amount']}",
            fill="black",
        )
        y += 20
    draw.text((20, y + 10), f"TOTAL {job['total']}", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@app.local_entrypoint()
def main(smoke: bool = False, n: int = DEFAULT_FULL_N, seed: int = 0, degrade: bool = False):
    """Modal entrypoint. `--smoke` renders DEFAULT_SMOKE_N images; else N (default 1000).

    Clean renders by default; `--degrade` opts into Augraphy (needs its deps confirmed)."""
    generate.remote(n=DEFAULT_SMOKE_N if smoke else n, seed=seed, degrade=degrade)


def _local_smoke(n: int = 3, seed: int = 0):
    """$0 logic check: assemble n jobs + print their targets. No Modal, no rendering."""
    import json
    import random

    sys.path.insert(0, _HERE)  # catalog_loader, jobs by bare name when run as a script

    from catalog_loader import load_catalog, validate_catalog
    from jobs import assemble_job, realistic_job_mix, to_target

    catalog = load_catalog(os.path.join(_HERE, "catalog", "catalog.json"))
    validate_catalog(catalog)
    rng = random.Random(seed)

    for i in range(n):
        trade, job_type = realistic_job_mix(rng)
        job = assemble_job(catalog, trade, job_type, rng)
        target = to_target(job)
        print(f"--- sample {i}: {trade}/{job_type} (total ${job['total']}) ---")
        print(json.dumps(target, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Local, Modal-free entrypoint so the logic is verifiable for $0.
    if "--local-smoke" in sys.argv:
        _local_smoke()
    else:
        print("Use `python finetune/synth/generate.py --local-smoke` for the $0 logic check,")
        print(
            "or `modal run finetune/synth/generate.py [--smoke]` to render on Modal (costs money)."
        )
