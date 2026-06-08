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

## 5. STRETCH GOALS — ranked (set in the 2026-06-08 grill; this is the living priority list)

Order is the user's. Only pursue once committed scope (§6 deployment + §7 build order) is solid; cut from the bottom.

1. **S1 — Recall eval** (~15–20 seeded Runs + scorer; recall@1 keyword vs semantic). _Highest._ Answers "does semantic Recall improve accuracy" + a 2nd measured Field-Notes data point. Borderline-committed. (ADR-0003)
2. **S3 / S4 / S5 — sponsor-model block (equal priority):**
   - **S3 Aya fine-tune** via `cohere-ai/cohere-finetune` (easiest tooling of any sponsor; trade-vocab translation; cheap 2nd 🎯 point).
   - **S4 Nemotron Omni** as selectable Best-Stack Perception. **Coupled to the Modal backend (now committed §7.2):** Omni is too big to run locally via Ollama → it only runs _for real_ on Modal, so it rides the §7.2 backend once that exists. Cheap part (resolver dropdown) is high; running it = needs Modal.
   - **S5 Nemotron Parse** inference as an extraction tool (NVIDIA breadth; no fine-tune — no recipe).
3. **S10 — Finalize & Send (real email/SMS).** _Medium._ User has a Twilio account → real send is feasible. **Constraint:** Twilio creds can't live in a public HF Space → real send runs in the local/demo path; the hosted Space falls back to a draft/shareable-link.
4. **S7 — Agent-trace export** to the Hub (📡 Sharing-is-Caring). Trace is shown live, not yet exported.
   _(S6 Modal-backed live Space was PROMOTED to committed §7.2 on 2026-06-08 — no longer a stretch.)_
5. **S2 — Inventory live-decrement** (finalize subtracts parts). Upgrades the read-only Inventory page (ADR-0010); only if core solid.
6. **S8 — FLUX Klein** branded visuals (LoRA; delight/📡; off the core skill).
7. **S9 — `gr.Workflow`** orchestra node-graph demo (separate artifact, goodwill only; NEVER the core app — ADR-0010).
8. **S11 — deferred grab-bag, REVISIT FLAG.** GEPA/DSPy auto prompt-opt, live video capture, service-report mode, Parse/embed fine-tunes, ambiguity-pause variant. Explicitly deferred; some parts may be promoted later — revisit, don't enumerate now.

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

- OpenBMB → MiniCPM-V (vision; **central part → $10k track**, do NOT swap away) ✅ · NVIDIA → Nemotron-3-Nano (brain) ✅ + Transcribe-alt/Omni/Parse/Embed (committed/stretch) · Cohere → Aya (multilingual) ✅ + **Transcribe (Audio, committed)** · Gradio → gr.Server custom frontend (🎨 Off-Brand) ✅ · llama.cpp via Ollama (🦙 Llama Champion) ✅ · no third-party APIs / on-device (🔌 Off the Grid) ✅ · Field Notes (📓) ◻️ · agent trace share (📡) ◻️ · fine-tune on HF (🎯) ◻️ → **MiniCPM-V on CORD/SROIE (committed, ADR-0006)**.
- ⚠️ **OpenAI prize is OUT OF SCOPE** — won by Codex-attributed commits (we build with a different agent), NOT by running gpt-oss. The spec's "gpt-oss Agent Brain" mapping is stale; brain is Nemotron (ADR-0009). Do not write submission copy claiming the OpenAI prize.

---

## 7. Build order — committed scope (set in the 2026-06-08 grill)

Phases in order. **Deployment de-risk jumps the queue ahead of all new feature work** (user-agreed): an undeployed app with 6 models is worth less than a deployed app with 3. Stretch ladder = §5; pursue only after this is solid.

0. **Doc-reconcile** — purge stale gpt-oss from spec §3; fix ZeroGPU figure. Small, do first so we don't build on a lie. _(done in this grill)_
1. **Stub Docker Space (deployment de-risk)** — confirm `gr.Server` boots as a **Docker-SDK Space** (now _sanctioned_ per kickoff transcript), `FF_REAL_MODELS` OFF → CPU/stub, no Ollama. **Test the container boots locally first** (`docker build` + `docker run`) to kill the unknown without HF build queues. #1 risk; nothing jumps this. Then make it a valid HF Space under the hackathon org (README front-matter + tags, bundle `data/` + `web/`). Structure the resolver so a Modal backend drops in via env flag (`FF_BACKEND=modal`) without touching the Dockerfile/frontend.
2. **Modal backend — hosted Space runs REAL models** _(promoted from stretch S6, 2026-06-08: user wants the clickable Space to actually run models, not just stub)_. Write `fieldforge/backends/modal.py` (`ModalModel`, mirrors `OllamaModel`) + deploy the orchestra on Modal GPUs + wire the Modal token as a Space secret + handle cold starts. **Hardest single item on the board** — internal de-risk: get ONE model (the brain) working Space→Modal end-to-end before doing all three (MiniCPM-V, Nemotron, Aya). Why Modal not ZeroGPU: ZeroGPU is Gradio-SDK-only + breaks with FastAPI/`gr.Server` (verified, ADR-0005); Modal is an outbound HTTPS call that works with Docker SDK and keeps the 🎨 bespoke frontend.
3. **Audio role — Cohere Transcribe local GGUF** (typed → real spoken note). De-risk the local serve first; D-fallback = typed note in Private Stack (ADR-0009).
4. **Semantic Recall** — Llama-Nemotron-Embed (text) via sentence-transformers, record-time cached (ADR-0003).
5. **Secondary pages** — Dashboard / Active Jobs / Inventory, **demoable-first → functional read-models** (Inventory read-only) (ADR-0010).
6. **MiniCPM-V fine-tune on CORD/SROIE** (Modal) — the 🎯 artifact; parallelizable, doesn't block the app (ADR-0006).
7. **Submission collateral** — demo video (~90s), social post (link in README), **Airplane-Mode Proof** clip.

> **Trade-off noted (2026-06-08):** promoting Modal to #2 pushes the demo-visible feature work (spoken voice note, semantic Recall, the 3 pages) later. Conscious choice — a hosted Space that actually runs the models is a stronger submission spine than stub-Space + more features.

**Also pending (from original handoff):** user manual end-to-end pass with `FF_REAL_MODELS=1` + real photo (vision → brain → edit → PDF → Spanish).

---

## 8. Git state

- Branch `design/fieldforge`, ~30+ commits, **NOT pushed**. Working tree clean.
- Per user's CLAUDE.md: break changes into commits; ASK before committing (or user commits); NEVER push/PR without asking; TDD; fix lint at root cause (no suppression); verify before claiming done.
- Models pulled in Ollama on this machine: `minicpm-v` (5.5GB), `nemotron-3-nano:4b` (2.8GB), `aya` (4.8GB). Disk was tight (~11GB free) — removed gemma4/deepseek to make room; watch disk before pulling more.
