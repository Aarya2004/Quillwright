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
