# Fine-tune line-item extraction on a public benchmark with a baseline-vs-tuned eval

For the 🎯 Well-Tuned quest we fine-tune a small model on the core task — document/photo → structured Line-Item/Observation JSON — and report **baseline vs fine-tuned field-level accuracy/F1 on a held-out split of a public Hugging Face dataset** (CORD or SROIE; `longmaodata/Invoice-annotation` as a candidate). The tuned model is published on HF. We deliberately choose a public benchmark over a bespoke trade-photo set because (a) public trade-PHOTO datasets are scarce/synthetic/commercial, while receipt/invoice extraction datasets are abundant and match our exact skill, and (b) a public benchmark makes the accuracy gain reproducible and credible.

## Considered Options

- **Bespoke hand-labeled trade set:** most domain-specific but heavy labeling effort and not reproducible in the window.
- **Augment public + small trade set:** middle ground; deferred unless time allows.
- **Public benchmark (CORD/SROIE) extraction + F1 (chosen):** reproducible, low-risk, directly strengthens the core extraction, yields a clean "X→Y accuracy" artifact for Field Notes.

## Consequences

- Produces a publishable HF model + a reproducible eval (baseline vs tuned) — the evidence for 🎯 and a 📓 Field Notes graph.
- The eval harness (field-level accuracy/F1 on the held-out split) is itself a small build task; keep it scriptable and deterministic.
- Remains a stretch in sequencing: execute once the core Run ships, but the plan is locked so it can be picked up cleanly.
