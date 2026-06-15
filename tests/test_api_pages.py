import quillwright.api.pages as pages
from quillwright.memory import Memory


def _seed_memory(tmp_path, monkeypatch):
    """Point the pages module at a fresh memory file with a couple of real runs."""
    path = str(tmp_path / "mem.json")
    mem = Memory(path)
    mem.record_run("replaced the capacitor", ["Dual run capacitor", "Labor"], total=138.0)
    mem.record_run("topped up refrigerant", ["R-410A refrigerant", "Labor"], total=120.0)
    monkeypatch.setattr(pages, "_memory", lambda: Memory(path))
    return path


def test_dashboard_aggregates_real_memory(tmp_path, monkeypatch):
    _seed_memory(tmp_path, monkeypatch)
    data = pages.dashboard_data()
    assert data["job_count"] == 2
    assert data["revenue_total"] == 258.0
    assert "Labor" in data["top_items"]
    # recent jobs are surfaced for the activity list, newest first
    assert data["recent"][0]["transcript"] == "topped up refrigerant"


def test_dashboard_is_honest_when_memory_is_empty(tmp_path, monkeypatch):
    path = str(tmp_path / "empty.json")
    monkeypatch.setattr(pages, "_memory", lambda: Memory(path))
    data = pages.dashboard_data()
    assert data["job_count"] == 0
    assert data["revenue_total"] == 0
    assert data["recent"] == []


def test_jobs_lists_past_runs_newest_first(tmp_path, monkeypatch):
    _seed_memory(tmp_path, monkeypatch)
    data = pages.jobs_data()
    jobs = data["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["transcript"] == "topped up refrigerant"
    assert jobs[0]["total"] == 120.0
    # a short item summary is provided for the table
    assert "R-410A refrigerant" in jobs[0]["items"]


def test_inventory_reads_seeded_json_with_real_low_stock_flags():
    data = pages.inventory_data()
    parts = data["parts"]
    assert len(parts) >= 4
    # every part carries a price from the catalog and a computed low-stock flag
    for p in parts:
        assert "rate" in p and "stock" in p and "low" in p
    # the low-stock count is derived, not hardcoded
    assert data["low_stock_count"] == sum(1 for p in parts if p["low"])


def test_estimates_page_served():
    from fastapi.testclient import TestClient

    from quillwright.server import app

    r = TestClient(app).get("/estimates")
    assert r.status_code == 200
    assert "My Estimates" in r.text
