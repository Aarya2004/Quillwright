import pytest
from fastapi.testclient import TestClient

import quillwright.api.estimate as est_api
from quillwright.server import app

client = TestClient(app)

EST_ROWS = [{"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0}]


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FF_ESTIMATE_STORE", str(tmp_path))
    est_api.reset_estimate_store()
    yield
    est_api.reset_estimate_store()


def test_save_then_list_then_load():
    r = client.post(
        "/api/save_estimate",
        json={"rows": EST_ROWS, "job_title": "Test Job", "tax_rate": 0.13, "thread": []},
    )
    assert r.status_code == 200
    id = r.json()["id"]

    listed = client.get("/api/estimates").json()
    assert listed["estimates"][0]["job_title"] == "Test Job"
    assert listed["estimates"][0]["id"] == id

    loaded = client.get(f"/api/estimate/{id}").json()
    assert loaded["estimate"]["line_items"][0]["description"] == "Labor"
    assert loaded["estimate"]["total"] == pytest.approx(101.7)  # 90 * 1.13


def test_save_update_in_place():
    id = client.post(
        "/api/save_estimate", json={"rows": EST_ROWS, "job_title": "J", "thread": []}
    ).json()["id"]
    client.post(
        "/api/save_estimate",
        json={
            "rows": EST_ROWS
            + [{"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0}],
            "job_title": "J",
            "thread": [],
            "id": id,
        },
    )
    assert len(client.get("/api/estimates").json()["estimates"]) == 1


def test_delete():
    id = client.post(
        "/api/save_estimate", json={"rows": EST_ROWS, "job_title": "J", "thread": []}
    ).json()["id"]
    assert client.delete(f"/api/estimate/{id}").status_code == 200
    assert client.get("/api/estimates").json()["estimates"] == []


def test_load_missing_returns_404():
    assert client.get("/api/estimate/9999").status_code == 404


def test_chat_endpoint_passes_and_returns_thread():
    out = client.post(
        "/api/chat",
        json={"message": "add a contactor", "rows": EST_ROWS, "tax_rate": 0.13, "thread": []},
    ).json()
    assert "thread" in out and len(out["thread"]) == 1


from quillwright.api.estimate import forge_estimate  # noqa: E402


def test_forge_autosaves_to_store(fresh_store):
    result = forge_estimate("replaced the capacitor and contactor, one hour labor", "hvac")
    assert result["estimate"]["line_items"]
    listed = client.get("/api/estimates").json()["estimates"]
    assert len(listed) == 1  # the finished forge auto-saved
