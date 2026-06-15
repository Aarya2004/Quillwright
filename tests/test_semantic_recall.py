"""Semantic Recall ranking — tested with a FAKE embedder (no torch needed).

The real embedder is nvidia/llama-nemotron-embed-1b-v2 via sentence-transformers
(ADR-0003); here we inject a deterministic fake so the cosine/ranking logic is
verified offline. The contract: semantic_ranker(query, runs, embedder) ranks runs
by cosine similarity between the query embedding and each run's cached embedding.
"""

from quillwright.recall_eval import embed_corpus, recall_at_1, semantic_ranker


class FakeEmbedder:
    """Maps known phrases to fixed vectors so 'coolant' lands near 'refrigerant'."""

    name = "fake-embedder"
    _VECS = {
        "coolant": [1.0, 0.9, 0.0],
        "refrigerant": [1.0, 1.0, 0.0],  # close to coolant (synonym)
        "capacitor": [0.0, 0.0, 1.0],  # far from both
    }

    def encode(self, text: str) -> list[float]:
        t = text.lower()
        for key, vec in self._VECS.items():
            if key in t:
                return vec
        return [0.1, 0.1, 0.1]


def _corpus():
    return [
        {"id": 1, "transcript": "replaced the capacitor", "line_items": ["Dual run capacitor"]},
        {"id": 2, "transcript": "topped up the refrigerant", "line_items": ["R-410A refrigerant"]},
    ]


def test_embed_corpus_caches_a_vector_per_run():
    corpus = embed_corpus(_corpus(), FakeEmbedder())
    assert all("embedding" in r for r in corpus)
    assert len(corpus[0]["embedding"]) == 3


def test_semantic_ranker_puts_synonym_match_first():
    corpus = embed_corpus(_corpus(), FakeEmbedder())
    emb = FakeEmbedder()
    # "coolant" never appears literally in run 2, but its vector is near refrigerant.
    ranked = semantic_ranker("coolant top up", corpus, emb)
    assert ranked[0]["id"] == 2


def test_semantic_recall_at_1_beats_a_keyword_miss():
    corpus = embed_corpus(_corpus(), FakeEmbedder())
    emb = FakeEmbedder()
    queries = [{"query": "coolant top up", "gold_id": 2}]
    score = recall_at_1(queries, corpus, lambda q, runs: semantic_ranker(q, runs, emb))
    assert score == 1.0
