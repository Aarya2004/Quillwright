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
    def __init__(self, path: str | None = None, account_id: str | None = None):
        # Read the env at construction time (not import time) so a test/launch that
        # sets FF_ESTIMATE_STORE / FF_ACCOUNT_ID before building the store wins.
        path = path or os.environ.get("FF_ESTIMATE_STORE", "/tmp/quillwright_estimates")
        account_id = account_id or os.environ.get("FF_ACCOUNT_ID", "demo")
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
            recs.append(
                {
                    "id": rec["id"],
                    "job_title": est.get("job_title", "Estimate"),
                    "total": est.get("total"),
                    "saved_seq": rec.get("saved_seq", 0),
                }
            )
        recs.sort(key=lambda r: r["saved_seq"], reverse=True)
        return recs

    def delete(self, id: str) -> None:
        path = self._path(id)
        if os.path.isfile(path):
            os.remove(path)
