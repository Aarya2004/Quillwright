---
title: Quillwright
emoji: ⚡
colorFrom: purple
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: Tell it about the job. It drafts the estimate.
tags:
  - backyard-ai
  - agent
  - small-models
  - off-the-grid
---

# Quillwright (FieldForge)

A human-supervised, small-model agent for tradespeople: snap a job photo + voice note → a team of **local** small models forges a finished, itemized **estimate**. No cloud, runs on your machine. Build Small Hackathon entry (Backyard AI track).

> **This hosted Space runs in stub mode** (CPU, no GPU): the agent flow, trace, editable estimate, and PDF all work, but the small models are stubbed. The real models (MiniCPM-V, Nemotron, Aya) run locally via Ollama — see the demo video / Airplane-Mode Proof for them in action. Live models reach the hosted Space via Modal (in progress).

See `docs/superpowers/specs/` and `docs/adr/` for the design.

## What's real

- **Vision** — MiniCPM-V (OpenBMB) reads job photos → observations, locally via Ollama.
- **Brain** — Nemotron-3-Nano (NVIDIA) drives the tool-calling agent loop (which items, quantities, when done), locally via Ollama. Tuned to ~0.97 item-F1 on the eval set (`scripts/run_brain_eval.py`).
- **Facts-from-Tools** — every price/total comes from the catalog + deterministic `compute`, never the LLM. Holds even for human edits.
- **Human-in-the-loop** — the agent pauses to ask when a price is missing; you answer and it resumes.
- **Frontend** — a bespoke web UI served by `gradio.Server` (FastAPI under the hood): streaming "Digital Apprentice" trace, editable estimate, PDF export.

## Run

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fieldforge.server          # http://127.0.0.1:7860
```

By default the models are stubbed (fast, no GPU). For the **real local models**, install [Ollama](https://ollama.com), pull the models, and set the flag:

```
ollama pull minicpm-v
ollama pull nemotron-3-nano:4b
FF_REAL_MODELS=1 python -m fieldforge.server
```

## Test

```
pytest -v
ruff check . && ruff format --check .       # Python lint/format
npx prettier --check "fieldforge/web/**/*"  # web lint/format

# brain accuracy against the eval set (needs Ollama + FF_REAL_MODELS=1)
FF_REAL_MODELS=1 PYTHONPATH=. python scripts/run_brain_eval.py
```

Models resolve per role via `fieldforge/resolver.py` (stub ↔ Ollama). Pricing is clearly-labeled sample data.
