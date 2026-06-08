# FieldForge — Progress & Handoff

_Last updated: 2026-06-08. Branch: `design/fieldforge` (NOT pushed — all work is local commits)._

FieldForge: a human-supervised, **local** small-model agent for tradespeople. Snap a job photo + voice note → an orchestra of small models (vision + tool-calling brain + multilingual) forges a finished, itemized **estimate**. No cloud. Built for the HuggingFace/Gradio "Build Small" hackathon (≤32B models, Gradio app, ends ~June 15).

---

## 1. How to run / test (orientation)

```bash
cd /Users/aaryaprakash/Development/random_projs/small-hackathon
source .venv/bin/activate

# Stub mode (fast, no GPU/models needed):
python -m fieldforge.server            # http://127.0.0.1:7860

# REAL local models (needs Ollama running + models pulled):
ollama pull minicpm-v nemotron-3-nano:4b aya     # already pulled on this machine
FF_REAL_MODELS=1 python -m fieldforge.server

# Tests + lint:
pytest -q                                          # 67 tests
ruff check . && ruff format --check .
npx prettier --check "fieldforge/web/**/*"

# Brain accuracy eval (needs Ollama + FF_REAL_MODELS=1):
FF_REAL_MODELS=1 PYTHONPATH=. python scripts/run_brain_eval.py
```

**Run the server with `uvicorn`/`python -m fieldforge.server`, NOT `.launch()`** — `gradio.Server` is a FastAPI app; `.launch()` does not serve our routes.

---

## 2. Architecture (where things live)

```
fieldforge/
├── server.py          # gradio.Server (FastAPI): serves web/ + all /api endpoints. ENTRY POINT.
├── agent.py           # LangGraph graph: perceive -> price/brain -> assemble. interrupt/resume.
├── brain_loop.py      # LLM tool-calling loop (run_brain): the agentic brain. SYSTEM prompt here.
├── brain_tools.py     # narrow tool surface for the brain: add_priced_item + finish (+ schemas)
├── brain_eval.py      # scorer (item F1 + qty accuracy) for the eval set
├── tools.py           # perceive / lookup_price / compute / draft_line_item / flag_for_human
├── catalog.py         # sample pricing + fuzzy/keyword lookup + add()
├── memory.py          # Memory: record_run / recall / profile (local JSON, keyword recall)
├── resolver.py        # ModelResolver: role -> model. backend="stub" (tests) | "ollama" (real)
├── models.py          # Pydantic: Capture, Observation, LineItem, Estimate, TraceStep
├── pdf.py             # Estimate -> PDF (reportlab)
├── backends/ollama.py # OllamaModel: .generate(prompt, image_path) + .chat(messages, tools)
├── api/
│   ├── estimate.py    # forge_estimate(_stream), resume_estimate_stream, perception/brain wiring,
│   │                  #   memory record+recall integration. MEMORY_PATH + reset_memory() here.
│   ├── upload.py      # save_upload (base64 image -> temp file)
│   ├── recalc.py      # recalc_estimate (server-authoritative totals on edit)
│   └── translate.py   # translate_estimate (Aya; descriptions only, never numbers)
└── web/               # bespoke frontend served by gr.Server (the gr.Blocks app.py was retired)
    ├── index.html
    ├── css/{theme,workspace}.css
    └── js/{client,trace,workspace}.js   # client.js = ONLY file that knows API URLs

data/
├── sample_catalog.json   # SAMPLE HVAC pricing (capacitor/contactor/refrigerant/labor)
└── brain_evalset.json    # 10 eval cases (note -> expected items+quantities)
scripts/run_brain_eval.py # runs brain over eval set, prints F1/qty accuracy

docs/
├── PROGRESS.md (this file) · CONTEXT.md (glossary) · adr/0001-0008 · research/problem-validation.md
├── design/frontend-core-workspace.md
└── superpowers/specs + plans (incl. 2026-06-07-llm-driven-brain.md)
```

