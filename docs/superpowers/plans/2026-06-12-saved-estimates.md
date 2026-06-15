# Saved Estimates & Refinement Threads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Estimates per Account so a tech can save, list, reopen, edit, and resume the refinement chat across sessions — making Quillwright read as a real platform.

**Architecture:** A new `EstimateStore` (JSON-on-disk, keyed by `account_id`, mirroring the existing `Memory` singleton in `api/estimate.py`) holds full Estimate JSON + a sanitized Refinement Thread per saved estimate. The chat engine (`api/chat.py`) is extended to accept and return the thread, replay it (sanitized, no dollars) to the model for reference resolution while numbers come live from the current rows, and compact it deterministically in code. A "My Estimates" page (mirroring the existing secondary pages in ADR-0010) lists and reopens. All decisions are recorded in **ADR-0013** and **CONTEXT.md**.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI (`gradio.Server`), pytest, vanilla JS/CSS frontend.

**Invariant (do not break):** Facts-from-Tools (ADR-0004). The model never emits a number. On resume it sees sanitized history (intents/ops, no dollars) for _references_ and the current Line Items for _numbers_. Saved Estimates are frozen snapshots; the live catalog prices only newly-added lines.

**Scope boundary (ADR-0013):** Single fixed `account_id="demo"`, no auth. JSON-on-disk behind a swappable interface. Durable locally; on the Space the store path is per-session/ephemeral. No "finalized/locked" status. No SQLite, no cloud persistence this week.

---

## File Structure

- **Create** `quillwright/estimate_store.py` — `EstimateStore` class: `save / list_estimates / load / delete`, keyed by `account_id`; persists full Estimate JSON + Refinement Thread + id + saved-at marker.
- **Create** `quillwright/thread.py` — Refinement Thread helpers: `append_turn`, `sanitized_history` (intents/ops, no dollars), `compact` (deterministic fold of old turns).
- **Modify** `quillwright/api/chat.py` — `chat_about_estimate` accepts `thread` + returns updated thread; `_model_chat` injects sanitized history into the prompt; records each turn's op.
- **Modify** `quillwright/api/estimate.py` — add an `EstimateStore` singleton (mirror `_memory()`), and auto-save on forge-finish.
- **Modify** `quillwright/server.py` — new endpoints: `POST /api/save_estimate`, `GET /api/estimates`, `GET /api/estimate/{id}`, `DELETE /api/estimate/{id}`; `GET /estimates` page; thread param on `/api/chat`.
- **Create** `quillwright/web/estimates.html` — "My Estimates" list page (mirror `jobs.html`).
- **Modify** `quillwright/web/js/client.js` — API functions for the new endpoints.
- **Modify** `quillwright/web/js/workspace.js` — Save button, thread state, reopen flow, send/receive thread on chat.
- **Modify** `quillwright/web/index.html` + `css/workspace.css` — Save button + "My Estimates" nav link.
- **Tests:** `tests/test_estimate_store.py`, `tests/test_thread.py`, extend `tests/test_api_chat.py`, new `tests/test_api_estimates.py`.

**ACCOUNT_ID:** a module constant `ACCOUNT_ID = os.environ.get("FF_ACCOUNT_ID", "demo")` in `estimate_store.py`. Everything keys off it. (The seam ADR-0013 calls out — later swapped for a session lookup.)

**STORE_PATH:** `os.environ.get("FF_ESTIMATE_STORE", "/tmp/quillwright_estimates")` — a directory; one JSON file per estimate id (`<account_id>/<id>.json`). On the Space, `FF_ESTIMATE_STORE` points at a per-session temp dir (set in the Dockerfile/launch, not hardcoded).

---

## Task 1: Refinement Thread helpers (sanitize + compact)

**Files:**

- Create: `quillwright/thread.py`
- Test: `tests/test_thread.py`

A Thread is `list[dict]`, each turn `{"message": str, "op": str}` where `op` is a terse, dollar-free intent line (e.g. `"added Compressor contactor"`, `"set Labor to 2"`, `"asked a question"`). `message` is the human's raw text (kept for display/replay; it is the human's words, not a model number). `sanitized_history` builds the model-facing context from `op` only.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_thread.py
from quillwright.thread import append_turn, sanitized_history, compact


def test_append_turn_records_message_and_op():
    thread = []
    out = append_turn(thread, message="add a contactor", op="added Compressor contactor")
    assert out == [{"message": "add a contactor", "op": "added Compressor contactor"}]
    # original not mutated (returns a new list)
    assert thread == []


