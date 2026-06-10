"""Modal deployment of the Quillwright Best-Stack brain (ADR-0009).

ADR-0005: the hosted HF Space has no GPU, so real models reach it via an outbound
HTTPS call to Modal. ADR-0009 locks the **Best Stack** brain as **Nemotron 3 Nano
30B-A3B** (31.6B total / 3.2B active, MoE) — genuinely better than the local 4B and
too big for local Ollama, which is exactly why it lives on Modal.

Served with **vLLM** using NVIDIA's documented FP8 + tool-calling recipe
(https://docs.vllm.ai/projects/recipes/en/latest/NVIDIA/Nemotron-3-Nano-30B-A3B.html).
vLLM exposes an OpenAI-compatible API, so the client (`backends/modal.py`) talks
/v1/chat/completions and adapts the tool_calls shape back to our contract.

De-risk scope (ADR-0005): the BRAIN only. Vision (Omni) + multilingual copy this
pattern once it's proven.

Deploy (you run these — they touch your Modal account + credits):
    modal setup                                   # one-time auth
    modal deploy quillwright/backends/modal_app.py
Then point the app at the printed URL:
    export FF_BACKEND=modal
    export FF_MODAL_BRAIN_URL="https://<...>.modal.run"
"""

import modal

MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"  # ADR-0009 Best-Stack brain, FP8 (~32GB).
VLLM_PORT = 8000
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.12.0", "huggingface_hub", "flashinfer-python")
    # Fetch NVIDIA's custom reasoning-parser plugin via huggingface_hub (debian_slim
    # has no wget; hf_hub_download also handles HF redirects/caching correctly).
    .run_commands(
        'python -c "'
        "from huggingface_hub import hf_hub_download; import shutil; "
        "p = hf_hub_download("
        "repo_id='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16', "
        "filename='nano_v3_reasoning_parser.py'); "
        "shutil.copy(p, '/root/nano_v3_reasoning_parser.py')\""
    )
    .env(
        {
            # FP8 MoE acceleration (FP8 variant only), per NVIDIA's recipe.
            "VLLM_USE_FLASHINFER_MOE_FP8": "1",
            "VLLM_FLASHINFER_MOE_BACKEND": "throughput",
        }
    )
)

# Cache the downloaded weights across cold starts (pull once, not every boot).
hf_cache = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)

app = modal.App("quillwright-brain")


@app.function(
    image=image,
    gpu="L40S",  # FP8 needs ~32GB VRAM; L40S has 48GB (A10G's 24GB is too small).
    volumes={"/root/.cache/huggingface": hf_cache},
    timeout=1200,
    scaledown_window=300,  # stay warm 5 min after a request to mask cold starts.
)
@modal.concurrent(max_inputs=8)
@modal.web_server(port=VLLM_PORT, startup_timeout=900)
def serve():
    """Launch vLLM's OpenAI-compatible server with NVIDIA's tool-calling recipe."""
    import subprocess

    cmd = [
        "vllm",
        "serve",
        MODEL,
        "--trust-remote-code",
        "--async-scheduling",
        "--kv-cache-dtype",
        "fp8",
        "--tensor-parallel-size",
        "1",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",  # the parser NVIDIA specifies for this model.
        "--reasoning-parser-plugin",
        "/root/nano_v3_reasoning_parser.py",
        "--reasoning-parser",
        "nano_v3",
        "--max-model-len",
        "262144",
        "--max-num-seqs",
        "8",
        "--port",
        str(VLLM_PORT),
        "--host",
        "0.0.0.0",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
