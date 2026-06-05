# Hosting on Modal; honest framing of "small/offline"

A Gradio Hugging Face Space runs models **server-side**, and HF's free tier has no GPU while ZeroGPU offers only ~3.5 min/day (≈25 min on PRO) of bursty, quota-limited GPU. Our agent makes many model calls per Run across several models (gpt-oss-20b ≈16GB VRAM alone), which does not fit that quota. Therefore real compute runs on **Modal** (contest provides $250/participant credits + a winner pool; real GPUs, scale-to-zero). The Space remains the Gradio entry point.

Consequently the two Modes are **renamed and reframed**: **Private Stack** (open small models ≤32B, no third-party AI APIs — the contest's actual "no cloud APIs" ask) vs **Best Stack** (larger hosted sponsor models). The literal "runs offline on a phone in airplane mode" claim is delivered as a **separate Airplane-Mode Proof**: the Private Stack running on a real local machine via llama.cpp with the network off (also satisfies the 🦙 Llama Champion quest). This keeps every claim honest — the hosted Space demonstrates the agent; the filmed clip proves true offline capability.

## Considered Options

- **ZeroGPU-only, shrink the stack:** pure-HF but the multi-model, multi-step agent blows the daily quota and risks a throttled, slow demo.
- **Genuinely on-device product + lightweight hosted showcase:** maximally honest offline story but two deploy targets and a reduced hosted experience.
- **Modal for compute + honest reframe (chosen):** feasible, snappy, uses sponsor credits, and separates the "agent demo" (hosted) from the "offline proof" (filmed local run).

## Consequences

- Deployment target is Modal-backed; the model-resolver calls Modal-hosted endpoints per Model Role + Mode.
- "Local Mode" terminology is retired (see CONTEXT.md) to avoid overclaiming on-device inference in the hosted Space.
- **Cold-start mitigation:** keep Modal containers warm during the demo window and rely on the streaming Trace to mask per-step latency (watching steps appear reads as "thinking," not "hanging"); optionally co-locate the Private Stack in one long-lived container per Run to incur one cold start instead of many.
- The Airplane-Mode Proof becomes a required submission artifact, not an afterthought.