def test_sanitized_history_uses_ops_only_no_dollars():
    thread = [
        {"message": "add a contactor", "op": "added Compressor contactor"},
        {"message": "make labor 2 hours", "op": "set Labor to 2"},
    ]
    hist = sanitized_history(thread)
    assert "added Compressor contactor" in hist
    assert "set Labor to 2" in hist
    assert "$" not in hist  # invariant: no dollar figures reach the model


def test_compact_keeps_last_k_verbatim_and_folds_the_rest():
    thread = [{"message": f"m{i}", "op": f"op{i}"} for i in range(6)]
    hist = compact(thread, keep_last=2)
    # old ops folded into ONE mechanical line; last 2 kept verbatim
    assert "earlier in this estimate" in hist.lower()
    assert "op0" in hist and "op3" in hist  # folded
    assert "op4" in hist and "op5" in hist  # verbatim tail
    # the fold is one line, not six
    assert hist.lower().count("earlier in this estimate") == 1


def test_compact_short_thread_no_fold():
    thread = [{"message": "m0", "op": "op0"}]
    hist = compact(thread, keep_last=2)
    assert "earlier in this estimate" not in hist.lower()
    assert "op0" in hist
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_thread.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quillwright.thread'`

- [ ] **Step 3: Write minimal implementation**

```python
# quillwright/thread.py
"""Refinement Thread: the sanitized, resumable record of post-forge chat turns
for one Saved Estimate (ADR-0013).

Each turn is {"message": <human text>, "op": <terse dollar-free intent>}. The
model-facing history is built from `op` ONLY — never dollar figures — so resuming
the conversation can never feed a stale number back to the model (Facts-from-Tools,
ADR-0004). Numbers always come live from the current Line Items, not from here.

Compaction is deterministic (code folds old ops into one line); no model summarizes
the thread — a second instance of Facts-from-Tools.
"""


def append_turn(thread: list[dict], message: str, op: str) -> list[dict]:
    """Return a new thread with one turn appended (does not mutate the input)."""
    return [*thread, {"message": message, "op": op}]


def sanitized_history(thread: list[dict]) -> str:
    """Model-facing history: the ops only, one per line. No dollars by construction."""
    return "\n".join(f"- {t['op']}" for t in thread if t.get("op"))


def compact(thread: list[dict], keep_last: int = 6) -> str:
    """Bounded model-facing history: fold all but the last `keep_last` ops into one
    mechanical 'earlier in this estimate: …' line; keep the tail verbatim."""
    if len(thread) <= keep_last:
        return sanitized_history(thread)
    head, tail = thread[:-keep_last], thread[-keep_last:]
    folded = "; ".join(t["op"] for t in head if t.get("op"))
    lines = [f"- earlier in this estimate: {folded}"]
    lines += [f"- {t['op']}" for t in tail if t.get("op")]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_thread.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add quillwright/thread.py tests/test_thread.py
git commit -m "feat(thread): sanitized + deterministically-compacted Refinement Thread helpers"
```

---

## Task 2: EstimateStore (save / list / load / delete, keyed by account)

**Files:**

- Create: `quillwright/estimate_store.py`
- Test: `tests/test_estimate_store.py`

Mirrors the `Memory` JSON pattern. One file per estimate at `<store_path>/<account_id>/<id>.json`. An id is a zero-padded sequence (`"0001"`) derived from existing files — deterministic, offline-friendly, like `Memory.recent`'s sequence ids (no wall-clock, no uuid, keeps tests deterministic). A stored record is `{id, account_id, estimate: <full Estimate JSON>, thread: <list>, saved_seq: <int>}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_estimate_store.py
import pytest
from quillwright.estimate_store import EstimateStore

EST = {
    "job_title": "AC Unit Repair — 123 Maple St",
    "line_items": [
        {"description": "Dual run capacitor", "quantity": 1, "unit": "ea",
         "rate": 24.0, "subtotal": 24.0, "price_source": "catalog"},
    ],
    "subtotal": 24.0, "tax_rate": 0.13, "tax": 3.12, "total": 27.12,
}


@pytest.fixture
def store(tmp_path):
    return EstimateStore(path=str(tmp_path), account_id="demo")


def test_save_returns_id_and_load_round_trips(store):
    rec = store.save(estimate=EST, thread=[])
    assert rec["id"]
    loaded = store.load(rec["id"])
    assert loaded["estimate"]["total"] == 27.12
    assert loaded["estimate"]["job_title"] == EST["job_title"]
    assert loaded["thread"] == []


