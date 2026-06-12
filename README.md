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

# Quillwright

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
python -m quillwright.server          # http://127.0.0.1:7860
```

By default the models are stubbed (fast, no GPU). For the **real local models**, install [Ollama](https://ollama.com), pull the models, and set the flag:

```
ollama pull minicpm-v
ollama pull nemotron-3-nano:4b
FF_REAL_MODELS=1 python -m quillwright.server
```

### Backend resolution — read this before "am I on Modal?"

There is no single local/Modal switch. `FF_REAL_MODELS=1` is the master gate out of
stub mode; backends then resolve **per role** (see `quillwright/resolver.py`), and a
few roles can only go one way:

| Role                                      | Stub (default) | Local (Ollama)                                                                        | Modal (hosted)                                                          |
| ----------------------------------------- | -------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **brain** (agent loop)                    | scripted       | Nemotron-3-Nano **4B**                                                                | Nemotron-3-Nano **30B** — set `FF_BACKEND=modal` + `FF_MODAL_BRAIN_URL` |
| **perception** (vision)                   | scripted       | MiniCPM-V                                                                             | _not hosted on Modal_ — stays on Ollama                                 |
| **multilingual**                          | scripted       | Aya                                                                                   | _not hosted on Modal_ — stays on Ollama                                 |
| **embedding / audio**                     | scripted       | on-device (sentence-transformers / transformers) — same path for any non-stub backend | _same on-device path_                                                   |
| **extraction** (Document Capture / Parse) | scripted       | _no local path_ (>30GB RAM on Apple Silicon)                                          | **Modal only**, always remote — needs `FF_MODAL_PARSE_URL`              |

Two inconsistencies that surprise people:

- **`FF_BACKEND=modal` moves only the _brain_ to Modal.** Vision and multilingual still
  resolve to Ollama; embedding/audio still run on-device. It is not a whole-stack switch.
- **Parse keys off its own `FF_MODAL_PARSE_URL`, independent of `FF_BACKEND`.** So you can
  run a local Ollama brain _and_ hit Modal Parse at the same time — "am I on Modal?" is not
  a single yes/no. This is intentional: Parse has no local serving path (ADR-0011), but it
  means the offline ("Airplane-Mode") story only holds while `FF_MODAL_PARSE_URL` is unset.

## Test

```
pytest -v
ruff check . && ruff format --check .                  # Python lint/format
npx prettier --check --ignore-unknown "quillwright/web/**/*"  # web lint/format
python scripts/check_deps_sync.py                      # pyproject ↔ requirements.txt

# brain accuracy against the eval set (needs Ollama + FF_REAL_MODELS=1)
FF_REAL_MODELS=1 PYTHONPATH=. python scripts/run_brain_eval.py
```

CI (`.github/workflows/ci.yml`) runs the same gate — the dependency-sync check,
ruff lint/format, pytest, and the web prettier check. It is **manual-only** (to
conserve Actions minutes): trigger it from the Actions tab or `gh workflow run ci.yml`.

Models resolve per role via `quillwright/resolver.py` (stub ↔ Ollama). Pricing is clearly-labeled sample data.
