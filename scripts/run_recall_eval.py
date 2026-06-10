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
    embed_corpus,
    keyword_overlap,
    keyword_ranker,
    load_recall_cases,
    recall_at_1,
    semantic_ranker,
)


def _semantic_ranker(corpus):
    """Return (ranker, embedded_corpus), or (None, corpus) if the embedder is absent.

    Resolves the 'embedding' role (sentence-transformers, ADR-0003), caches a vector
    per corpus run, and ranks by cosine. Requires FF_REAL_MODELS=1 so the heavy
    torch/sentence-transformers import only happens when explicitly enabled.
    """
    if os.environ.get("FF_REAL_MODELS") != "1":
        return None, corpus
    try:
        from quillwright.resolver import ModelResolver

        embedder = ModelResolver(mode="private", backend="ollama").for_role("embedding")
        embedded = embed_corpus(corpus, embedder)
        return (lambda q, runs: semantic_ranker(q, runs, embedder)), embedded
    except Exception as exc:  # noqa: BLE001 — report honestly, don't fabricate a number
        print(f"  (semantic ranker unavailable: {exc})")
        return None, corpus


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

    semantic, embedded_corpus = _semantic_ranker(corpus)
    if semantic is None:
        print("Semantic recall@1:  (run with FF_REAL_MODELS=1 to measure)")
    else:
        print("\nper-query (semantic re-rank):")
        for q in queries:
            ranked = semantic(q["query"], embedded_corpus)
            hit = bool(ranked) and ranked[0]["id"] == q["gold_id"]
            print(f"  {'HIT ' if hit else 'miss'}  {q['query']!r} -> gold #{q['gold_id']}")
        sem = recall_at_1(queries, embedded_corpus, semantic)
        print(f"\nSemantic recall@1:  {sem:.3f}")
        print(f"Delta (semantic - keyword): {sem - kw:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
