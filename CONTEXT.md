# Quillwright

An on-device, human-supervised AI agent for tradespeople that turns a field capture (photos + voice note) into a finished, editable estimate or service report — the paperwork techs otherwise hand-write after a job.

## Language

**Capture**:
The raw multimodal input from a job — photos plus a voice note (and optional typed note) — normalized into one object the agent works from.
_Avoid_: upload, input, submission

**Observation**:
A single fact the perception model extracts from a photo — an item, part, damage, or piece of read text (e.g. a nameplate model number).
_Avoid_: detection, finding, result

**Document Capture**:
A second capture path: a document the tech or customer hands over — a spec sheet, supplier quote, or old written estimate — read by the Extraction Model Role (Nemotron Parse) into structured text + tables that feed the same Estimate pipeline. Distinct from a job-site photo (different input, different model); entered via its own control, never auto-classified.
_Avoid_: scan, OCR (Document Capture is the agent-facing capability; OCR is one mechanism)

**Proposed Line Item**:
A Line Item whose price came from a Document Capture, not the catalog — surfaced to the human as a proposal to confirm or edit before it enters the Estimate. The document is the _source_, but the price only becomes customer-facing once a human confirms it (an Agent Pause), preserving Facts-from-Tools.
_Avoid_: draft line (a Line Item is already a draft; "Proposed" specifically means awaiting human confirmation of a document-read price)

**Agent Brain**:
The orchestrator model that runs the plan → act → self-check loop and decides which Tools to call. There is exactly one.
_Avoid_: orchestrator, controller, LLM

**Tool**:
A callable capability the Agent Brain invokes. Tools are where facts (prices, math) come from; the Brain does routing and judgment, not arithmetic. The v1 set: `perceive`, `search_past_jobs`, `lookup_price`, `compute`, `draft_line_item`, `flag_for_human`, `translate`, `update_profile`.
_Avoid_: function, plugin, skill

**Facts-from-Tools**:
The correctness rule: any number that reaches the customer (price, quantity, markup, tax, total) must come from a Tool (`lookup_price`, `compute`) or user-confirmed data — never from the Agent Brain's free generation. This extends to **Document Capture**: a price read off a document by Nemotron Parse is a _model_ output, so it is never used directly — it becomes a Proposed Line Item the human confirms (the document is the source; the human is the gate).
_Avoid_: no-hallucination (too vague)

**Line Item**:
One priced row of an Estimate — description, quantity, unit, rate, subtotal.
_Avoid_: entry, row, charge

**Estimate**:
The hero Deliverable — an itemized, priced quote for a job. Editable draft, not a system-of-record invoice.
_Avoid_: quote, invoice, bill

**Service Report**:
The secondary Deliverable — a written record of findings, work done, and captioned photos. (Stretch beyond the Estimate.)
_Avoid_: inspection report (a regulated cousin we are deliberately not building)

**Deliverable**:
The finished work product the agent produces — an Estimate or a Service Report — that the human edits and exports.
_Avoid_: output, document, artifact

