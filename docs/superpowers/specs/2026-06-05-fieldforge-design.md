# Quillwright — Design Doc

_Build Small Hackathon (Gradio × Hugging Face) — June 5–15, 2026_
_Date: 2026-06-05 · Track: Backyard AI (with a dash of delight)_
_Companion docs: [`CONTEXT.md`](../../../CONTEXT.md) (glossary) · [`docs/adr/`](../../adr/) (ADRs 0001–0007)_

> **Quillwright** — a human-supervised, tool-using AI agent for tradespeople. Capture a job with a few photos and a voice note, and a team of small models autonomously forges the dreaded paperwork — an itemized **Estimate** (or service report) — that techs otherwise spend hours typing up at 6pm in the truck. Built on open small models, no third-party AI APIs, supervised by you, every number honest.

This spec reflects all decisions from the grilling session. Where a decision carries architectural weight, the governing ADR is cited.

---

## 1. The problem (validated)

Field-service workers (HVAC, roofing, electrical, restoration, inspection, contracting) do the job in the field, then manually write up the **Estimate / service report**. This write-up is the most-hated, most-quantified pain in the trade:

- Admin overhead **consumes 1–2 hours/day per technician** (handwritten reports, manual entry).
- Average **~22 min/report** → ~**275 hours/year per tech** (≈7 work-weeks) on paperwork instead of billable work.
- Home inspectors spend **1.5–2 hours writing every report**; cutting 1 hr/report ≈ **$24,000/yr** in lost opportunity.
- A multi-hundred-million-dollar market (ServiceTitan, Jobber, Housecall Pro, Spectora) sells on _"spend less time on paperwork"_; Jobber claims **~7 hrs/week** saved.

**Why it's still unsolved for the worker — and our wedge.** Incumbents are **expensive (per-seat + cloud), still make the tech manually build the estimate, fail offline, and lock in data.** Verified complaints map 1:1 onto our strengths:

| Incumbent complaint (verified)                                            | Quillwright answer                                     |
| ------------------------------------------------------------------------- | ----------------------------------------------------- |
| Per-seat cost / "tax on growth"; $245–398/tech/mo + $5–50k implementation | Open small models, no per-call AI tax                 |
| "Photos didn't sync until back at Wi-Fi"; manual paper reports            | Capture → deliverable produced in the moment          |
| Mobile app "clunky"; techs still tap pricebook + type narratives          | Autonomous capture → deliverable, not data entry      |
| "AI features half-baked"                                                  | The agentic AI _is_ the product                       |
| "Data export after leaving is extremely difficult"                        | Local-owned data; PDF **and** JSON export, no lock-in |

