"""EmbeddingModel: local text embeddings for semantic Recall (ADR-0003).

Wraps `nvidia/llama-nemotron-embed-1b-v2` via sentence-transformers — the model
card's recommended local path (NOT Ollama; it has no embeddings API). Runs fully
offline → preserves 🔌 Off the Grid and adds NVIDIA breadth.

sentence-transformers + torch are heavy (~2GB), so the import is LAZY: importing
this module costs nothing; the model loads on first `.encode()`. Per ADR-0003 the
hot path only embeds the QUERY (run vectors are cached at record time), so torch
stays out of recall-time latency.
"""

DEFAULT_MODEL = "nvidia/llama-nemotron-embed-1b-v2"


class EmbeddingModel:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.name = model
        self._st = None  # lazily-loaded SentenceTransformer

    def _model(self):
        if self._st is None:
            from sentence_transformers import SentenceTransformer

            self._st = SentenceTransformer(self.name, trust_remote_code=True)
        return self._st

    def encode(self, text: str) -> list[float]:
        vec = self._model().encode(text, normalize_embeddings=True)
        return vec.tolist()