**Mode**:
The execution tier the user selects, distinguished by model class and data path (both hosted on Modal). **Private Stack** resolves every Model Role to an open small model (≤32B, no third-party AI APIs — the contest's "no cloud APIs" ask). **Best Stack** resolves roles to larger hosted sponsor models for higher quality. The two modes differ ONLY in which model each role resolves to — same loop, tools, UI, and Deliverable.
_Avoid_: Local/Connected (renamed — "Local" wrongly implied on-device inference; a hosted Gradio Space runs models server-side), offline/online, tier

**Airplane-Mode Proof**:
A separately filmed demonstration of the Private Stack running on a real local machine (via llama.cpp) with the network actually off — the honesty anchor for "small models genuinely work offline," distinct from the Modal-hosted Space.
_Avoid_: offline mode, local mode (those wrongly describe the hosted Space)

**Model Role**:
A named slot in the pipeline (Perception, Audio, Agent Brain, Multilingual, Embedding, Visual) that resolves to a concrete model depending on Mode.
_Avoid_: model (a Model Role is the slot; a model is what fills it)

**Trace**:
The recorded sequence of the Agent Brain's steps (thought, Tool call, result, confidence) — shown live in the UI and exportable to the Hub.
_Avoid_: log, history

**Workspace**:
The main two-panel screen — Trace streaming on the left, Deliverable building on the right — where the human watches and supervises the run. Laptop-first, gracefully stacked on mobile.
_Avoid_: dashboard, canvas, screen

**Run**:
One execution of the Agent Brain over a single Capture, from plan to finished Deliverable.
_Avoid_: session, job (a "job" is the real-world work; a Run is one agent execution over its Capture)

**Agent Pause**:
The agent stopping mid-Run to ask the human for a low-confidence or missing-info decision, then resuming.
_Avoid_: prompt, interrupt (reserve "interrupt" for the human-initiated kind)

**Interrupt**:
A human-initiated change during a Run (edit a Line Item, correct an Observation, redirect). Applied to shared state and picked up by the agent at the start of its next step — no restart.
_Avoid_: barge-in, cancel

**Profile Memory**:
A small persistent record of one tech's defaults — trade, common Line Items, markup, report tone, language. Read at the start of a Run (resolves the trade, user-overridable) and updated after.
_Avoid_: settings, preferences, config

**Episodic Memory**:
An append-only store of past Runs (Capture summary + final Deliverable + key Line Items) the agent can recall to inform a new Run.
_Avoid_: history, log, cache

**Recall**:
The agent retrieving relevant past Runs from Episodic Memory via hybrid search — a keyword/structured pre-filter then a semantic re-rank — exposed as the `search_past_jobs` Tool.
_Avoid_: lookup, query, retrieval (use "Recall" for this specific agent-facing capability)

## Relationships

- A **Capture** is turned into **Observations** by the Perception **Model Role**.
- The **Agent Brain** consumes **Observations** + the voice transcript, calls **Tools**, and produces **Line Items** → a **Deliverable**.
- Every **Model Role** resolves to a concrete model based on the active **Mode**.
- The **Agent Brain** emits a **Trace** of its steps.
- A human supervises: confirms **Observations**, answers low-confidence prompts, edits the **Deliverable** before export.

## Flagged ambiguities

- "voice handling" was unspecified — resolved: the **Audio** Model Role transcribes the voice note (Cohere Transcribe 2B in Private Stack; Nemotron 3 ASR / Nemotron Omni audio in Best Stack — see ADR-0009).
- "online/offline" was overloaded — resolved into the single term **Mode** (Private Stack vs Best Stack), an endpoint swap only. "Local Mode" was retired because a hosted Gradio Space runs models server-side (see ADR-0005); the true-offline claim lives in the **Airplane-Mode Proof**.
- "adapt prices" was ambiguous — resolved: deterministic learning from user-confirmed edits/prefs only; novel items are flagged, never LLM-guessed (**Facts-from-Tools**).
- "translate tool vs language toggle" overlapped — resolved: one underlying translate function, two entry points (human toggle + autonomous agent call).
- "Local/on-device" (the hero) vs hosting reality — resolved: real compute on Modal; "small/private" = open models + no third-party APIs; literal offline = the filmed **Airplane-Mode Proof**.

## Scope note

The **Irreducible Core** (ADR-0007) is the must-ship, polished slice: Capture → supervised agent builds a correct Estimate live → one Agent Pause + one Interrupt → editable Estimate → PDF, Private Stack only. All other designed features (second Mode, memory, multilingual, fine-tune, service report, video, FLUX) are layered on after the core is flawless and are cut from the end under time pressure.

## Implementation reality (as built)

- **Frontend** is a bespoke HTML/CSS/JS app served by `gradio.Server` (FastAPI), not Gradio components — the rule-compliant way to a smooth custom UI (the 🎨 Off-Brand path).
- **Private Stack runs genuinely locally via Ollama** (llama.cpp) on the dev machine — Perception = MiniCPM-V, Agent Brain = nemotron-3-nano:4b (NVIDIA Nemotron — NOT gpt-oss; the spec's gpt-oss mapping is superseded by ADR-0009) — gated by `FF_REAL_MODELS=1`; otherwise a deterministic/keyword stub. This realizes the "no cloud" claim directly on-device; Modal (ADR-0005) remains the option for hosted-Space compute.
- **Model orchestra (ADR-0009):** Perception = MiniCPM-V (protects the OpenBMB track; Nemotron Omni is a selectable Best-Stack alternative), Brain = Nemotron 3 Nano, Audio = Cohere Transcribe, Multilingual = Cohere Aya, Embedding = Llama-Nemotron-Embed-1B (un-tuned). The one shipped fine-tune is MiniCPM-V on CORD/SROIE (ADR-0006).
- The **Agent Brain is LLM-driven tool-calling** over a narrow surface (`add_priced_item` + `finish`); deterministic tools still own all numbers (Facts-from-Tools). Accuracy is tracked by an eval set (`data/brain_evalset.json`, `scripts/run_brain_eval.py`).
