from fastapi.testclient import TestClient

from quillwright.server import app

client = TestClient(app)


def test_model_info_endpoint_reports_mode_and_roles(monkeypatch):
    # Default test env (no FF_REAL_MODELS / FF_BACKEND) → stub mode.
    for var in ("FF_REAL_MODELS", "FF_BACKEND", "FF_MODAL_BRAIN_URL"):
        monkeypatch.delenv(var, raising=False)
    out = client.get("/api/model_info").json()
    assert out["mode"] == "stub"
    assert "brain" in out["roles"]
    assert out["roles"]["brain"] == "stub"
