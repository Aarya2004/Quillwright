# Two-tier execution Mode via endpoint swap

> **Updated by ADR-0005 (hosting reality):** the modes were renamed from "Local/Connected" to **Private Stack / Best Stack**. "Local" wrongly implied on-device inference — a hosted Gradio Space runs models server-side (on Modal). The endpoint-swap design below is unchanged; only the names and the honest framing of "Private Stack = open small models, no third-party APIs" are corrected. The genuine offline story moved to the separate **Airplane-Mode Proof** (ADR-0005).


FieldForge runs in two user-selectable **Modes**: **Local** (every Model Role resolves to a tiny on-device model — offline, free, private) and **Connected** (roles resolve to larger hosted sponsor models for higher quality). We deliberately constrain the modes to differ ONLY in which model each Model Role resolves to — the agent loop, Tools, UI, and Deliverable are identical across modes. This keeps it one product with a model-resolver layer rather than two divergent products, which matters in a 10-day build.

## Considered Options

- **Single tier (small models only):** simplest, but forfeits the larger sponsor models (NVIDIA Nemotron, Cohere Command/Aya-32B) and the "best performance" story.
- **Modes that differ in capabilities (Connected unlocks video/image-gen/deeper reasoning):** more impressive but doubles the feature set to build and test — rejected for the core; any capability divergence (e.g. image/video generation) is fenced as an explicit stretch.
- **Endpoint swap only (chosen):** same everything, swap the model per role. Captures all sponsor pools without dropping any model (MiniCPM-V lives in Local; Nemotron/Aya/Command in Connected; gpt-oss spans both), and the "small standalone, optional upgrade" framing is the most honest small-model fit for the contest.

## Consequences

- Requires a model-resolver/registry abstraction so every Tool calls "the model for this role in this mode" rather than a hard-coded model.
- Local Mode is the demo hero (airplane-mode); Connected Mode is the quality upgrade.
- Image/video generation, if built, is a stretch that may only exist in Connected Mode — the one sanctioned capability divergence.