**Key invariants (do not break):**
- **Facts-from-Tools**: every customer-facing number (price/qty/markup/tax/total) comes from a tool (`lookup_price`/`compute`) or user-confirmed edit — NEVER from an LLM. Holds on edits and translation.
- **Resolver swap**: models resolve per role via `resolver.py`. Stub for tests (no GPU); Ollama for real. `FF_REAL_MODELS=1` flips perception+brain+multilingual to real.
- **Narrow brain tool surface**: brain only calls `add_priced_item` + `finish`. This is WHY the 4B model is reliable — do not widen it casually.

---

## 3. DONE — built, committed, and verified

### Backend / agent
- ✅ **LangGraph agent** (perceive → price/brain → assemble) with `interrupt`/resume.
- ✅ **LLM-driven brain** — `nemotron-3-nano:4b` drives tool-calling (add items, set quantities, finish). Deterministic fallback when models off.
- ✅ **Facts-from-Tools** enforced (catalog lookup + `compute`); quantities supported ("3 hours" → qty 3).
- ✅ **Real vision** — `minicpm-v` reads job photos → structured observations.
- ✅ **Human-in-the-loop pause/resume** — missing price → agent pauses, asks, resumes (works with real brain too).
- ✅ **Fuzzy catalog lookup** — natural phrasing ("refrigerant" → `refrigerant_r410a`).
- ✅ **Memory** — record each finished run; recall similar past jobs (keyword, ranked); profile (common items). Surfaced as a "Memory" trace card on similar jobs.
- ✅ **Multilingual** — Cohere **Aya** translates estimate descriptions (Spanish/French/Mandarin); numbers untouched.
- ✅ **Eval harness** — `data/brain_evalset.json` + scorer + runner. **Measured: item F1 0.367 → 0.880 (fuzzy lookup) → 0.967 (prompt tuning); qty accuracy 0.40 → 1.00.**

### Frontend (bespoke, via gr.Server)
- ✅ Two-pane Workspace: light "Digital Apprentice" (streaming trace cards) + editable Draft Estimate.
- ✅ Sidebar (brand + Estimate Builder + working New Estimate; no dead links).
- ✅ Streaming trace (SSE) grouped into friendly cards (Memory / Site Analysis / Market Pricing / Estimate Assembled).
- ✅ Photo upload (camera button + thumbnails → /api/upload → real vision).
- ✅ Agent-Pause question card (ask price → resume).
- ✅ Inline-editable estimate (qty/rate) with server-authoritative recalc.
- ✅ Preview PDF / Finalize (download PDF) / Add Item / Discard.
- ✅ Language dropdown (English/Spanish/French/Mandarin) → live re-translate.
- ✅ Industrial-orange theme (Hanken/Inter/JetBrains Mono), minimalist (no useless UI).

### Infra / housekeeping
- ✅ Guardrail hooks in `.claude/` (ruff format-on-edit + block-lint-config). Verified firing.
- ✅ Retired obsolete `gr.Blocks` `app.py`; docs updated.
- ✅ ADRs 0001–0008 + CONTEXT.md glossary + problem-validation research (citable stats).

### Test/verification status
- ✅ **Automated: 67 pytest tests pass** (models, resolver, catalog, tools, agent incl. brain+pause+resume, pdf, ui presenters, api estimate/stream/pause/upload/recalc/translate, ollama backend, brain_tools, brain_loop, brain_eval, memory, memory_integration). ruff + prettier clean.
- ✅ **Verified by me (assistant) over HTTP / headless-Chrome screenshots:**
  - Real vision: photo → `model=minicpm-v` → observations ("RUN CAPACITOR" etc.).
  - Real brain: live forge → add×N + finish, total correct, no fabricated numbers (~15s).
  - Brain stress test (6 varied inputs) + eval (10 cases, F1 0.97).
  - Pause→resume with real brain ($55 → $89.27).
  - Translate (Spanish "Condensador doble de carreras", numbers unchanged $273.46).
  - Memory recall card appears on similar 2nd/3rd job.
  - Edit/recalc ($155.94), PDF (200/%PDF).
