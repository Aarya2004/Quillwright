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
