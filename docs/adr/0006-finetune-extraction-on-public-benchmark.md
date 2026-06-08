# Fine-tune line-item extraction on a public benchmark with a baseline-vs-tuned eval

> **Updated 2026-06-08 (model target made concrete):** the fine-tune target is now **MiniCPM-V** (the live Perception model), trained with OpenBMB's official LoRA recipe on **CORD/SROIE**. We surveyed every sponsor's fine-tunability before locking this (see ADR-0009 for the model orchestra). Rejected alternatives: **Nemotron Parse** — best task fit but _no published fine-tune recipe_ (inference-only encoder-decoder), so it stays best-effort stretch; **Llama-Nemotron-Embed** — fine-tunable but we have no labeled retrieval triples and only a handful of seeded Runs, so it is used **un-tuned**; **Cohere Aya** — easiest tooling (`cohere-ai/cohere-finetune`) but multilingual is a supporting beat, not the hero skill, so it is a ranked stretch (Aya → FLUX → Parse). **One required fine-tune (MiniCPM-V); everything else un-tuned or stretch** — per ADR-0007.

For the 🎯 Well-Tuned quest we fine-tune a small model on the core task — document/photo → structured Line-Item/Observation JSON — and report **baseline vs fine-tuned field-level accuracy/F1 on a held-out split of a public Hugging Face dataset** (CORD or SROIE; `longmaodata/Invoice-annotation` as a candidate). The tuned model is published on HF. We deliberately choose a public benchmark over a bespoke trade-photo set because (a) public trade-PHOTO datasets are scarce/synthetic/commercial, while receipt/invoice extraction datasets are abundant and match our exact skill, and (b) a public benchmark makes the accuracy gain reproducible and credible.

## Considered Options

- **Bespoke hand-labeled trade set:** most domain-specific but heavy labeling effort and not reproducible in the window.
- **Augment public + small trade set:** middle ground; deferred unless time allows.
- **Public benchmark (CORD/SROIE) extraction + F1 (chosen):** reproducible, low-risk, directly strengthens the core extraction, yields a clean "X→Y accuracy" artifact for Field Notes.

## Consequences

- Produces a publishable HF model + a reproducible eval (baseline vs tuned) — the evidence for 🎯 and a 📓 Field Notes graph.
- The eval harness (field-level accuracy/F1 on the held-out split) is itself a small build task; keep it scriptable and deterministic.
- Remains a stretch in sequencing: execute once the core Run ships, but the plan is locked so it can be picked up cleanly.
