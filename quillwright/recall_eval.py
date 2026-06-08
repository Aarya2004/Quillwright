"""Score Recall: given a query, does the ranker put the right past run first?

The viability question for semantic Recall (ADR-0003) is "does meaning-based
re-ranking beat keyword matching on queries where the words differ but the intent
matches" (e.g. query "coolant" should find a run that says "refrigerant"). This
module measures recall@1 for any ranker, plus a keyword baseline, so we can report
a measured keyword-vs-semantic delta for the Field Notes write-up.

A `ranker` is `fn(query, runs) -> runs_ranked_best_first`. The keyword baseline
ranks by literal token overlap; the semantic ranker (embedding cosine) drops in
with the same signature once the embedder lands — no change here.
"""

import json


def load_recall_cases(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _haystack(run: dict) -> str:
    return (run["transcript"] + " " + " ".join(run["line_items"])).lower()


def keyword_overlap(query: str, run: dict) -> int:
    """How many query tokens appear literally in the run (the keyword signal)."""
    hay = _haystack(run)
    return sum(1 for tok in query.lower().split() if tok in hay)


def keyword_ranker(query: str, runs: list[dict]) -> list[dict]:
    """Baseline: rank by literal token overlap, ties keep corpus order (stable)."""
    return sorted(runs, key=lambda r: keyword_overlap(query, r), reverse=True)


def recall_at_1(queries: list[dict], corpus: list[dict], ranker) -> float:
    """Fraction of queries whose gold run is ranked first by `ranker`.

    Each query is {"query": str, "gold_id": int}; runs are matched by "id".
    """
    if not queries:
        return 0.0
    hits = 0
    for q in queries:
        ranked = ranker(q["query"], corpus)
        if ranked and ranked[0]["id"] == q["gold_id"]:
            hits += 1
    return round(hits / len(queries), 3)


def keyword_recall_at_1(queries: list[dict], corpus: list[dict]) -> float:
    """recall@1 using the keyword baseline ranker.

    Note: a query with zero literal overlap leaves the corpus in its original
    order, so the first run is a non-match — that miss is the point (it's where
    semantic recall should win).
    """

    def ranker(query, runs):
        ranked = keyword_ranker(query, runs)
        # if nothing overlaps at all, treat it as no result (a guaranteed miss),
        # rather than crediting whatever happened to sort first.
        if ranked and keyword_overlap(query, ranked[0]) == 0:
            return []
        return ranked

    return recall_at_1(queries, corpus, ranker)
