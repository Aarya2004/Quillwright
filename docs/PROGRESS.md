# Quillwright — Progress & Handoff

_Last updated: 2026-06-10. Branch: `design/fieldforge` (project renamed to Quillwright; git BRANCH name unchanged). PUSHED to GitHub `origin` (github.com/Aarya2004/Quillwright) through the Modal work. **HF Space NOT re-uploaded since the 2026-06-08-early stub** — the live Space is stale (no redesign/pages/chat/real-models). The 2026-06-09/10 model wiring (Modal Best-Stack brain, semantic Recall, spoken Audio) needs torch and is LOCAL-DEMO only — not in the stub Space._

> **Shipped 2026-06-09/10 — model wiring (real models, assistant-verified end-to-end):**
>
> - **Modal Best-Stack brain (ADR-0005/0009):** Nemotron 3 Nano **30B-A3B** (FP8) served on Modal via vLLM (NVIDIA's tool-calling recipe), reachable over HTTPS from the GPU-less Space. `backends/modal_app.py` + `ModalModel` client (OpenAI→our-shape adapter) + resolver `backend="modal"` + `FF_BACKEND=modal`. Verified: `FF_BACKEND=modal` forge → 30B → correct $171.76 estimate, 3/3 runs. Cleared 5 infra blockers (wget, volume mount, nvcc/FP8-MoE, vLLM message-format). **⚠️ Cost lesson: de-risk session ran $4.16 (failed deploys each pay a full GPU cold-start); Modal app now STOPPED. Don't leave it serving the live Space.**
> - **Semantic Recall (S1, ADR-0003):** `llama-nemotron-embed-1b-v2` via sentence-transformers (lazy torch); `Memory(embedder=)` caches vectors at record-time, cosine re-rank at recall-time. **Measured: keyword 0.750 → semantic 0.875 (+0.125)** — the 2nd Field-Notes data point, with one honest remaining miss.
> - **Spoken Audio (ADR-0009):** `cohere-transcribe-03-2026` on-device via transformers (AutoProcessor + CohereAsrForConditionalGeneration — `pipeline()` errors; CrispASR/llama.cpp can't serve the Conformer arch). Mic button → record → `/api/transcribe` → fills the note. Verified: trade note transcribes cleanly. Gated repo (HF access + token).
> - **Model honesty:** boot banner (STUB vs REAL + Ollama reachability check), real model name in the trace, stale gpt-oss label fixed → Nemotron.
> - **Real-brain chat:** chat refinement routes through the tool-calling brain under `FF_REAL_MODELS=1`/Modal (was keyword-only).
> - **Tests: 89 → 115 pass.** ruff + prettier clean. Embedding/Audio are opt-in `[embed]`/`[audio]` extras (heavy torch; NOT in the Space).
> - **State:** all pushed to GitHub **except** the 2 commits being shipped now (semantic Recall + Audio). Live Space still stale.

> **Shipped 2026-06-08 (late) — 6 commits, all assistant-verified offline, NOT yet user-verified live (now PUSHED):**
>
> - **JSON export** (`api/export.py`, `/api/export_json`, "Export JSON" button) — the "no-lock-in" wedge; same server-authoritative totals as the PDF.
> - **Conversational chat** (`api/chat.py`, `/api/chat`) — refine the estimate by talking to the Apprentice ("add a contactor", "change labor to 3 hrs", "drop the refrigerant"). Facts-from-Tools holds (catalog prices only); deterministic so the stub Space works with zero models. Real-brain wiring point noted for later.
> - **Three secondary pages** (ADR-0010): Dashboard / Active Jobs (honest read-models over the real memory store) + Parts Catalog (read-only over a seeded inventory JSON joined with the catalog; computed low-stock flags). All four nav destinations now real.
> - **Recall eval scaffold** (S1, ADR-0003): `data/recall_evalset.json` (18 runs, 8 queries) + `recall_eval.py` + `scripts/run_recall_eval.py`. **Keyword baseline measured recall@1 = 0.750**; semantic ranker has a drop-in wiring point.
> - **Memory extension**: `record_run(total=)` + `recent()` + `revenue_total` (backward-compatible).
> - **UI redesign**: the Digital Apprentice pane is now ONE continuous stream — JetBrains-Mono trace cards with a connector rail + staggered fade-in/working-pulse/check-pop, a "Refine" divider, then chat turns, above a permanently docked chat input. Tabs dropped. `prefers-reduced-motion` respected.
> - **Tests: 67 → 89 pass** (+22). ruff + prettier clean.
> - ⚠️ **Pending live eyeball:** assistant verified via populated previews + headless empty-state screenshots; a real `FF_REAL_MODELS=1` forge + chat turn is the final user check.

Quillwright: a human-supervised, **local** small-model agent for tradespeople. Snap a job photo + voice note → an orchestra of small models (vision + tool-calling brain + multilingual) forges a finished, itemized **estimate**. No cloud. Built for the HuggingFace/Gradio "Build Small" hackathon (≤32B models, Gradio app, ends ~June 15).

---

## 1. How to run / test (orientation)

```bash
cd /Users/aaryaprakash/Development/random_projs/small-hackathon
source .venv/bin/activate

# Stub mode (fast, no GPU/models needed):
python -m quillwright.server            # http://127.0.0.1:7860

# REAL local models (needs Ollama running + models pulled):
ollama pull minicpm-v nemotron-3-nano:4b aya     # already pulled on this machine
FF_REAL_MODELS=1 python -m quillwright.server

# Tests + lint:
pytest -q                                          # 67 tests
ruff check . && ruff format --check .
npx prettier --check "quillwright/web/**/*"

# Brain accuracy eval (needs Ollama + FF_REAL_MODELS=1):
FF_REAL_MODELS=1 PYTHONPATH=. python scripts/run_brain_eval.py
```

**Run the server with `uvicorn`/`python -m quillwright.server`, NOT `.launch()`** — `gradio.Server` is a FastAPI app; `.launch()` does not serve our routes.

---

## 2. Architecture (where things live)

```
quillwright/
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
- ✅ Preview PDF / **Export JSON** / Finalize (download PDF) / Add Item / Discard.
- ✅ Language dropdown (English/Spanish/French/Mandarin) → live re-translate.
- ✅ Industrial-orange theme (Hanken/Inter/JetBrains Mono), minimalist (no useless UI).
- ✅ **(2026-06-08-late) Unified Apprentice stream**: mono trace cards + connector rail + staggered motion, docked conversational **chat** to refine the estimate (Facts-from-Tools), "Refine" divider between trace and chat.
- ✅ **(2026-06-08-late) Three secondary pages**: Dashboard / Active Jobs / Parts Catalog — real read-models, demoable-first (ADR-0010); all four nav links live.

### Infra / housekeeping

- ✅ Guardrail hooks in `.claude/` (ruff format-on-edit + block-lint-config). Verified firing.
- ✅ Retired obsolete `gr.Blocks` `app.py`; docs updated.
- ✅ ADRs 0001–0008 + CONTEXT.md glossary + problem-validation research (citable stats).

### Test/verification status

- ✅ **Automated: 89 pytest tests pass** (was 67; +22 from 2026-06-08-late: api export/chat/pages, recall_eval, memory totals/recent). Covers models, resolver, catalog, tools, agent incl. brain+pause+resume, pdf, ui presenters, api estimate/stream/pause/upload/recalc/translate/export/chat/pages, ollama backend, brain_tools, brain_loop, brain_eval, recall_eval, memory, memory_integration. ruff + prettier clean.
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
- ⚠️ **Memory is single global file** (`/tmp/quillwright_memory.json`) — no per-user separation; `/tmp` clears on reboot. Fine for demo, not multi-user.
- ⚠️ **Audio**: voice note is currently a TEXT transcript field — no real speech-to-text wired (Audio model role exists in resolver but unused). "Voice note" is typed, not spoken.

---

## 5. STRETCH GOALS — ranked (set in the 2026-06-08 grill; this is the living priority list)

Order is the user's. Only pursue once committed scope (§6 deployment + §7 build order) is solid; cut from the bottom.

1. **S1 — Recall eval** ✅ **DONE & MEASURED (2026-06-10)** — semantic Recall wired (`llama-nemotron-embed-1b-v2`); **keyword 0.750 → semantic 0.875 (+0.125)** on the 18-run / 8-query set. The Field-Notes data point is in hand (one honest remaining miss keeps it credible). Embedder is an opt-in `[embed]` extra (torch; not in the Space).
2. **S3 / S4 / S5 — sponsor-model block (equal priority):**
   - **S3 Aya fine-tune** via `cohere-ai/cohere-finetune` (easiest tooling of any sponsor; trade-vocab translation; cheap 2nd 🎯 point).
   - **S4 Nemotron Omni** as selectable Best-Stack Perception. **Coupled to the Modal backend (now committed §7.2):** Omni is too big to run locally via Ollama → it only runs _for real_ on Modal, so it rides the §7.2 backend once that exists. Cheap part (resolver dropdown) is high; running it = needs Modal.
   - **S5 Nemotron Parse** inference as an extraction tool (NVIDIA breadth; no fine-tune — no recipe).
3. **S10 — Finalize & Send (real email/SMS).** _Medium._ User has a Twilio account → real send is feasible. **Constraint:** Twilio creds can't live in a public HF Space → real send runs in the local/demo path; the hosted Space falls back to a draft/shareable-link.
4. **S7 — Agent-trace export** to the Hub (📡 Sharing-is-Caring). Trace is shown live, not yet exported.
   _(S6 Modal-backed live Space was PROMOTED to committed §7.2 on 2026-06-08 — no longer a stretch.)_
5. **S2 — Inventory live-decrement** (finalize subtracts parts). _The read-only Inventory page now EXISTS (2026-06-08-late)_; this stretch is only the live-decrement upgrade on top of it (ADR-0010); only if core solid.
6. **S8 — FLUX Klein** branded visuals (LoRA; delight/📡; off the core skill).
7. **S9 — `gr.Workflow`** orchestra node-graph demo (separate artifact, goodwill only; NEVER the core app — ADR-0010).
8. **S11 — deferred grab-bag, REVISIT FLAG.** GEPA/DSPy auto prompt-opt, live video capture, service-report mode, Parse/embed fine-tunes, ambiguity-pause variant. Explicitly deferred; some parts may be promoted later — revisit, don't enumerate now.

---

## 6. DEPLOYMENT — STUB SPACE LIVE (de-risk done); collateral + Modal pending

The hackathon requires: **a Gradio app hosted as a Hugging Face Space** + a demo video + a social post.

### ✅ Deployment status (2026-06-08) — phase 1 DONE

The #1 unknown is killed: **the bespoke `gr.Server`/FastAPI app runs as a Docker-SDK HF Space.**

- ✅ Space exists: **`build-small-hackathon/Quillwright`** (Docker SDK, `cpu-basic`), org membership confirmed. App domain: `https://build-small-hackathon-quillwright.hf.space`.
- ✅ `Dockerfile` + `requirements.txt` + `.dockerignore` + README front-matter (`sdk: docker`, `app_port: 7860`, hackathon tags). `server.py` honors `$FF_HOST`/`$PORT` (binds `0.0.0.0` in container; local dev unchanged).
- ✅ Verified locally (Docker build + run: serves Workspace + stub forge total $128.82) AND on HF (build succeeded, stage `RUNNING`, runtime logs show `GET / → 200` + all assets internally).
- ✅ Deployed via `hf upload` (commit 76a2f92) — NOT git push (HF git protocol failed on git 2.51 `expected 'acknowledgments'`; force-push correctly blocked by guardrails). Code also on GitHub `origin` = github.com/Aarya2004/Quillwright.

### ⚠️ OPEN LOOSE ENDS (do before submission)

- ⚠️ **Space is PRIVATE** → the public `*.hf.space` URL serves HF's 404/login wrapper to anonymous visitors (judges can't open it). **MUST flip to Public before submission** (Settings → Change visibility, or `hf repo settings ... --private false`). User will do this pre-submission, NOT at the last minute.
- ⚠️ **Public-serving path UNVERIFIED.** We proved the app serves _internally_ (authed/signed requests in runtime logs), but never tested an anonymous visitor hitting the live URL (private blocks it). **When flipped public, immediately re-smoke-test** with buffer before the deadline: `curl -s -o /dev/null -w "%{http_code}\n" https://build-small-hackathon-quillwright.hf.space/` → expect 200 (+ a stub forge POST). If it still 404s public, that's a new issue to chase.
- ℹ️ To update the Space after edits: `hf upload build-small-hackathon/Quillwright . --repo-type=space --exclude=...` (git push to `hf` remote is broken on this git version — use `hf upload`).

### The core deployment problem (see ADR-0005)

A HF Space runs models **server-side**. Free HF tier has **no GPU**; ZeroGPU is quota-limited (~3.5min/day free). Our real models (minicpm-v, nemotron, aya via Ollama) run great **locally on the dev Mac** but won't fit/perform on a free Space. Options:

1. **Hosted Space = stub/lightweight mode** (`FF_REAL_MODELS` off) so it runs on CPU, AND **film the real models running locally** as the demo video (the honest "airplane-mode / no-cloud" proof). ← simplest, recommended.
2. **Hosted Space backed by Modal GPU** (contest gives $250 Modal credits) — wire a `ModalModel` resolver backend (mirrors `OllamaModel`) calling Modal-hosted models. More work; gives a live real-model Space.
3. **Ollama inside the Space container** on CPU — works but slow.

### Deployment checklist

- ✅ Hosting strategy decided: **#1 stub Docker Space now** (done) + **#2 Modal-backed live models** (committed §7.2, user priority). NOT ZeroGPU (Gradio-SDK-only, breaks gr.Server — ADR-0005).
- ✅ Valid HF Space: `requirements.txt`, **Docker SDK** (resolved the gr.Server SDK caveat — Docker is sanctioned, no `app.py`/`sdk: gradio` needed), README front-matter (`sdk: docker`, `app_port: 7860`).
- ✅ Bundle `data/` (catalog + evalset) and `web/` into the Space.
- ✅ Stub mode works with zero external deps on the Space (verified — no GPU/Ollama needed).
- ✅ Test the deployed Space (stub path) — internally verified; ⚠️ public-anon path pending the Public flip (see loose ends above).
- ◻️ **Flip Space to Public + re-verify the public URL** (see ⚠️ loose ends).
- ◻️ **Modal**: implement `quillwright/backends/modal.py` + resolver `backend="modal"`, deploy model endpoints, set Space secret (= committed §7.2; de-risk one model first).
- ◻️ **Airplane-Mode Proof clip** — record the local real-model run with wifi off (🦙 + 🔌 quests).
- ◻️ Demo video (~90s; script in the Field Notes outline below).
- ◻️ Social post (link in Space README).
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
1. ✅ **DONE (2026-06-08) — Stub Docker Space (deployment de-risk).** `gr.Server` confirmed booting as a Docker-SDK Space; built + run locally AND deployed live (stage RUNNING). Only remaining: flip Public + verify the public URL (see §6 loose ends). Resolver Modal-readiness (env-flag backend) deferred to phase 2 itself.
2. ✅ **DONE (2026-06-10) — Modal Best-Stack BRAIN.** Nemotron 30B-A3B (FP8) on Modal via vLLM, proven end-to-end (`FF_BACKEND=modal` forge → correct estimate). De-risk scope satisfied (brain only). **Remaining for full Modal:** (a) vision (Omni) + multilingual still copy this pattern — NOT done; (b) the **live Space isn't wired to Modal** (needs `FF_BACKEND`/`FF_MODAL_BRAIN_URL` as Space secrets) — deferred given the $4.16 cost lesson + continuous-spend risk of a judge-clickable hosted GPU. Modal app currently STOPPED.
3. ✅ **DONE (2026-06-10) — Audio role.** `cohere-transcribe-03-2026` on-device via transformers (NOT llama.cpp — Conformer arch unsupported; that ADR-0009 assumption was wrong, verified). Mic capture → `/api/transcribe` → note field. Opt-in `[audio]` extra; gated repo. Spoken voice note is now REAL (was typed).
4. **Semantic Recall** — Llama-Nemotron-Embed (text) via sentence-transformers, record-time cached (ADR-0003).
5. ✅ **DONE (2026-06-08-late) — Secondary pages** — Dashboard / Active Jobs / Inventory shipped as honest read-models (Dashboard + Jobs over the real memory store; Inventory read-only over seeded JSON). Demoable-first satisfied (ADR-0010). _Only the live-inventory-decrement upgrade (S2) remains, and it's optional._
6. **MiniCPM-V fine-tune on CORD/SROIE** (Modal) — the 🎯 artifact; parallelizable, doesn't block the app (ADR-0006).
7. **Submission collateral** — demo video (~90s), social post (link in README), **Airplane-Mode Proof** clip.
8. 🟡 **PARTIAL (2026-06-11) — Document Capture / Nemotron Parse (ADR-0011).** `modal_parse_app.py` (real v1.2 recipe: bfloat16, GenerationConfig, downloads repo `postprocessing.py`+`latex2html.py`, returns clean `{blocks}`) + `backends/parse.py` (`ParseModel` → Observations + Proposed Line Items) + `ProposedLineItem`/`price_source="document"` models + `extraction` role wired + 9 block-parser tests. **127/127 green.** Not deployed (user tests first). **⚠️ HIGH PRIORITY — NOT YET WIRED TO THE WEB LAYER:** `ParseModel` produces the data but nothing calls it from `server.py`/the UI. Document Capture = an "Add document" upload → `ParseModel.parse_document` → surface Proposed Line Items in the Agent Pause for human confirm. **Without this, Parse is dead code from the user's POV — do not forget to wire it up.** Plan: deploy → run `/tmp/quote.png` to confirm real table markdown parses → then build the upload endpoint + Agent-Pause surfacing.

> **Trade-off noted (2026-06-08):** promoting Modal to #2 pushes the demo-visible feature work (spoken voice note, semantic Recall, the 3 pages) later. Conscious choice — a hosted Space that actually runs the models is a stronger submission spine than stub-Space + more features.

**Also pending (from original handoff):** user manual end-to-end pass with `FF_REAL_MODELS=1` + real photo (vision → brain → edit → PDF → Spanish).

---

## 8. Git state

- Branch `design/fieldforge` (BRANCH name unchanged despite the Quillwright project rename). **⚠️ The 6 commits from 2026-06-08-late (memory totals, pages, recall eval, export+chat, server routes, UI redesign) are LOCAL ONLY — not yet pushed to GitHub `origin` and the Space has NOT been re-uploaded.** Everything before them IS pushed to `origin` (github.com/Aarya2004/Quillwright) + deployed to the Space via `hf upload` (not git — HF git push broken on git 2.51). Remotes: `origin` (GitHub) + `hf` (Space).
- **Working tree NOT clean:** uncommitted branding assets in `quillwright/web/img/` (favicons/logos — yours, mid-iteration) + `.claude/scheduled_tasks.lock` (ignored harness file). The 6 feature commits are clean of those.
- Per user's CLAUDE.md: break changes into commits; ASK before committing (or user commits); NEVER push/PR without asking; TDD; fix lint at root cause (no suppression); verify before claiming done.
- Models pulled in Ollama on this machine: `minicpm-v` (5.5GB), `nemotron-3-nano:4b` (2.8GB), `aya` (4.8GB). Disk was tight (~11GB free) — removed gemma4/deepseek to make room; watch disk before pulling more.
