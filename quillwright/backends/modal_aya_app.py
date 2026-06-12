"""Modal deployment of the Quillwright Best-Stack Multilingual: Aya Expanse 8B.

ADR-0009 lists Best-Stack Multilingual as "Aya larger / Command". The pick here is
CohereLabs/aya-expanse-8b in full BF16: a *newer generation* than the local Aya 23
(q4 via Ollama) — better multilingual quality at full precision, and small enough
for a cheap A10G (24 GB). Deliberately NOT aya-expanse-32b: ADR-0009 records the
contest rule as STRICTLY under 32B per model ("verified at kickoff"), which a
32B-named model fails. If that reading is overturned (PROGRESS/CONTEXT say "<=32B"),
upgrading is this file's MODEL constant + FF_MODAL_AYA_MODEL — one line.

Translation only needs .generate() (descriptions in, descriptions out — numbers
never pass through a model), so this is the simplest of the three vLLM apps: no
tool parsing, no reasoning parser, no FP8 MoE kernels (plain dense 8B).

NOT deployed yet (build-only; deploys touch your Modal account + credits):
    modal deploy quillwright/backends/modal_aya_app.py
Then point the app at the printed URL (per-role opt-in):
    export FF_BACKEND=modal
    export FF_MODAL_AYA_URL="https://<...>.modal.run"
"""

import modal

MODEL = "CohereLabs/aya-expanse-8b"  # ADR-0009 Best-Stack Multilingual (see above).
VLLM_PORT = 8000
image = (
    # No FP8-MoE JIT here (dense BF16 model) — the slim base is enough.
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.12.0", "huggingface_hub")
    .env({"HF_HOME": "/cache"})
)

# Shared with the other apps: pull weights once, not every cold start.
hf_cache = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)

app = modal.App("quillwright-aya")


@app.function(
    image=image,
    gpu="A10G",  # 8B BF16 ~16GB; A10G's 24GB fits with short-context headroom.
    volumes={"/cache": hf_cache},
    timeout=1200,
    scaledown_window=300,  # stay warm 5 min after a request to mask cold starts.
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=VLLM_PORT, startup_timeout=900)
def serve():
    """Launch vLLM's OpenAI-compatible server for translation calls."""
    import subprocess

    cmd = [
        "vllm",
        "serve",
        MODEL,
        # Estimate descriptions are short; a small context keeps VRAM comfortable.
        "--max-model-len",
        "8192",
        "--max-num-seqs",
        "8",
        "--tensor-parallel-size",
        "1",
        "--port",
        str(VLLM_PORT),
        "--host",
        "0.0.0.0",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
