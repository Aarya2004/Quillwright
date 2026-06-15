from quillwright.api.estimate import forge_estimate


def test_forge_estimate_returns_trace_and_estimate_json():
    out = forge_estimate("replaced capacitor, 1h labor", "hvac")
    assert "trace" in out and "estimate" in out
    est = out["estimate"]
    assert est is not None
    # estimate is plain JSON-serializable dicts, not pydantic objects
    assert isinstance(est["total"], float)
    descs = [li["description"].lower() for li in est["line_items"]]
    assert any("capacitor" in d for d in descs)
    # trace is a list of step dicts with the expected keys
    assert out["trace"] and set(out["trace"][0]) == {"action", "model", "detail", "status"}


def test_perception_prefers_modal_omni_when_configured(monkeypatch):
    # Best-Stack Perception: FF_BACKEND=modal + the Omni URL sends a real photo to
    # the hosted Omni; without the URL the local/stub path keeps working.
    from quillwright.api.estimate import _perception
    from quillwright.backends.modal import ModalModel

    monkeypatch.setenv("FF_BACKEND", "modal")
    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    model = _perception("note", has_real_image=True)
    assert isinstance(model, ModalModel)


def test_perception_without_omni_url_falls_back_to_stub(monkeypatch):
    # FF_BACKEND=modal moves ONLY the brain (README contract): a photo with no Omni
    # URL must not surprise-require Ollama when real models are off.
    from quillwright.api.estimate import _perception
    from quillwright.resolver import StubModel

    monkeypatch.setenv("FF_BACKEND", "modal")
    monkeypatch.delenv("FF_MODAL_OMNI_URL", raising=False)
    model = _perception("note", has_real_image=True)
    assert isinstance(model, StubModel)
