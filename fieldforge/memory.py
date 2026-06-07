"""On-device memory: persistent Profile + Episodic past-jobs, with keyword Recall.

Stored as a local JSON file — private, no cloud. The agent records each finished
run and can recall similar past jobs to inform a new estimate.
"""

import json
import os
from collections import Counter


class Memory:
    def __init__(self, path: str):
        self._path = path
        self._runs: list[dict] = []
        self._load()

    def _load(self) -> None:
        if os.path.isfile(self._path):
            with open(self._path) as f:
                self._runs = json.load(f).get("runs", [])

    def record_run(self, transcript: str, line_items: list[str]) -> None:
        self._runs.append({"transcript": transcript, "line_items": list(line_items)})
        self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({"runs": self._runs}, f, indent=2)

    def recall(self, query: str) -> list[dict]:
        q = query.strip().lower()
        scored = [(self._haystack(r).count(q), r) for r in self._runs]
        matches = [(score, r) for score, r in scored if score > 0]
        matches.sort(key=lambda sr: sr[0], reverse=True)
        return [r for _score, r in matches]

    @staticmethod
    def _haystack(run: dict) -> str:
        return (run["transcript"] + " " + " ".join(run["line_items"])).lower()

    def profile(self) -> dict:
        """Learned per-tech defaults derived from recorded runs."""
        counts = Counter(item for r in self._runs for item in r["line_items"])
        common = [item for item, _ in counts.most_common()]
        return {"common_items": common, "job_count": len(self._runs)}
