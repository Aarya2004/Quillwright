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

# Roles served on Modal (ADR-0005 hosted compute, ADR-0009 Best Stack). Labels are
# informational; each role's modal app pins the real repo id (see backends/modal.py
# ROLE_ENDPOINTS). Perception + audio share the ONE Omni deployment (omnimodal).
MODAL_ROLES = {
    "brain": "nemotron-3-nano-30b-a3b",
    "perception": "nemotron-3-nano-omni-30b-a3b",
    "audio": "nemotron-3-nano-omni-30b-a3b",
    "multilingual": "aya-expanse-8b",
}


def brain_resolver() -> "ModelResolver":
    """The resolver for the agent brain, chosen by env (one source of truth).

    FF_BACKEND=modal  -> Best-Stack brain (Nemotron 30B) hosted on Modal (ADR-0009).
    otherwise         -> Private-Stack brain (Nemotron 4B) via local Ollama.

    The brain is special: FF_BACKEND=modal *means* "brain on Modal", so a missing
    FF_MODAL_BRAIN_URL fails LOUD in ModalModel rather than silently downgrading.
    Other roles opt in per-URL via modal_resolver_if_configured().
    """
    import os

    if os.environ.get("FF_BACKEND") == "modal":
        return ModelResolver(mode="best", backend="modal")
    return ModelResolver(mode="private", backend="ollama")


def modal_resolver_if_configured(role: str) -> "ModelResolver | None":
    """A Best-Stack Modal resolver for `role`, or None when the local path should run.

    Per-role opt-in (mirrors FF_MODAL_PARSE_URL): FF_BACKEND=modal moves ONLY the
    brain; perception/audio/multilingual each ride Modal IFF their own URL env is
    also set. Callers fall back to their existing local/stub path on None — turning
    on the hosted brain never breaks a role whose GPU app isn't deployed.
    """
    import os

    if os.environ.get("FF_BACKEND") != "modal":
        return None
    from quillwright.backends.modal import ROLE_ENDPOINTS

    if role not in ROLE_ENDPOINTS or not os.environ.get(ROLE_ENDPOINTS[role][0]):
        return None
    return ModelResolver(mode="best", backend="modal")


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
        # Embedding has ONE serving path (sentence-transformers, ADR-0003) regardless
        # of mode/backend — it is not an Ollama/Modal model. Resolve it directly.
        if role == "embedding" and self._backend != "stub":
            from quillwright.backends.embedding import EmbeddingModel

            return EmbeddingModel()
        # Audio: on-device Cohere Transcribe via transformers (ADR-0009) — not Ollama —
        # EXCEPT under the modal backend, where it rides the hosted Omni deployment
        # like any other MODAL_ROLES entry (falls through to the modal branch below).
        if role == "audio" and self._backend not in ("stub", "modal"):
            from quillwright.backends.audio import AudioModel

            return AudioModel()
        # Extraction (Nemotron Parse) has ONE serving path too, but a REMOTE one:
        # it is visual, so it never fits Ollama/vLLM and is always hosted on Modal
        # (ADR-0011). The Modal endpoint URL comes from FF_MODAL_PARSE_URL.
        if role == "extraction" and self._backend != "stub":
            from quillwright.backends.parse import ParseModel

            return ParseModel()
        if self._backend == "ollama":
            if role not in OLLAMA_TAGS:
                raise KeyError(f"no ollama tag for role: {role}")
            from quillwright.backends.ollama import OllamaModel

            return OllamaModel(OLLAMA_TAGS[role])
        if self._backend == "modal":
            if role not in MODAL_ROLES:
                raise KeyError(f"role '{role}' is not served on Modal")
            from quillwright.backends.modal import ModalModel

            return ModalModel(MODAL_ROLES[role], role=role)
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        return StubModel(responses=[""], name=self._roles[role])
