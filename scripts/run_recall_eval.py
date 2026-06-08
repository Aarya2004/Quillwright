"""Measure Recall@1: keyword baseline vs semantic re-rank (ADR-0003).

Keyword baseline runs with no models:
    PYTHONPATH=. .venv/bin/python scripts/run_recall_eval.py

Semantic re-rank (once the embedder is wired) needs FF_REAL_MODELS=1 + the
embedding role resolvable. If it isn't available, the script reports the keyword
baseline alone and says so — it never fabricates a semantic number.
"""

import os
import sys

from quillwright.recall_eval import (
    keyword_overlap,
    keyword_ranker,
    load_recall_cases,
    recall_at_1,
)


def _semantic_ranker():
    """Return an embedding-cosine ranker, or None if the embedder isn't available.

    Wiring point for ADR-0003: resolve the 'embedding' role, encode each run's
    haystack once + the query, rank by cosine. Returns None today so the baseline
    still reports cleanly.
    """
    if os.environ.get("FF_REAL_MODELS") != "1":
        return None
    try:
        from quillwright.resolver import ModelResolver  # noqa: F401

        # TODO(phase: semantic Recall): resolve embedding role + cosine rank here.
        # embedder = ModelResolver(mode="private", backend="ollama").for_role("embedding")
        return None
    except Exception:
        return None


def main() -> int:
    data = load_recall_cases("data/recall_evalset.json")
    corpus, queries = data["corpus"], data["queries"]
    print(f"Recall eval: {len(corpus)} seeded runs, {len(queries)} queries\n")

    def keyword_with_empty_on_no_overlap(query, runs):
        ranked = keyword_ranker(query, runs)
        if ranked and keyword_overlap(query, ranked[0]) == 0:
            return []
        return ranked

    kw = recall_at_1(queries, corpus, keyword_with_empty_on_no_overlap)
    print("per-query (keyword baseline):")
    for q in queries:
        ranked = keyword_with_empty_on_no_overlap(q["query"], corpus)
        hit = bool(ranked) and ranked[0]["id"] == q["gold_id"]
        print(f"  {'HIT ' if hit else 'miss'}  {q['query']!r} -> gold #{q['gold_id']}")
    print(f"\nKeyword recall@1:   {kw:.3f}")

    semantic = _semantic_ranker()
    if semantic is None:
        print("Semantic recall@1:  (embedder not wired yet — baseline only)")
    else:
        sem = recall_at_1(queries, corpus, semantic)
        print(f"Semantic recall@1:  {sem:.3f}")
        print(f"Delta (semantic - keyword): {sem - kw:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