We do **the one dreaded part** better and export into whatever they already use. We do **not** replace their CRM/scheduling/payments (that's the tarpit).

### Why it fits _this_ hackathon

- **Honest small-model fit:** private + multi-step + free at the model layer → open small models are the right architecture (the contest's thesis). True offline is proven separately (Airplane-Mode Proof).
- **A DOER, not a chat:** a supervised, multi-step, tool-using agent producing real work product.
- **Sponsor-aligned:** every anchor sponsor is racing toward on-device, multimodal, _agentic_ small models.
- **Validatable & visual:** loud, reachable communities (r/HVAC, r/Roofing, r/xactimate, InterNACHI); a vivid before/after demo.

---

## 2. Scope (locked)

A **Gradio app on a Hugging Face Space**, compute on **Modal** (ADR-0005).

### 2.1 Irreducible Core (must ship, polished — ADR-0007)

Capture (photos + voice) → the supervised agent builds a **correct itemized Estimate live** (Facts-from-Tools) → **one Agent Pause + one human Interrupt** → inline-editable Estimate → **PDF export**. **Private Stack only (single Mode).** This _is_ the hero demo.

### 2.2 Layers added only after the core is flawless (cut from the end — ADR-0007)

1. Multilingual language toggle (Aya) — Cohere/Toronto closing beat.
2. Profile + Episodic memory + Recall — "learns your business."
3. Second Mode (Best Stack) + JSON export.
4. CORD/SROIE fine-tune + eval (🎯).
5. Service-report mode.
6. Live video capture.
7. FLUX visuals.
   (Airplane-Mode Proof filmed in parallel once the Private Stack runs.)

### 2.3 Non-goals (YAGNI)

No scheduling/dispatch/payments/CRM/accounting integration. No accounts/multi-user/cloud sync. Not a diagnostic/safety device. No LLM-invented numbers (ADR-0004).

> **Relaxed (2026-06-08, ADR-0010):** the "not a system of record" non-goal is _partially_ relaxed for three persistence-backed secondary pages — **Dashboard (System Overview)**, **Active Jobs List**, **Inventory** — which read/aggregate over the existing memory store. Governing constraint: **demoable-first is non-negotiable** (each page ships seeded-and-beautiful before any live-functional work; functional depth cuts from the end). This does NOT reintroduce CRM/scheduling/payments — those remain hard non-goals.

### 2.4 Secondary pages (ADR-0010 — demoable-first, then functional)

Three pages alongside the hero Workspace, each shipped in two stages (stage 1 gates stage 2):

1. **Dashboard / System Overview** — KPI cards + revenue, aggregated over past Runs. _Functional target_ (read-model over memory).
2. **Active Jobs List** — filterable table of past Runs. _Functional target_ (read-model over memory).
3. **Inventory / Parts** — stock view over a seeded inventory JSON. _Target: read-only (real "low stock" reads); live decrement on estimate finalize is a stretch._
   (`gr.Workflow` node-graph "orchestra" demo — low-priority stretch, a _separate_ artifact, never the core app or these pages.)

---

## 3. The model orchestra (verified, ≤32B)

Two **Modes** differ _only_ by which model fills each **Model Role** (endpoint swap — ADR-0001, renamed by ADR-0005). Both run on Modal.

- **Private Stack** = open small models, no third-party AI APIs (the contest's "no cloud APIs" ask).
- **Best Stack** = larger hosted sponsor models for quality.

> **Updated 2026-06-08 (ADR-0009) — this table supersedes the original.** The Agent Brain shipped is **NVIDIA Nemotron**, not gpt-oss (the gpt-oss mapping was never built; OpenAI's prize is Codex-attributed commits, not a model — out of scope). Perception stays **MiniCPM-V** in Private Stack to protect the OpenBMB $10k track (Omni is a _selectable_ Best-Stack alternative, not a swap). Audio + Embedding are filled additively.

| Model Role              | Private Stack                            | Best Stack (selectable)          | Modality            | Sponsor          |
| ----------------------- | ---------------------------------------- | -------------------------------- | ------------------- | ---------------- |
| **Perception**          | MiniCPM-V (live)                         | Nemotron 3 Nano Omni _(stretch)_ | image → text        | OpenBMB / NVIDIA |
| **Audio**               | Cohere Transcribe (2B, local GGUF)       | Nemotron 3 ASR / Omni            | audio → text        | Cohere / NVIDIA  |
| **Agent Brain**         | Nemotron 3 Nano 4B (live)                | Nemotron 3 Nano (30B/3B-active)  | text + tool-calling | NVIDIA           |
| **Multilingual**        | Cohere Aya (3.3B, live)                  | Aya larger / Command             | text → text         | Cohere           |
| **Embedding**           | Llama-Nemotron-Embed-1B (text, un-tuned) | —                                | text → vector       | NVIDIA           |
| **Extraction** _(tool)_ | —                                        | Nemotron Parse (<1B) inference   | image → JSON        | NVIDIA           |
| **Visual** _(stretch)_  | —                                        | Black Forest Labs FLUX.2 Klein   | text → image        | BFL              |

Tool-calling-tuned models de-risk the agent loop (Nemotron's agentic post-training + tool-use focus; MiniCPM4-MCP/MiniCPM5 speak MCP/BFCL-style calls).

---

## 4. Architecture

### 4.1 Flow

```
[Capture]              [Perceive]          [Agent: plan→act→self-check]        [Deliverable]
photos ─┐                                  ┌ perceive(image)→Observations       ┌ Estimate (itemized)
voice ──┼ Audio role→transcript ─ Brain ───┼ search_past_jobs(q)→Recall   ─draft┤  PDF + JSON
(typed) ┘                       (Nemotron) ├ lookup_price / compute            └ language toggle (Aya)
                                           ├ draft_line_item / flag_for_human
                                           └ translate / update_profile
                              ▲                                      │
                              └────── human: Agent Pause + Interrupt ┘
                                 (edits → shared state, applied at next step; Trace shown live + exported)
```

### 4.2 Components (focused, independently testable)

- **`resolver/`** — maps each Model Role → concrete model endpoint by Mode (ADR-0001/0005). Every Tool calls "the model for this role in this mode."
- **`capture/`** — Gradio modal: images + audio (+ optional text) → normalized `Capture`. Audio transcribed via the Audio role.
- **`perception/`** — wraps the Perception role. `perceive(image) → [Observation]`. No business logic.
- **`agent/`** — the Agent Brain (Nemotron 3 Nano): the plan→act→self-check loop, tool registry, human-in-the-loop checkpoints, and **Trace** emission. Re-derives its next step from current shared run-state each iteration (ADR-0002).
- **`tools/`** — the 8 Tools (§4.4).
- **`memory/`** — Profile (per-tech defaults) + Episodic (past Runs) + hybrid **Recall** (keyword pre-filter → semantic re-rank via the Embedding role) (ADR-0003).
- **`deliverable/`** — renders the inline-editable Estimate (and service report, stretch); recalcs via `compute`; exports PDF + JSON; language toggle via Aya.
- **`ui/`** — the two-panel **Workspace** (§5).

### 4.3 Data flow & correctness

`Capture` → `perception` → `[Observation]` → `agent` (routes tools) → `[Line Item]` → `deliverable`.
**Facts-from-Tools (ADR-0004):** any customer-facing number (price, qty, markup, tax, total) comes from a Tool (`lookup_price`, `compute`) or user-confirmed data — never from the Brain's free generation. Prices adapt deterministically (learn confirmed edits/prefs into catalog + Profile; novel items flagged, never guessed).

### 4.4 Tools (ADR-0004)

`perceive` · `search_past_jobs` · `lookup_price` · `compute` · `draft_line_item` · `flag_for_human` (→ Agent Pause) · `translate` · `update_profile`. `translate` has two entry points (UI language toggle + autonomous agent call) over one function.

### 4.5 Supervision (ADR-0002)

- **Agent Pause:** agent stops to ask on low-confidence/missing info, then resumes.
- **Interrupt:** human edits an Observation/Line Item anytime → written to shared state → picked up at the agent's _next step_ (no restart, no mid-step preemption). Short steps keep it feeling seamless.

### 4.6 Hosting & latency (ADR-0005)

Compute on Modal (contest $250 credits + winner pool). HF free tier has no GPU; ZeroGPU's ~3.5 min/day can't sustain a multi-model agent. **Cold-start mitigation:** keep containers warm during the demo + stream the Trace to mask per-step latency; optionally co-locate the Private Stack in one long-lived container per Run.

---

## 5. Frontend & interaction

- **Platform:** Gradio web app (HF Space), **laptop-first**, responsive-but-not-pixel-perfect on mobile. The field-phone story is told honestly in the pitch (models run server-side; the phone would be a thin client).
- **Aesthetic:** minimalist, functional, restrained — every element earns its place; custom theme + targeted CSS earns 🎨; no decorative pills/dead buttons.
- **Layout — the Workspace:** two panels — **Trace (left)** streaming the agent's steps, **Deliverable (right)** building live. Capture via a "New job" modal. One visible control: the **Mode toggle**. A small **active-model badge** per Trace step (e.g. `perceive → MiniCPM-V ⠋`) surfaces the orchestra through real work — no separate orchestra panel.
- **Flow:** Capture → autonomous **Run** (Trace + Estimate build) → **Agent Pause** inline when needed → human **Interrupt** anytime (inline edit) → finished, fully-editable Estimate → export (PDF + JSON) → **language toggle** (Aya).
- **Failure (graceful):** model/tool errors surface honestly in the Trace; the agent retries / falls back / raises an Agent Pause; partial work preserved; never a silent crash.

---

## 6. Memory (ADR-0003)

- **Profile Memory:** small persistent per-tech record (trade, common Line Items, markup, report tone, language). Read at Run start (resolves trade, user-overridable), updated after (and via `update_profile`).
- **Episodic Memory:** append-only past Runs (Capture summary + Deliverable + key Line Items).
- **Recall:** `search_past_jobs` = keyword/structured pre-filter → semantic re-rank (Embedding role: local in Private Stack, Cohere Embed in Best Stack).
- Demos require pre-seeding a Profile + a few past Runs (memory only shows value across jobs).

---

## 7. Correctness, testing, honesty

- **Facts-from-Tools** is the testable invariant: assert no customer-facing number lacks Tool/user-confirmed provenance.
- **Tool unit tests:** `compute`, `lookup_price` deterministic.
- **Perception fixtures:** real job photos with expected Observations.
- **Agent trace assertions:** fixed `Capture` → expected tool calls → structured Estimate, no fabricated numbers.
- **Golden deliverables:** snapshot end-to-end Estimates for regression.
- **Daily demo rehearsal** once the core runs.
- **Honesty banners:** "AI-generated draft — review before sending"; sample pricing is labeled; we state it's a drafting aid, not a system of record or safety device.

---

## 8. Fine-tune + eval (🎯 — ADR-0006)

Fine-tune a small model on the core task (doc/photo → structured Line-Item JSON) using a **public HF dataset** (CORD / SROIE / `longmaodata/Invoice-annotation`); report **baseline vs tuned field-level accuracy/F1** on a held-out split; publish the tuned model on HF. Reproducible benchmark → credible "X→Y accuracy" artifact for 📓 Field Notes. Stretch in sequencing; plan locked.

---

## 9. Demo (the judged artifact)

- **Hero narrative:** _"it does my dreaded paperwork"_ (the doer). Other features are supporting beats.
- **Structure (~90s, real-time lightly trimmed):** pain hook ("6pm in the truck") → Capture → live Run (Trace + Estimate building) → one **Agent Pause** answered → one human **Interrupt** (fix a price, recalcs live) → finished Estimate → **language-toggle** closer.
- **+ Airplane-Mode Proof:** filmed clip of the Private Stack via llama.cpp on a real machine, network off (🦙 + offline honesty).
- Plus the required social post.

---

## 10. Bonus quests

**Primary:** 🔌 Off the Grid (Private Stack, no third-party APIs) · 📡 Sharing is Caring (export the Trace) · 🎨 Off-Brand (custom minimalist frontend) · 📓 Field Notes (architecture + fine-tune eval write-up).
**Stretch:** 🦙 Llama Champion (llama.cpp + Airplane-Mode Proof) · 🎯 Well-Tuned (CORD/SROIE fine-tune).

## 11. Sponsor-prize surface

NVIDIA (Nemotron 3 Nano Agent Brain + Transcribe-alt/Omni/Parse/Embed; RTX prizes — community-vote lane too) · OpenBMB (MiniCPM-V perception, $10k special category — keep central) · Cohere (Transcribe Audio + Aya multilingual; Toronto) · Modal (hosting/compute credits + $20k Modal-credits prize; fine-tune host) · Black Forest Labs (stretch visuals). ⚠️ OpenAI prize (Codex-attributed commits, not a model) is OUT OF SCOPE — see ADR-0009.

---

## 12. Build sequence (10-day window, day 1 = June 5)

Build the **Irreducible Core** as a complete vertical slice first; later layers attach without rewiring it (ADR-0007).

1. Skeleton + contracts: Gradio app, `Capture`, tool registry, **resolver** (single Private Stack to start).
2. Perception tool: vision model → Observations; fixtures + tests.
3. Capture: image + audio(+transcript) + text → `Capture`.
4. Agent loop (core): Nemotron plan→act→self-check over `perceive`/`lookup_price`/`compute`/`draft_line_item`/`flag_for_human`; Facts-from-Tools; Trace emission.
5. Estimate deliverable: inline-editable, live-recalc, PDF export; golden snapshot.
6. Supervision: Agent Pause + human Interrupt (shared-state, between-steps).
7. Workspace polish (🎨): Trace panel + active-model badges; minimalist theme.
8. **— Core complete & rehearsed —** then layer (cut from the end): multilingual toggle → memory + Recall → Best Stack + JSON → fine-tune + eval → service report → video → FLUX.
9. Trace export (📡) + Field Notes (📓) + Airplane-Mode Proof (🦙).
10. Submission: demo video (real-time hero + airplane-mode clip) + social post + Space link.

---

## 13. Open questions (resolve during build)

- Best Private-Stack vision model for nameplates/serials within latency (MiniCPM-V 4.6 vs Nemotron Omni) — benchmark in step 2.
- Local STT sizing vs accuracy on noisy field audio.
- Sample pricing-catalog contents per demo trade (curated, clearly labeled sample data).
- Modal container shape: per-role vs co-located Private Stack; warm-pool cost during demo window.
- Exact public dataset + small base model for the fine-tune.
