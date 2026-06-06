from typing import Protocol


class Model(Protocol):
    name: str
    def generate(self, prompt: str) -> str: ...


class StubModel:
    """Deterministic model for tests/dev. Pops scripted responses in order."""
    def __init__(self, responses: list[str], name: str = "StubModel"):
        self._responses = list(responses)
        self.name = name

    def generate(self, prompt: str) -> str:
        if not self._responses:
            return ""
        return self._responses.pop(0)


# Which concrete model fills each role per Mode. Real backends wired later (ADR-0005).
PRIVATE_STACK = {
    "perception": "MiniCPM-V-4.6",
    "audio": "whisper-local",
    "brain": "gpt-oss-20b",
}
BEST_STACK = {
    "perception": "Nemotron-3-Nano-Omni",
    "audio": "Nemotron-3-Nano-Omni",
    "brain": "gpt-oss-20b",
}


class ModelResolver:
    def __init__(self, mode: str = "private", overrides: dict[str, Model] | None = None):
        self.mode = mode
        self._overrides = overrides or {}
        self._roles = PRIVATE_STACK if mode == "private" else BEST_STACK

    def for_role(self, role: str) -> Model:
        if role in self._overrides:
            return self._overrides[role]
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        # No real backend yet in the core plan: a named stub stands in.
        return StubModel(responses=[""], name=self._roles[role])