- ⚠️ **Manually verified by YOU (user):** you ran the app and gave UI feedback (twice) → drove the "Digital Apprentice" redesign + sidebar. **NOT yet user-verified end-to-end with REAL models + a real photo + edit + PDF + translate in one sitting.** ← recommended next manual pass.

---

## 4. WORK IN PROGRESS / KNOWN GAPS

- ⚠️ **Punjabi removed** — Aya's Gurmukhi output was mixed-script; dropped from dropdown (Mandarin added). User said they'll improve later.
- ⚠️ **"Finalize & Send" only downloads a PDF** — it does not actually send to a customer (no email/SMS). Currently same as Preview PDF.
- ⚠️ **Job title is hardcoded** ("AC Unit Repair — 123 Maple St") in the UI/recalc — not derived from the job.
- ⚠️ **Quantity unit handling is loose** — qty applies but unit (ea/hr/lb) comes from catalog; "2 hours" labor works, but unusual units aren't validated.
- ⚠️ **Real-models latency ~15–30s** for a full run (vision + brain + translate). Fine for recorded demo; warm models for live. Headless screenshots sometimes time out before completion.
- ⚠️ **Memory is single global file** (`/tmp/fieldforge_memory.json`) — no per-user separation; `/tmp` clears on reboot. Fine for demo, not multi-user.
- ⚠️ **Audio**: voice note is currently a TEXT transcript field — no real speech-to-text wired (Audio model role exists in resolver but unused). "Voice note" is typed, not spoken.

---

## 5. NOT STARTED (optional / stretch)

- ◻️ **GEPA / DSPy auto prompt-optimization** — eval harness is READY for it; documented as future work. Would chase the last ~3% F1. Needs DSPy + a reflection model (cloud-ish). Decided: document as stretch, don't build now.
- ◻️ **Semantic recall** (embeddings / Cohere Embed) — ADR-0003's hybrid recall; currently keyword-only. "Embedding" role stubbed in resolver.
- ◻️ **Ambiguity pause** ("Standard or Silver Duty?") — the mockup's exact variant; we built the missing-price pause instead.
- ◻️ **Real speech-to-text** for the voice note (whisper-class local model).
- ◻️ **Live video capture** mode.
- ◻️ **Black Forest Labs (FLUX)** visual generation — branded headers/diagrams (sponsor stretch).
- ◻️ **Fine-tuned model published on HF** (🎯 Well-Tuned quest) — we did eval-driven prompt tuning instead; a published fine-tune is separate.

---

## 6. DEPLOYMENT — NOT DONE YET (required for submission)

The hackathon requires: **a Gradio app hosted as a Hugging Face Space** + a demo video + a social post.

### The core deployment problem (see ADR-0005)
A HF Space runs models **server-side**. Free HF tier has **no GPU**; ZeroGPU is quota-limited (~3.5min/day free). Our real models (minicpm-v, nemotron, aya via Ollama) run great **locally on the dev Mac** but won't fit/perform on a free Space. Options:

1. **Hosted Space = stub/lightweight mode** (`FF_REAL_MODELS` off) so it runs on CPU, AND **film the real models running locally** as the demo video (the honest "airplane-mode / no-cloud" proof). ← simplest, recommended.
2. **Hosted Space backed by Modal GPU** (contest gives $250 Modal credits) — wire a `ModalModel` resolver backend (mirrors `OllamaModel`) calling Modal-hosted models. More work; gives a live real-model Space.
3. **Ollama inside the Space container** on CPU — works but slow.

