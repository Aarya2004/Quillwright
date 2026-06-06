# Frontend on gr.Server — Plan

**Goal:** Replace the clunky `gr.Blocks` UI with a smooth, bespoke frontend (the user's HTML mockup) served by `gradio.Server`, calling the existing tested agent backend. Stays a Gradio app (rule-compliant) and earns the 🎨 Off-Brand quest.

**Why:** `gr.Blocks` auto-generates a generic, stiff UI that fights the bespoke design. `gradio.Server` (FastAPI + Gradio's API engine, confirmed available in our Gradio 6.16) serves our own HTML/CSS/JS at `/` and exposes Python functions via `@app.api`, with SSE streaming for the live Trace. The hackathon's Off-Brand hint points at exactly this.

**Untouched:** `models.py`, `resolver.py`, `catalog.py`, `tools.py`, `agent.py`, `pdf.py`, `ui.py` and all 25 tests stay green. The old `app.py` (gr.Blocks) is kept until the new path is approved — not deleted.

## File structure

```
fieldforge/
├── server.py              # gradio.Server: mount web/ static, register api endpoints. Glue only.
├── api/
│   ├── __init__.py
│   ├── estimate.py        # forge_estimate (stream), answer_pause, generate_pdf — adapt HTTP <-> agent.py
│   └── schemas.py         # request/response dataclasses for the endpoints
└── web/                   # the whole frontend (pure HTML/CSS/JS, no Python)
    ├── index.html         # Forge Estimate workspace (cleaned mockup)
    ├── css/
    │   ├── theme.css      # design tokens (colors/fonts/spacing) from the Tailwind config
    │   └── workspace.css  # Forge Estimate page styles
    ├── js/
    │   ├── client.js      # single wrapper around the API (@gradio/client / fetch). Only file that knows URLs.
    │   ├── trace.js       # renders the live AI Forge log from the stream
    │   └── workspace.js   # page logic: wire buttons, estimate table, pause card
    └── assets/            # icons/fonts/images (or CDN)
```

**Principles:** `web/` opens as a normal website on its own; one file = one job; `client.js` is the only place that knows API URLs; `api/` is a thin adapter over the tested agent (no business logic). New pages later = `web/<page>.html` + matching css/js + `api/<page>.py`.

## API endpoints (in `api/estimate.py`)

- `forge_estimate(transcript, trade) -> stream of events` — runs the agent; **streams** TraceStep events as they happen, then a final estimate payload. (SSE via `@app.api` streaming.)
- `answer_pause(thread_id, value) -> stream` — resumes the agent after an Agent Pause (Command(resume=value)); streams remaining steps + final estimate.
- `generate_pdf(estimate_json) -> file path/url` — calls `pdf.estimate_to_pdf`, returns the downloadable PDF.

Event shape (JSON lines): `{"type":"trace","step":{action,model,detail,status}}` … then `{"type":"estimate","data":{...}}` or `{"type":"pause","data":{reason,item,thread_id}}`.

## Build sequence (each step its own commit; ask before committing)

1. **Tiny proof.** `server.py` serving a minimal `web/index.html` + a non-streaming `forge_estimate` endpoint; click a button -> see the estimate JSON. Verify it serves and the call works. *Exit: HTTP 200 at /, button returns estimate.*
2. **Streaming.** Convert `forge_estimate` to stream TraceStep events; `trace.js` renders them appearing one-by-one. *Exit: steps stream visibly, not all-at-once.*
3. **Port the design.** Replace the minimal page with the cleaned full mockup (two-pane workspace, theme.css from the Tailwind tokens). Dead elements removed (side/mobile nav, notifications/settings/avatar, LIVE SYNC, Edit Manual) per the prior decision. *Exit: looks like the mockup, smooth.*
4. **Estimate table + summary.** Render line items into the right pane; inline-edit recalcs totals (calls compute via an endpoint or client-side mirror — decide in step). *Exit: edits update totals.*
5. **Agent Pause card.** When the stream emits a `pause`, show the question card; answering calls `answer_pause` and resumes. *Exit: pause -> answer -> resume works end-to-end.*
6. **PDF + footer actions.** Preview PDF (download), language dropdown rendered (multilingual activates in the post-core layer). *Exit: PDF downloads.*
7. **Switch entry point + retire app.py.** Make `server.py` the documented run target; remove/retire `app.py` only with explicit approval. *Exit: README updated, backend tests still 25/25.*

## Open questions to settle during build
- Inline-edit recalculation: round-trip to a `compute` endpoint (honest, server-authoritative) vs client-side mirror (snappier). Lean server-authoritative to preserve Facts-from-Tools; revisit if laggy.
- Streaming transport: `@app.api` SSE vs `@gradio/client` submit/iterator — pick whichever the installed Gradio 6.16 supports cleanly (verify in step 2).
- Whether to keep `ui.py` presenters (server-side HTML) or move trace rendering fully into `trace.js` (client-side). Lean client-side for smoothness; `ui.py` stays for tests/PDF.

## Risks
- `gr.Server` streaming API specifics in 6.16 may differ from docs — verify early (step 2), fall back to polling if needed.
- More web-dev surface to maintain than gr.Blocks — accepted tradeoff for the smooth feel.
