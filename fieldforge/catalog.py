import json


class Catalog:
    def __init__(self, items: list[dict]):
        self._by_key = {i["key"].lower(): i for i in items}

    @classmethod
    def from_file(cls, path: str) -> "Catalog":
        with open(path) as f:
            data = json.load(f)
        return cls(data["items"])

    def lookup(self, key: str) -> dict | None:
        return self._by_key.get(key.strip().lower())

    def add(self, key: str, description: str, unit: str, rate: float) -> None:
        self._by_key[key.strip().lower()] = {
            "key": key,
            "description": description,
            "unit": unit,
            "rate": rate,
        }
