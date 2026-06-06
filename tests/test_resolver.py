from fieldforge.resolver import ModelResolver, StubModel


def test_stub_model_returns_scripted_response():
    stub = StubModel(responses=["hello"])
    assert stub.generate("anything") == "hello"


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
