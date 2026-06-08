from typing import Protocol


class Model(Protocol):
    name: str

    def generate(self, prompt: str) -> str: ...


class StubModel:
    """Deterministic model for tests/dev. Pops scripted responses/chats in order."""

    def __init__(
        self,
        responses: list[str],
        name: str = "StubModel",
        chats: list[dict] | None = None,
    ):
        self._responses = list(responses)
        self._chats = list(chats or [])
        self.name = name

    def generate(self, prompt: str, image_path: str | None = None) -> str:
        if not self._responses:
            return ""
        return self._responses.pop(0)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self._chats:
            return {"content": ""}
        return self._chats.pop(0)


# Which concrete model fills each role per Mode. Real backends wired later (ADR-0005).
# Display labels per role (used by the stub backend). These are LABELS ONLY — the
# real on-device models are in OLLAMA_TAGS below (the brain is Nemotron, not gpt-oss;
# ADR-0009 superseded the gpt-oss mapping).
PRIVATE_STACK = {
    "perception": "MiniCPM-V",
    "audio": "Cohere-Transcribe",
    "brain": "Nemotron-3-Nano-4B",
}
BEST_STACK = {
    "perception": "Nemotron-3-Nano-Omni",
    "audio": "Nemotron-3-Nano-Omni",
    "brain": "Nemotron-3-Nano-30B",
}

# Actual locally-available Ollama tags per role (what we really run on-device).
OLLAMA_TAGS = {
    "perception": "minicpm-v",
    "brain": "nemotron-3-nano:4b",
    "multilingual": "aya",
}


class ModelResolver:
    def __init__(
        self,
        mode: str = "private",
        overrides: dict[str, Model] | None = None,
        backend: str = "stub",
    ):
        self.mode = mode
        self._overrides = overrides or {}
        self._roles = PRIVATE_STACK if mode == "private" else BEST_STACK
        self._backend = backend

    def for_role(self, role: str) -> Model:
        if role in self._overrides:
            return self._overrides[role]
        if self._backend == "ollama":
            if role not in OLLAMA_TAGS:
                raise KeyError(f"no ollama tag for role: {role}")
            from quillwright.backends.ollama import OllamaModel

            return OllamaModel(OLLAMA_TAGS[role])
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        return StubModel(responses=[""], name=self._roles[role])
