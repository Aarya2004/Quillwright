# LLM-driven Agent Brain — Plan

**Goal:** Replace the deterministic agent core with a real tool-calling loop driven by a local small model (nemotron-3-nano:4b via Ollama), while preserving Facts-from-Tools, pause/resume, and the streamed Trace.

**Why:** Make the "agentic small-model orchestra" genuine — the brain actually decides which tools to call — not scripted Python. The sponsor-aligned NVIDIA model does the reasoning; deterministic tools still own the numbers.

## Hard requirements (must not regress)
- **Facts-from-Tools (ADR-0004):** the LLM chooses *actions*; `lookup_price`/`compute` still produce every number. The model may NOT emit prices/totals itself.
- **Reliability (4B):** bounded step budget (e.g. max 12 tool calls), validate/repair on bad tool args, graceful stop. Never infinite-loop.
- **Pause/resume (ADR-0002):** missing-price still raises a LangGraph `interrupt`; resume continues the loop.
- **Streamed Trace:** every tool call emits a TraceStep (action, model, detail, status) so the UI keeps streaming.
- **Tests stay green; stub backend still works offline** (no Ollama needed for unit tests).

## Design

### Tool-calling backend
- Extend `OllamaModel` with a `chat(messages, tools)` method using Ollama's native `/api/chat` tool API (verified working with nemotron). Returns either text or `tool_calls`.
- `StubModel` gains a scriptable `chat()` returning canned tool_calls, so the agent loop is testable without Ollama.

### Tool registry (the brain's available tools)
Expose a subset as LLM tools (JSON schemas):
- `add_priced_item(item)` — looks up the catalog price (or pauses if missing) and adds the line item. Wraps lookup_price+compute+draft so the model can't touch numbers.
- `finish()` — signals the estimate is complete.
(Deliberately NARROW: the model decides *which items* to add and *when done*; the tool does the pricing. This is how we keep Facts-from-Tools while making the brain real.)

### The loop (new `agent.py`, still LangGraph for interrupt/checkpoint)
1. `perceive_node` (unchanged) — vision -> observations.
2. `brain_node` — seed the chat with a system prompt + the observations + transcript; loop:
   - call `model.chat(messages, tools)`
   - if `tool_calls`: execute each via the registry (a missing price -> `interrupt`), append tool results, emit TraceStep, continue
   - if `finish` called or step budget hit or plain text: stop
   - validate/repair: if a tool call has bad/unknown args, append a corrective tool message and retry (up to N)
3. `assemble_node` (unchanged) — build the Estimate from accumulated line items.

### Config / fallback
- Brain model configurable (default `nemotron-3-nano:4b`; `llama3.1:8b` selectable if nemotron proves flaky).
- If `FF_REAL_MODELS` is off, the brain uses the deterministic path (keep the current node as `_deterministic_brain`) so the app still runs with zero models. The LLM brain is the real-models path.

## Build sequence (TDD, commit each)
1. `OllamaModel.chat()` + `StubModel.chat()` (scriptable tool_calls) — unit tests with a fake post.
2. Tool registry: `add_priced_item` / `finish` with JSON schemas + a dispatcher; tests (incl. missing-price -> pause signal).
3. New `brain_node` loop over a scripted StubModel.chat: asserts it adds the right items, respects the step budget, emits trace, and pauses on missing price. (No Ollama.)
4. Wire into the graph behind the real-models flag; keep deterministic path as fallback. Full-suite green.
5. Live smoke test with real nemotron (manual, FF_REAL_MODELS=1): a couple of transcripts, confirm sane behavior; tune the system prompt.
6. Reliability pass: step budget, repair loop, bad-output handling; document observed quirks.

## Risks
- 4B tool-calling drift on multi-step — mitigated by the narrow tool surface (only add_priced_item/finish) + step budget + repair.
- Latency: each chat round-trip is ~1-3s; multiple items = several seconds. The streamed Trace masks it.
- Keep the deterministic fallback so a flaky brain never bricks the demo.
