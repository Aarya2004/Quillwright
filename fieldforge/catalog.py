import json
import re

# Generic words that shouldn't drive a match on their own.
_STOPWORDS = {
    "the", "a", "an", "and", "of", "to", "up", "top", "new", "some", "duty",
    "dual", "run", "compressor", "service", "replacement", "part", "ea", "lb",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in _STOPWORDS}


class Catalog:
    def __init__(self, items: list[dict]):
        self._by_key = {i["key"].lower(): i for i in items}
        # Significant tokens per item, drawn from key + description.
        self._tokens = {
            i["key"].lower(): _tokens(i["key"].replace("_", " ") + " " + i["description"])
            for i in items
        }

    @classmethod
    def from_file(cls, path: str) -> "Catalog":
        with open(path) as f:
            data = json.load(f)
        return cls(data["items"])

    def lookup(self, key: str) -> dict | None:
        norm = key.strip().lower()
        if norm in self._by_key:  # exact key still wins
            return self._by_key[norm]
        query = _tokens(norm)
        if not query:
            return None
        # Match the catalog item sharing the most significant tokens with the query.
        best_key, best_overlap = None, 0
        for k, toks in self._tokens.items():
            overlap = len(query & toks)
            if overlap > best_overlap:
                best_key, best_overlap = k, overlap
        return self._by_key[best_key] if best_overlap >= 1 else None

    def add(self, key: str, description: str, unit: str, rate: float) -> None:
        self._by_key[key.strip().lower()] = {
            "key": key,
            "description": description,
            "unit": unit,
            "rate": rate,
        }
        self._tokens[key.strip().lower()] = _tokens(key.replace("_", " ") + " " + description)