def test_save_update_in_place_same_id(store):
    rec = store.save(estimate=EST, thread=[])
    updated = {**EST, "total": 99.99}
    rec2 = store.save(estimate=updated, thread=[{"message": "m", "op": "o"}], id=rec["id"])
    assert rec2["id"] == rec["id"]
    assert store.load(rec["id"])["estimate"]["total"] == 99.99
    assert store.load(rec["id"])["thread"] == [{"message": "m", "op": "o"}]
    # still exactly one estimate
    assert len(store.list_estimates()) == 1


def test_list_estimates_newest_first_with_summary(store):
    store.save(estimate={**EST, "job_title": "Job A"}, thread=[])
    store.save(estimate={**EST, "job_title": "Job B", "total": 50.0}, thread=[])
    listed = store.list_estimates()
    assert [e["job_title"] for e in listed] == ["Job B", "Job A"]  # newest first
    assert listed[0]["total"] == 50.0
    assert listed[0]["id"]  # id present for the reopen link


def test_delete_removes(store):
    rec = store.save(estimate=EST, thread=[])
    store.delete(rec["id"])
    assert store.list_estimates() == []
    assert store.load(rec["id"]) is None


def test_accounts_are_isolated(tmp_path):
    a = EstimateStore(path=str(tmp_path), account_id="demo")
    b = EstimateStore(path=str(tmp_path), account_id="other")
    a.save(estimate=EST, thread=[])
    assert len(a.list_estimates()) == 1
    assert b.list_estimates() == []  # other account sees nothing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_estimate_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quillwright.estimate_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# quillwright/estimate_store.py
"""EstimateStore: per-Account persistence of Saved Estimates + Refinement Threads
(ADR-0013).

JSON-on-disk behind a small, swappable interface (save / list / load / delete),
keyed by `account_id`. Separate from Episodic Memory (memory.py), which stays a
pure append-only Recall corpus. One file per estimate at
`<path>/<account_id>/<id>.json`. Ids are zero-padded sequence numbers (deterministic
and offline-friendly, like Memory's sequence ids — no uuid/wall-clock).

Durable locally; on the hosted Space `path` points at a per-session temp dir so
visitors never see each other's data (the Space is one container / one account).
"""

import json
import os

ACCOUNT_ID = os.environ.get("FF_ACCOUNT_ID", "demo")
STORE_PATH = os.environ.get("FF_ESTIMATE_STORE", "/tmp/quillwright_estimates")


