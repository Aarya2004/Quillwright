"""Modal deployment of the Quillwright Best-Stack Perception + Audio: Nemotron Omni.

ADR-0009: Omni (nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning, 31B total / 3B active
MoE) is the selectable Best-Stack *alternative* for Perception — MiniCPM-V stays the
Private-Stack default (protects the OpenBMB track). Because Omni is omnimodal
(image + audio + text), this ONE deployment also serves the Best-Stack Audio role:
the client (`backends/modal.py`) sends photos as image_url parts and voice notes as
input_audio parts to the same /v1/chat/completions endpoint.

Served with vLLM (>=0.20 per NVIDIA's Omni recipe,
https://recipes.vllm.ai/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16) in the
FP8 variant (32.8 GB — same L40S class the brain app proved; encoders stay BF16).

NOT deployed yet (build-only; deploys touch your Modal account + credits):
    modal deploy quillwright/backends/modal_omni_app.py
Then point the app at the printed URL (per-role opt-in — the brain URL stays separate):
    export FF_BACKEND=modal
    export FF_MODAL_OMNI_URL="https://<...>.modal.run"

Deploy-time caveats (verify on first run, cheaply, ONE request at a time):
  - VRAM: 32.8 GB weights + BF16 encoders on a 48 GB L40S is tighter than the brain;
    --max-model-len is kept small (32K) for headroom. If engine init OOMs, bump to
    gpu="A100-80GB" for the verification run only.
  - The browser records voice notes as webm; Omni's recipe lists wav/mp3. The local
    transformers path handles webm today — if Omni rejects it, transcode to wav in
    /api/transcribe before the Modal call (do not silently drop audio).
"""

import modal

MODEL = "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-FP8"  # ADR-0009 Best-Stack Omni.
VLLM_PORT = 8000
image = (
    # CUDA devel base (nvcc) for FlashInfer's FP8 MoE JIT — same backbone/arch lesson
    # as the brain app (debian_slim crashes engine init).
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    # vllm[audio] pulls the audio decoders the Omni recipe requires.
    .pip_install("vllm[audio]==0.20.0", "huggingface_hub", "flashinfer-python")
    .env(
        {
            "VLLM_USE_FLASHINFER_MOE_FP8": "1",
            "VLLM_FLASHINFER_MOE_BACKEND": "throughput",
            # Weights go to the mounted cache volume (NOT ~/.cache — Modal refuses to
            # mount a volume over a non-empty dir).
            "HF_HOME": "/cache",
        }
    )
)

# Shared with the brain app: pull weights once, not every cold start.
hf_cache = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)

app = modal.App("quillwright-omni")


@app.function(
    image=image,
    gpu="L40S",  # FP8 weights 32.8GB; encoders BF16. 48GB with a small context fits.
    volumes={"/cache": hf_cache},
    timeout=1200,
    scaledown_window=120,  # warm 2 min after a request (masks cold starts; limits idle L40S burn).
    min_containers=0,  # true scale-to-zero: $0 when idle (open-ended judging window — never pre-warm-and-forget).
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=VLLM_PORT, startup_timeout=900)
def serve():
    """Launch vLLM's OpenAI-compatible server with NVIDIA's Omni recipe."""
    import subprocess

    cmd = [
        "vllm",
        "serve",
        MODEL,
        "--trust-remote-code",
        # One photo or one short voice note per request — not the recipe's video load.
        "--max-model-len",
        "32768",
        "--max-num-seqs",
        "8",
        # The cmd is joined into ONE shell string (shell=True, like the brain app):
        # single-quote the JSON and keep it space-free so it stays one shell token.
        "--limit-mm-per-prompt",
        '\'{"image":4,"audio":1,"video":0}\'',
        "--kv-cache-dtype",
        "fp8",
        "--tensor-parallel-size",
        "1",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
        "--reasoning-parser",
        "nemotron_v3",  # built into vLLM >=0.20 (no plugin file, unlike the brain app).
        "--port",
        str(VLLM_PORT),
        "--host",
        "0.0.0.0",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