### Deployment checklist (TODO)
- ◻️ Decide hosting strategy (1/2/3 above). Recommend #1 for the deadline + #2 if time.
- ◻️ Make the app a valid HF Space:
  - ◻️ `requirements.txt` (or keep pyproject) the Space build understands.
  - ◻️ A Space entry that Gradio recognizes. **Caveat: `gradio.Server` + custom frontend may need a specific Space SDK config (`sdk: gradio`, `app_file`)** — VERIFY a `gr.Server` app boots as a Space (this is untested; may need an `app.py` that exposes the Server, or run via the Space's uvicorn). This is the #1 deployment unknown to de-risk early.
  - ◻️ HF Space metadata (`README.md` front-matter: title, sdk, app_file, etc.).
- ◻️ Bundle `data/` (catalog + evalset) and `web/` into the Space.
- ◻️ Ensure stub mode works with zero external deps on the Space (it should — stub needs no GPU).
- ◻️ If Modal: implement `fieldforge/backends/modal.py` + resolver `backend="modal"`, deploy model endpoints, set env.
- ◻️ Test the deployed Space end-to-end (stub path at minimum).
- ◻️ **Airplane-Mode Proof clip** — record the local real-model run with wifi off (🦙 + 🔌 quests).
- ◻️ Demo video (~90s; script is in this repo's wrap-up / Field Notes outline below).
- ◻️ Social post.
- ◻️ Submit Space link + video + post by the deadline.

### Submission collateral (TODO)
- ◻️ **Field Notes blog post** (📓) — centerpiece: the eval story (manual test said "perfect", eval said 0.37, drove to 0.97 via fuzzy lookup + prompt tuning). Plus: small-model orchestra, gr.Server, Facts-from-Tools, on-device/no-cloud. Sponsor mapping below.
- ◻️ **Demo video** (~90s): pain hook → capture (photo+note) → watch Digital Apprentice stream → pause/answer → edit a rate (recalc) → language toggle (Spanish) → "wifi off, still works". Lead with Spanish (not Punjabi). Warm models first.
- ◻️ **Agent trace export / share on Hub** (📡 Sharing-is-Caring quest) — not yet built; the trace is shown live but not exported to the Hub.

### Sponsor / bonus-quest mapping (for submission)
- OpenBMB → MiniCPM-V (vision) ✅ · NVIDIA → Nemotron-3-Nano (brain) ✅ · Cohere → Aya (multilingual) ✅ · Gradio → gr.Server custom frontend (🎨 Off-Brand) ✅ · llama.cpp via Ollama (🦙 Llama Champion) ✅ · no third-party APIs / on-device (🔌 Off the Grid) ✅ · Field Notes (📓) ◻️ · agent trace share (📡) ◻️ · fine-tune on HF (🎯) ◻️ (we did prompt-tuning, not a published fine-tune).

---

## 7. Immediate recommended next steps (priority order)

1. **De-risk deployment EARLY**: confirm a `gradio.Server` custom-frontend app actually boots as a HF Space (the big unknown). If it doesn't, may need a thin `app.py` Server-export or a different Space config.
2. **User manual end-to-end pass** with `FF_REAL_MODELS=1` + a real photo (vision → brain → edit → PDF → Spanish). Flag anything broken.
3. Decide hosting (stub-Space + filmed local proof vs Modal-backed).
4. Record the demo video + write Field Notes (the eval story is the hook).
5. (Optional) agent-trace export for 📡, semantic recall, "send" for Finalize.

---

## 8. Git state
- Branch `design/fieldforge`, ~30+ commits, **NOT pushed**. Working tree clean.
- Per user's CLAUDE.md: break changes into commits; ASK before committing (or user commits); NEVER push/PR without asking; TDD; fix lint at root cause (no suppression); verify before claiming done.
- Models pulled in Ollama on this machine: `minicpm-v` (5.5GB), `nemotron-3-nano:4b` (2.8GB), `aya` (4.8GB). Disk was tight (~11GB free) — removed gemma4/deepseek to make room; watch disk before pulling more.
