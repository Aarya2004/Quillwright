# Expanded model orchestra: maximize NVIDIA breadth while protecting the OpenBMB track

We expand the model orchestra to use more sponsor models (the bonus-badge strategy rewards collecting sponsor surfaces), but **additively** — filling empty Model Roles rather than swapping working ones. This supersedes the spec's §3 table, whose Agent Brain was listed as **gpt-oss-20b**; the brain shipped is **Nemotron 3 Nano** (verified in `resolver.py` / `OLLAMA_TAGS`). The kickoff transcript also corrected our sponsor assumptions: the **OpenAI prize is won by Codex-attributed commits, not by running gpt-oss** — so gpt-oss carries no prize value for us and is dropped.

## The role → model assignment (locked)

| Model Role             | Private Stack                          | Best Stack (selectable)            | Sponsor          | Status                           |
| ---------------------- | -------------------------------------- | ---------------------------------- | ---------------- | -------------------------------- |
| **Perception**         | MiniCPM-V                              | Nemotron 3 Nano **Omni** (if time) | OpenBMB / NVIDIA | live (MiniCPM-V); Omni stretch   |
| **Audio**              | **Cohere Transcribe (2B)**             | Nemotron 3 ASR / Omni              | Cohere / NVIDIA  | new — closes typed-vs-spoken gap |
| **Agent Brain**        | **Nemotron 3 Nano 4B**                 | Nemotron 3 Nano (30B/3B-active)    | NVIDIA           | live                             |
| **Multilingual**       | Cohere Aya (3.3B)                      | Aya larger / Command               | Cohere           | live                             |
| **Embedding**          | **Llama-Nemotron-Embed-1B (un-tuned)** | —                                  | NVIDIA           | new — upgrades Recall to hybrid  |
| **Extraction (tool)**  | —                                      | **Nemotron Parse (<1B)** inference | NVIDIA           | best-effort                      |
| **Visual** _(stretch)_ | —                                      | FLUX.2 Klein 4B                    | BFL              | stretch                          |

## Considered Options

- **Max-NVIDIA (swap Perception → Omni, replace everywhere):** most NVIDIA surface, but **forfeits the OpenBMB $10k track** (which requires MiniCPM as a central part of the app) and throws away the eval-tuned MiniCPM-V vision path. Rejected.
- **Core-first (add only Audio, defer the rest):** safest for the deadline but leaves NVIDIA breadth and the Embedding role on the table.
- **Additive-only (chosen):** keep MiniCPM-V as Perception (protect OpenBMB); add NVIDIA in the _empty_ roles (Audio alt, Embedding, Parse) and offer Omni as a Best-Stack Perception _alternative_, not a replacement. Captures NVIDIA's RTX prizes **and** OpenBMB's $10k, and it is literally the two-Mode design (ADR-0001) realized rather than a rewrite.

## Why Cohere isn't sidelined

Adding NVIDIA risked stranding Cohere. Resolved: Cohere owns **two live roles** — **Audio** (Cohere Transcribe, the on-device STT that makes the "voice note" genuinely spoken) and **Multilingual** (Aya). No Cohere fine-tune is required; both ship un-tuned. (Aya remains the _easiest_ stretch fine-tune via `cohere-ai/cohere-finetune` if time allows.)

## Consequences

- `resolver.py` gains real role mappings beyond the current three Ollama tags: Audio (Cohere Transcribe), Embedding (Llama-Nemotron-Embed-1B). The spec §3 table and the gpt-oss brain mapping are **stale and superseded by this ADR**; update on the next spec pass.

### Audio serving: local GGUF (llama.cpp), with a claim-preserving fallback

The Audio role (**Cohere Transcribe, 2B Conformer**) is served as a **local GGUF via llama.cpp** — a separate runtime from Ollama (Ollama serves text LLMs, not ASR). This keeps the spoken voice note _inside_ the on-device Private Stack, preserving 🔌 Off the Grid + the Airplane-Mode Proof, and **adds a second model to the 🦙 Llama Champion (llama.cpp) story**.

- **De-risk first:** verify the Transcribe GGUF actually serves locally _before_ building capture UI around it. llama.cpp support for Conformer ASR may be less mature than for text LLMs — treat "spoken note in Private Stack" as unverified until the local serve runs cleanly.
- **Fallback = ADR-0007 "Option D":** if the local GGUF path is too fiddly under time pressure, Private Stack reverts to the **typed transcript** (as today) and real STT lives in **Best Stack only**. We do **NOT** fall back to a hosted Cohere ASR API in the Private Stack — that would break the offline claim, which is the entire point of the role.
- **The OpenAI sponsor prize is out of scope** (Codex-attributed commits; we build with a different agent). Do not write submission copy claiming it.
- Embedding is used **un-tuned** (no labeled retrieval data); the only shipped fine-tune is MiniCPM-V/CORD-SROIE (ADR-0006).
- Per ADR-0007's cut order, all new roles attach without rewiring the core; under time pressure they cut from the end (Parse, Omni, FLUX first).
- 32B rule (verified at kickoff: **total** params, **strictly under** 32B, per-model): every model here is comfortably legal; watch only that any "Aya 32B"-class Best-Stack pick uses a sub-32B variant.
