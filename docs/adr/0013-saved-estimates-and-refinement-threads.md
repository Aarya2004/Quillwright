# Saved Estimates, Refinement Threads, and the single-tenant demo Account

We add per-Account persistence so the app reads as a real platform: a Tech can save
an Estimate, see it in a "My Estimates" list, reopen it across sessions, and resume the
refinement chat. All stored data (Saved Estimates, their Refinement Threads, Profile
Memory) is keyed by `account_id`. Because we sell to **solo tradespeople**, an Account ==
the one Tech == the business — there is no organization layer and no multi-tech sharing.

## Status

accepted

## Decisions

- **Single demo Account, no auth (this week).** The data model is multi-tenant-_shaped_
  (everything keyed by `account_id`) but bound to one fixed `account_id = "demo"` at
  startup. No login, no sessions, no password storage. Real login (swap the fixed key for
  a session lookup) is a deliberate post-hackathon extension — _not_ built before the
  deadline, on a soon-to-be-Public Space, with P0 blockers still open.

- **Estimate Store is separate from Episodic Memory.** Episodic Memory stays a pure,
  append-only, lossy Recall corpus (`{transcript, line_items: [str], total}`) — it serves
  the _agent_ and feeds the measured 0.875 Recall number; we don't perturb it. The
  **Estimate Store** holds full Estimate JSON (rates, units, tax*rate, provenance, id) and
  serves the \_user* (reopen and re-export). Different jobs, different stores.

- **JSON-on-disk behind a swappable `EstimateStore` interface** (`save / list / load /
delete`, keyed by `account_id`). NOT SQLite: an Estimate is a nested document (line items
  - refinement thread) that JSON models naturally, and SQLite's concurrency/query wins are
    irrelevant at demo scale. The interface is the seam a durable/multi-tenant backend slots
    into later.

- **Durable locally; ephemeral-or-gated on the Space.** The store is a real file locally —
  the full saved-estimates experience is demoed and **filmed locally**, where depth is
  judged. On the Public HF Space the store writes to a per-session temp dir (or the feature
  is gated), because the Space is one container / one filesystem / one `account_id="demo"`:
  a shared durable store would leak Judge A's job data to Judge B. This matches ADR-0005
  (local is the full experience; the Space is the CPU shop window) and keeps the claim
  honest — we do not advertise live cloud persistence we did not build.

- **Lifecycle: auto-save on forge-finish + explicit Save (mid-draft), update-in-place on
  edit, Discard deletes.** No "finalized/locked" status — an Estimate is an editable quote,
  not a system-of-record invoice.

- **Refinement Thread: persisted, resumable, but sanitized.** Post-forge chat turns are
  stored per Saved Estimate as `{human message, operation taken}` — **intents and ops only,
  never dollar figures**. On resume the model gets the sanitized thread for _reference
  resolution_ ("make _it_ 2 hours") but the **current Line Items for _numbers_**. Stale
  historical dollars never re-enter the model → Facts-from-Tools (ADR-0004) holds on the
  resume path. The Thread is a sibling of the Trace, not part of it (Trace = forge steps;
  Thread = human editing conversation).

- **Thread Compaction is deterministic.** A long Thread is kept inside the small model's
  context by folding the oldest turns into one mechanical "earlier in this estimate: …"
  line built _in code_ from the stored ops (last K turns kept verbatim) — never by asking a
  model to summarize. This is a second instance of Facts-from-Tools and a point worth
  showing in the Field Notes post. Invisible in the normal demo (3–4 turns); demonstrable
  on a deliberately deep thread.

- **Saved Estimates are frozen snapshots.** Reopening shows the exact numbers saved; the
  live catalog prices only _newly added_ lines (same as forging fresh today). Existing lines
  never silently re-price — an Estimate may already be a quote shown to a Customer. Both old
  and new numbers are tool-sourced (at save time vs now); neither is the model. Refreshing to
  current catalog prices, if ever wanted, is an explicit action, not an automatic surprise.

## Considered and rejected (for this week)

- **SQLite** — solves durability-equivalent-to-JSON (the cheap problem) but adds relational
  awkwardness for nested Estimates and does nothing for visitor isolation (the expensive
  problem). Negative value here.
- **Durable + isolated cloud persistence on the Space** (HF persistent disk / Dataset repo /
  Turso) — requires per-visitor identity, i.e. the auth we deliberately deferred, plus a
  privacy review before going Public. 2–3 day sink against a ~3-day runway with open P0s.

## Consequences

- The post-hackathon upgrade is "implement a durable `EstimateStore` backend + add login,"
  not a rewrite — everything is already keyed by `account_id` and the store is swappable.
- "My Estimates" on the live Space is session-scoped (resets on reload) by design; the
  durable experience is the local run + the demo video.
