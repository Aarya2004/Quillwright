from quillwright.resolver import ModelResolver, StubModel


def test_stub_model_returns_scripted_response():
    stub = StubModel(responses=["hello"])
    assert stub.generate("anything") == "hello"


def test_stub_model_chat_returns_scripted_messages():
    stub = StubModel(
        responses=[],
        chats=[
            {"tool_calls": [{"function": {"name": "add_priced_item", "arguments": {"item": "x"}}}]},
            {"tool_calls": [{"function": {"name": "finish", "arguments": {}}}]},
        ],
    )
    first = stub.chat([], tools=[])
    second = stub.chat([], tools=[])
    assert first["tool_calls"][0]["function"]["name"] == "add_priced_item"
    assert second["tool_calls"][0]["function"]["name"] == "finish"


def test_resolver_returns_model_for_role():
    resolver = ModelResolver(mode="private", overrides={"perception": StubModel(responses=["ok"])})
    model = resolver.for_role("perception")
    assert model.generate("x") == "ok"


def test_resolver_unknown_role_raises():
    resolver = ModelResolver(mode="private")
    try:
        resolver.for_role("nope")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_ollama_backend_returns_real_model_with_local_tag():
    from quillwright.backends.ollama import OllamaModel

    resolver = ModelResolver(mode="private", backend="ollama")
    brain = resolver.for_role("brain")
    vision = resolver.for_role("perception")
    assert isinstance(brain, OllamaModel) and isinstance(vision, OllamaModel)
    # maps to the actual local Ollama tags
    assert brain.name == "nemotron-3-nano:4b"
    assert vision.name == "minicpm-v"


def test_modal_backend_returns_modal_brain(monkeypatch):
    from quillwright.backends.modal import ModalModel

    monkeypatch.setenv("FF_MODAL_BRAIN_URL", "https://example--quillwright-brain-serve")
    resolver = ModelResolver(mode="best", backend="modal")
    brain = resolver.for_role("brain")
    assert isinstance(brain, ModalModel)
    assert brain.name == "nemotron-3-nano-30b-a3b"


def test_modal_backend_rejects_roles_not_hosted():
    # A role with no Modal serving path must fail LOUD, not silently stub.
    resolver = ModelResolver(mode="best", backend="modal")
    try:
        resolver.for_role("visual")
        assert False, "expected KeyError for visual"
    except KeyError:
        pass


def test_modal_backend_hosts_omni_for_perception_and_audio(monkeypatch):
    # Best-Stack Perception AND Audio both ride the ONE Omni deployment (ADR-0009:
    # Omni is omnimodal — image + audio — so one app serves two Model Roles).
    from quillwright.backends.modal import ModalModel

    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--quillwright-omni-serve")
    resolver = ModelResolver(mode="best", backend="modal")
    perception = resolver.for_role("perception")
    audio = resolver.for_role("audio")
    assert isinstance(perception, ModalModel) and isinstance(audio, ModalModel)
    assert "omni" in perception.name
    assert "omni" in audio.name


def test_modal_backend_hosts_aya_for_multilingual(monkeypatch):
    from quillwright.backends.modal import ModalModel

    monkeypatch.setenv("FF_MODAL_AYA_URL", "https://example--quillwright-aya-serve")
    resolver = ModelResolver(mode="best", backend="modal")
    multilingual = resolver.for_role("multilingual")
    assert isinstance(multilingual, ModalModel)
    assert "aya" in multilingual.name


def test_modal_resolver_if_configured_gates_on_backend_and_url(monkeypatch):
    # Per-role opt-in (mirrors FF_MODAL_PARSE_URL): FF_BACKEND=modal moves ONLY the
    # brain; each other role rides Modal IFF its own URL is also set. Without that,
    # the local path keeps working — never a surprise dependency on a GPU endpoint.
    from quillwright.resolver import modal_resolver_if_configured

    monkeypatch.delenv("FF_BACKEND", raising=False)
    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    assert modal_resolver_if_configured("perception") is None  # backend not modal

    monkeypatch.setenv("FF_BACKEND", "modal")
    monkeypatch.delenv("FF_MODAL_OMNI_URL", raising=False)
    assert modal_resolver_if_configured("perception") is None  # role URL not set

    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    resolver = modal_resolver_if_configured("perception")
    assert resolver is not None
    from quillwright.backends.modal import ModalModel

    assert isinstance(resolver.for_role("perception"), ModalModel)

    # A role with no Modal endpoint mapping never upgrades.
    assert modal_resolver_if_configured("embedding") is None


def test_modal_model_requires_url():
    from quillwright.backends.modal import ModalModel

    try:
        ModalModel("brain", base_url="")
        assert False, "expected RuntimeError when no URL configured"
    except RuntimeError:
        pass


def test_extraction_role_resolves_to_parse_model(monkeypatch):
    # Parse (Document Capture, ADR-0011) is a single REMOTE serving path — it
    # resolves to ParseModel for any non-stub backend, independent of brain hosting.
    from quillwright.backends.parse import ParseModel

    monkeypatch.setenv("FF_MODAL_PARSE_URL", "https://example--quillwright-parse-parser-parse")
    resolver = ModelResolver(mode="best", backend="modal")
    extractor = resolver.for_role("extraction")
    assert isinstance(extractor, ParseModel)


def test_extraction_role_under_stub_backend_is_not_parse_model():
    # With the stub backend (tests/CI default), extraction must NOT try to reach
    # Modal — it falls through to the stub path and raises like any unknown role.
    resolver = ModelResolver(mode="private")  # backend defaults to "stub"
    try:
        resolver.for_role("extraction")
        assert False, "expected KeyError for extraction under stub backend"
    except KeyError:
        pass


def test_parse_model_requires_url(monkeypatch):
    from quillwright.backends.parse import ParseModel

    monkeypatch.delenv("FF_MODAL_PARSE_URL", raising=False)
    try:
        ParseModel(base_url="")
        assert False, "expected RuntimeError when no Parse URL configured"
    except RuntimeError:
        pass