class EstimateStore:
    def __init__(self, path: str = STORE_PATH, account_id: str = ACCOUNT_ID):
        self._dir = os.path.join(path, account_id)
        self._account_id = account_id

    def _ensure_dir(self) -> None:
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, id: str) -> str:
        return os.path.join(self._dir, f"{id}.json")

    def _next_id(self) -> str:
        if not os.path.isdir(self._dir):
            return "0001"
        existing = [f[:-5] for f in os.listdir(self._dir) if f.endswith(".json")]
        nums = [int(e) for e in existing if e.isdigit()]
        return f"{(max(nums) + 1 if nums else 1):04d}"

    def save(self, estimate: dict, thread: list[dict], id: str | None = None) -> dict:
        """Create (id=None) or update-in-place (id given) a Saved Estimate."""
        self._ensure_dir()
        if id is None:
            id = self._next_id()
        rec = {
            "id": id,
            "account_id": self._account_id,
            "estimate": estimate,
            "thread": thread,
            "saved_seq": int(id),
        }
        with open(self._path(id), "w") as f:
            json.dump(rec, f, indent=2)
        return rec

    def load(self, id: str) -> dict | None:
        path = self._path(id)
        if not os.path.isfile(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_estimates(self) -> list[dict]:
        """Saved estimates newest-first, each a list-row summary (id + title + total)."""
        if not os.path.isdir(self._dir):
            return []
        recs = []
        for fname in os.listdir(self._dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(self._dir, fname)) as f:
                rec = json.load(f)
            est = rec.get("estimate", {})
            recs.append({
                "id": rec["id"],
                "job_title": est.get("job_title", "Estimate"),
                "total": est.get("total"),
                "saved_seq": rec.get("saved_seq", 0),
            })
        recs.sort(key=lambda r: r["saved_seq"], reverse=True)
        return recs

    def delete(self, id: str) -> None:
        path = self._path(id)
        if os.path.isfile(path):
            os.remove(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_estimate_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add quillwright/estimate_store.py tests/test_estimate_store.py
git commit -m "feat(store): per-account EstimateStore (save/list/load/delete) on JSON-on-disk"
```

---

## Task 3: Chat records ops into the thread + replays sanitized history

**Files:**

- Modify: `quillwright/api/chat.py`
- Test: `tests/test_api_chat.py` (extend)

Extend the shared ops to return an `op` string, thread it through `chat_about_estimate`, and inject `compact(thread)` into the model prompt. The keyword path also records ops so the stub Space builds a thread.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_chat.py (append)
from quillwright.api.chat import chat_about_estimate

ROWS = [
    {"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0},
    {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
]


def test_chat_returns_updated_thread_with_op():
    out = chat_about_estimate("add a contactor", [dict(r) for r in ROWS], thread=[])
    assert "thread" in out
    assert len(out["thread"]) == 1
    assert out["thread"][0]["message"] == "add a contactor"
    assert out["thread"][0]["op"]  # a non-empty intent line
    assert "$" not in out["thread"][0]["op"]  # invariant: no dollars in the op


def test_chat_thread_accumulates_across_turns():
    out1 = chat_about_estimate("add a contactor", [dict(r) for r in ROWS], thread=[])
    out2 = chat_about_estimate(
        "remove the capacitor",
        out1["estimate"]["line_items"],
        thread=out1["thread"],
    )
    assert len(out2["thread"]) == 2


def test_chat_thread_default_empty_when_omitted():
    out = chat_about_estimate("change labor to 2 hours", [dict(r) for r in ROWS])
    assert out["thread"][0]["op"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_chat.py -k "thread" -v`
Expected: FAIL — `chat_about_estimate() got an unexpected keyword argument 'thread'` (and KeyError on `"thread"`)

- [ ] **Step 3: Write minimal implementation**

In `quillwright/api/chat.py`:

(a) Each `_op_*` already returns `{"reply": ...}`. Add an `"op"` key to each:

```python
# in _op_add, success branch:
    return {
        "reply": f"Added {qty:g} × {priced['description']} at ${priced['rate']:.2f} from the catalog.",
        "op": f"added {priced['description']}",
    }
# in _op_add, not-found branch: add  "op": "tried to add an unknown part"
# in _op_remove success:           "op": f"removed {removed['description']}"
# in _op_remove not-found:          "op": "tried to remove an unmatched item"
# in _op_change_qty success:        "op": f"set {rows[i]['description']} to {quantity:g}"
# in _op_change_qty failure:        "op": "asked to change a quantity (unclear)"
```

(b) Replace `_finish` and add thread handling:

```python
from quillwright.thread import append_turn, compact


def _finish(rows, tax_rate, reply, op, thread, message, needs_price=False):
    est = recalc_estimate(rows, job_title="Estimate", tax_rate=tax_rate)
    new_thread = append_turn(thread, message=message, op=op) if op else thread
    return {"estimate": est, "reply": reply, "needs_price": needs_price, "thread": new_thread}
```

(c) `_model_chat` injects compacted history and passes message/op through:

```python
def _model_chat(message, rows, tax_rate, model, thread):
    rows_summary = (
        ", ".join(f"{r['description']} (qty {r['quantity']:g})" for r in rows) or "(empty)"
    )
    history = compact(thread)
    user = (
        (f"Earlier edits:\n{history}\n\n" if history else "")
        + f"Current estimate: {rows_summary}\nRequest: {message}"
    )
    messages = [
        {"role": "system", "content": _CHAT_SYSTEM},
        {"role": "user", "content": user},
    ]
    msg = model.chat(messages, CHAT_TOOLS)
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        text = (msg.get("content") or "").strip()
        return _finish(rows, tax_rate, text or "Let me know what you'd like to change.",
                       op="asked a question", thread=thread, message=message)
    fn = tool_calls[0].get("function", {})
    result = _apply_model_call(fn.get("name", ""), fn.get("arguments", {}) or {}, rows)
    return _finish(rows, tax_rate, result["reply"], op=result.get("op", ""),
                   thread=thread, message=message, needs_price=result.get("needs_price", False))
```

(d) `_keyword_chat` passes `message`/`op` to each `_finish` call. For each branch, pass the matching `result["op"]`; for the two guidance fall-throughs (empty input / unrecognized), pass `op=""` (no thread turn for non-edits that aren't even questions). Example for the remove branch:

```python
    if re.search(r"\b(remove|delete|drop|take off|get rid of)\b", msg):
        result = _op_remove(rows, msg)
        return _finish(rows, tax_rate, result["reply"], op=result.get("op", ""),
                       thread=thread, message=message)
```

(e) `chat_about_estimate` gains `thread`:

```python
def chat_about_estimate(message, rows, tax_rate=0.13, model=None, thread=None):
    rows = [dict(r) for r in rows]
    thread = list(thread or [])
    brain = model if model is not None else _resolve_brain()
    if brain is not None:
        return _model_chat(message, rows, tax_rate, brain, thread)
    return _keyword_chat(message, rows, tax_rate, thread)
```

Update `_keyword_chat`'s signature to `(message, rows, tax_rate, thread)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_chat.py -v`
Expected: PASS (existing chat tests still green + 3 new thread tests pass)

- [ ] **Step 5: Commit**

```bash
git add quillwright/api/chat.py quillwright/thread.py tests/test_api_chat.py
git commit -m "feat(chat): record sanitized ops into the Refinement Thread + replay compacted history"
```

---

## Task 4: API endpoints — save / list / load / delete + thread on /api/chat

**Files:**

- Modify: `quillwright/server.py`
- Modify: `quillwright/api/estimate.py` (EstimateStore singleton + reset for tests)
- Test: `tests/test_api_estimates.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_estimates.py
import pytest
from fastapi.testclient import TestClient
from quillwright.server import app
import quillwright.api.estimate as est_api

client = TestClient(app)

EST_ROWS = [{"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0}]


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FF_ESTIMATE_STORE", str(tmp_path))
    est_api.reset_estimate_store()
    yield
    est_api.reset_estimate_store()


def test_save_then_list_then_load():
    r = client.post("/api/save_estimate", json={
        "rows": EST_ROWS, "job_title": "Test Job", "tax_rate": 0.13, "thread": [],
    })
    assert r.status_code == 200
    id = r.json()["id"]

    listed = client.get("/api/estimates").json()
    assert listed["estimates"][0]["job_title"] == "Test Job"
    assert listed["estimates"][0]["id"] == id

    loaded = client.get(f"/api/estimate/{id}").json()
    assert loaded["estimate"]["line_items"][0]["description"] == "Labor"
    assert loaded["estimate"]["total"] == pytest.approx(101.7)  # 90 * 1.13


def test_save_update_in_place():
    id = client.post("/api/save_estimate", json={"rows": EST_ROWS, "job_title": "J", "thread": []}).json()["id"]
    client.post("/api/save_estimate", json={
        "rows": EST_ROWS + [{"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0}],
        "job_title": "J", "thread": [], "id": id,
    })
    assert len(client.get("/api/estimates").json()["estimates"]) == 1


def test_delete():
    id = client.post("/api/save_estimate", json={"rows": EST_ROWS, "job_title": "J", "thread": []}).json()["id"]
    assert client.delete(f"/api/estimate/{id}").status_code == 200
    assert client.get("/api/estimates").json()["estimates"] == []


def test_load_missing_returns_404():
    assert client.get("/api/estimate/9999").status_code == 404


def test_chat_endpoint_passes_and_returns_thread():
    out = client.post("/api/chat", json={
        "message": "add a contactor", "rows": EST_ROWS, "tax_rate": 0.13, "thread": [],
    }).json()
    assert "thread" in out and len(out["thread"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_estimates.py -v`
Expected: FAIL — 404s / `AttributeError: reset_estimate_store` / missing `thread` key

- [ ] **Step 3: Write minimal implementation**

In `quillwright/api/estimate.py` (mirror the `_memory()` singleton):

```python
from quillwright.estimate_store import EstimateStore

_ESTIMATE_STORE: EstimateStore | None = None


def estimate_store() -> EstimateStore:
    global _ESTIMATE_STORE
    if _ESTIMATE_STORE is None:
        _ESTIMATE_STORE = EstimateStore()
    return _ESTIMATE_STORE


def reset_estimate_store() -> None:
    """Drop the in-process store (re-reads env path next use). For tests."""
    global _ESTIMATE_STORE
    _ESTIMATE_STORE = None


def save_estimate_record(rows, job_title, tax_rate, thread, id=None) -> dict:
    """Recalc to authoritative numbers (Facts-from-Tools), then persist the snapshot."""
    from quillwright.api.recalc import recalc_estimate

    est = recalc_estimate(rows, job_title=job_title, tax_rate=tax_rate)
    return estimate_store().save(estimate=est, thread=thread, id=id)
```

In `quillwright/server.py` add endpoints and thread the chat param:

```python
from quillwright.api.estimate import (
    save_estimate_record, estimate_store,  # add to the existing import
)


@app.post("/api/save_estimate")
def api_save_estimate(payload: dict = Body(...)) -> dict:
    rec = save_estimate_record(
        payload.get("rows", []),
        job_title=payload.get("job_title", "Estimate"),
        tax_rate=payload.get("tax_rate", 0.13),
        thread=payload.get("thread", []),
        id=payload.get("id"),
    )
    return {"id": rec["id"]}


@app.get("/api/estimates")
def api_estimates() -> dict:
    return {"estimates": estimate_store().list_estimates()}


@app.get("/api/estimate/{id}")
def api_estimate(id: str):
    rec = estimate_store().load(id)
    if rec is None:
        return HTMLResponse("not found", status_code=404)
    return rec


@app.delete("/api/estimate/{id}")
def api_delete_estimate(id: str) -> dict:
    estimate_store().delete(id)
    return {"ok": True}
```

Update the existing `/api/chat` handler to pass + return the thread:

```python
@app.post("/api/chat")
def api_chat(payload: dict = Body(...)) -> dict:
    return chat_about_estimate(
        payload.get("message", ""),
        payload.get("rows", []),
        tax_rate=payload.get("tax_rate", 0.13),
        thread=payload.get("thread", []),
    )
```

Note: `api_estimate` returns an `HTMLResponse` 404 to match the codebase's existing `static_files` 404 idiom; the success path returns the dict (FastAPI serializes it). If a stricter JSON 404 is wanted, that's a follow-up — not needed for the tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_estimates.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `pytest -q`
Expected: PASS (all prior tests + new ones)

- [ ] **Step 6: Commit**

```bash
git add quillwright/server.py quillwright/api/estimate.py tests/test_api_estimates.py
git commit -m "feat(api): save/list/load/delete estimate endpoints + thread on /api/chat"
```

---

## Task 5: Auto-save on forge-finish

**Files:**

- Modify: `quillwright/api/estimate.py`
- Test: `tests/test_api_estimates.py` (extend)

When a forge completes, auto-create a Saved Estimate so "My Estimates" populates naturally (ADR-0013 lifecycle). The forge entry points are `forge_estimate` / `forge_estimate_stream`. Auto-save the assembled estimate at completion. This task wires it at the non-streaming `forge_estimate` return and at the stream's terminal event.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_estimates.py (append)
from quillwright.api.estimate import forge_estimate


def test_forge_autosaves_to_store(fresh_store):
    result = forge_estimate("replaced the capacitor and contactor, one hour labor", "hvac")
    assert result["estimate"]["line_items"]
    listed = client.get("/api/estimates").json()["estimates"]
    assert len(listed) == 1  # the finished forge auto-saved
```

(Note: `fresh_store` is the autouse fixture; naming it as a param just makes the dependency explicit.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_estimates.py::test_forge_autosaves_to_store -v`
Expected: FAIL — `assert 0 == 1` (forge does not save yet)

- [ ] **Step 3: Write minimal implementation**

Find the `return` of `forge_estimate` (the assembled-estimate dict, ~`api/estimate.py:116+`). Before returning, auto-save:

```python
    # ADR-0013: auto-save the finished estimate so "My Estimates" populates.
    est = result["estimate"]  # the dict already shaped for the client
    try:
        estimate_store().save(estimate=est, thread=[])
    except Exception:  # noqa: BLE001 — persistence is best-effort; never fail a forge
        pass
    return result
```

Apply the same best-effort save at the stream's terminal "estimate complete" event in `forge_estimate_stream` (after the final estimate dict is assembled, before/with the final yielded event). Use the same `estimate_store().save(estimate=<final est dict>, thread=[])` call guarded by try/except.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_estimates.py::test_forge_autosaves_to_store -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS (confirm no forge/stream test regressed)

- [ ] **Step 6: Commit**

```bash
git add quillwright/api/estimate.py tests/test_api_estimates.py
git commit -m "feat(forge): auto-save the finished estimate to the per-account store (ADR-0013)"
```

---

## Task 6: Frontend — Save button, thread state, client API functions

**Files:**

- Modify: `quillwright/web/js/client.js`
- Modify: `quillwright/web/js/workspace.js`
- Modify: `quillwright/web/index.html`
- Modify: `quillwright/web/css/workspace.css`

No automated JS tests exist (the JS is verified via `node --check` + headless screenshots, per PROGRESS). Verification here is `node --check` + a manual/headless smoke. Keep changes minimal and mirror existing patterns.

- [ ] **Step 1: Add client API functions**

In `quillwright/web/js/client.js` (mirror the existing `fetch` helpers; `chatAboutEstimate` must now send + the page tracks the returned thread):

```javascript
export async function saveEstimate(rows, jobTitle, taxRate, thread, id) {
  const res = await fetch("/api/save_estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, job_title: jobTitle, tax_rate: taxRate, thread, id }),
  });
  return res.json();
}

export async function listEstimates() {
  const res = await fetch("/api/estimates");
  return res.json();
}

export async function loadEstimate(id) {
  const res = await fetch(`/api/estimate/${id}`);
  if (!res.ok) return null;
  return res.json();
}
```

Update `chatAboutEstimate` to send the thread:

```javascript
export async function chatAboutEstimate(message, rows, taxRate, thread) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, rows, tax_rate: taxRate, thread }),
  });
  return res.json();
}
```

- [ ] **Step 2: Track thread + saved id in workspace.js**

Add module state near `let rows` (line ~28):

```javascript
let refinementThread = []; // ADR-0013: sanitized post-forge chat turns
let savedId = null; // id of this estimate in the store (null until saved/forged)
```

In `sendChat` (line ~404), send + adopt the thread, then persist:

```javascript
const out = await chatAboutEstimate(text, rows, TAX_RATE, refinementThread);
typing.remove();
appendMsg("bot", out.reply);
if (out.thread) refinementThread = out.thread;
if (out.estimate) setEstimate(out.estimate);
// Persist the refined estimate + thread in place (best-effort).
saveCurrent();
```

Add a `saveCurrent` helper (update-in-place via `savedId`):

```javascript
async function saveCurrent() {
  try {
    const out = await saveEstimate(rows, JOB_TITLE, TAX_RATE, refinementThread, savedId);
    if (out && out.id) savedId = out.id;
  } catch {
    /* best-effort; never block the UI on persistence */
  }
}
```

Reset state in `newEstimate` (find where rows reset): set `refinementThread = []; savedId = null;`.

- [ ] **Step 3: Add the Save button**

In `index.html`, next to the estimate actions (Add Item / Preview PDF / Export JSON), add:

```html
<button id="save-btn" class="btn-ghost" type="button">Save</button>
```

Wire it in `workspace.js` near the other listeners (line ~432):

```javascript
$("save-btn").addEventListener("click", saveCurrent);
```

Import the new functions at the top of `workspace.js` alongside `chatAboutEstimate`:

```javascript
  saveEstimate,
  listEstimates,
  loadEstimate,
```

- [ ] **Step 4: Verify the JS parses**

Run: `node --check quillwright/web/js/client.js && node --check quillwright/web/js/workspace.js`
Expected: no output (exit 0)

- [ ] **Step 5: Prettier**

Run: `npx prettier --write --ignore-unknown "quillwright/web/**/*"`
Expected: files formatted, no errors

- [ ] **Step 6: Commit**

```bash
git add quillwright/web/js/client.js quillwright/web/js/workspace.js quillwright/web/index.html quillwright/web/css/workspace.css
git commit -m "feat(ui): Save button + thread-aware chat + in-place persistence"
```

---

## Task 7: "My Estimates" page (list + reopen)

**Files:**

- Create: `quillwright/web/estimates.html`
- Modify: `quillwright/server.py` (route)
- Modify: `quillwright/web/index.html` (nav link) + `css/workspace.css`
- Test: `tests/test_api_pages.py` (extend — route serves HTML)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_pages.py (append)
def test_estimates_page_served():
    from fastapi.testclient import TestClient
    from quillwright.server import app
    r = TestClient(app).get("/estimates")
    assert r.status_code == 200
    assert "My Estimates" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_pages.py::test_estimates_page_served -v`
Expected: FAIL — 404 (no `/estimates` route)

- [ ] **Step 3: Add the route + page**

In `quillwright/server.py` (mirror `jobs_page`):

```python
@app.get("/estimates", response_class=HTMLResponse)
def estimates_page() -> str:
    return (WEB / "estimates.html").read_text()
```

Create `quillwright/web/estimates.html` mirroring `jobs.html`'s structure (same nav sidebar + header). The body lists estimates and links each to the workspace with the id as a query param, so the workspace can reopen it:

```html
<!-- estimates.html: mirror jobs.html's shell; key content: -->
<h1>My Estimates</h1>
<ul id="estimate-list"></ul>
<script type="module">
  import { listEstimates } from "./js/client.js";
  const out = await listEstimates();
  const ul = document.getElementById("estimate-list");
  if (!out.estimates.length) {
    ul.innerHTML = "<li>No saved estimates yet — forge one to begin.</li>";
  } else {
    ul.innerHTML = out.estimates
      .map(
        (e) =>
          `<li><a href="/?estimate=${e.id}">${e.job_title}</a>` +
          `<span>${e.total != null ? "$" + e.total.toFixed(2) : ""}</span></li>`,
      )
      .join("");
  }
</script>
```

(Match the actual `jobs.html` markup/classes when implementing — read it first so the nav + styling are consistent.)

- [ ] **Step 4: Add the nav link**

In `index.html`'s sidebar (and the other pages' navs for consistency), add a "My Estimates" link pointing to `/estimates`, mirroring the Dashboard/Active Jobs/Parts Catalog links.

- [ ] **Step 5: Reopen flow in workspace.js**

On load, if `?estimate=<id>` is present, fetch and adopt it (frozen snapshot + its thread). Add near the bottom (the "First paint" section, line ~445):

```javascript
const reopenId = new URLSearchParams(location.search).get("estimate");
if (reopenId) {
  loadEstimate(reopenId).then((rec) => {
    if (!rec) return;
    savedId = rec.id;
    refinementThread = rec.thread || [];
    setEstimate(rec.estimate, true);
    // Replay the saved thread as chat bubbles (read-only history on reopen).
    (rec.thread || []).forEach((t) => {
      appendMsg("user", t.message);
    });
  });
}
```

- [ ] **Step 6: Verify**

Run: `pytest tests/test_api_pages.py -v && node --check quillwright/web/js/workspace.js`
Expected: PASS + clean parse

Run: `npx prettier --write --ignore-unknown "quillwright/web/**/*"`

- [ ] **Step 7: Commit**

```bash
git add quillwright/web/estimates.html quillwright/server.py quillwright/web/index.html quillwright/web/css/workspace.css tests/test_api_pages.py
git commit -m "feat(ui): My Estimates page + reopen-by-id flow (frozen snapshot + thread replay)"
```

---

## Task 8: Full verification pass

- [ ] **Step 1: Full test suite**

Run: `pytest -q`
Expected: PASS (was 143; now ~143 + the new store/thread/api/estimates tests)

- [ ] **Step 2: Lint + format + dep-sync**

Run:

```bash
ruff check . && ruff format --check .
npx prettier --check --ignore-unknown "quillwright/web/**/*"
python scripts/check_deps_sync.py
node --check quillwright/web/js/client.js && node --check quillwright/web/js/workspace.js
```

Expected: all clean (no new deps were added, so dep-sync stays green)

- [ ] **Step 3: Manual smoke (the acceptance bar — local, per ADR-0013)**

Run: `python -m quillwright.server` then in the browser:

1. Forge an estimate → it appears in "My Estimates".
2. Forge a second → both listed, newest first.
3. Refine via chat ("add a contactor", then "make labor 2 hours") → thread accumulates.
4. Reload → reopen the saved estimate from "My Estimates" → rows are the frozen snapshot, thread bubbles replay.
5. Continue the chat ("add another contactor") → references resolve, new line priced from current catalog; existing lines unchanged.
6. Discard → the saved row is gone from the list.

Expected: all six behave as described. Capture a screenshot of "My Estimates" for the demo/video.

- [ ] **Step 4: Final commit (if any format/touch-ups)**

```bash
git add -A
git commit -m "chore: saved-estimates verification pass — tests/lint/format green"
```

---

## Self-Review Notes

- **Spec coverage:** Account/single-tenant (Task 2 `account_id`), separate store (Task 2), JSON-on-disk swappable interface (Task 2), auto-save + explicit Save + update-in-place + Discard (Tasks 4/5/6), sanitized resumable thread (Tasks 1/3), deterministic compaction (Task 1), frozen snapshot + live-catalog-for-new-lines (Task 7 reopen uses stored rates; `_op_add` already pulls current catalog), My Estimates list + reopen (Task 7). All map to ADR-0013.
- **Facts-from-Tools guard:** Task 1 + Task 3 assert no `$` in ops/history; numbers always via `recalc_estimate`/catalog. A dedicated "vague ask → asks, never invents a number" test belongs with the _chat rate-edit_ feature (separate, smaller task tracked outside this plan) — noted so it isn't lost.
- **Space safety:** `FF_ESTIMATE_STORE` is env-driven; the Space sets it to a per-session temp dir (Dockerfile/launch change — call out at deploy, not in app code).
- **Not in this plan (deliberate):** real auth, durable cloud store, SQLite, "finalized/locked" status, cross-session live thread beyond compaction — all post-hackathon (ADR-0013).
