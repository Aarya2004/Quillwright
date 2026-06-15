import pytest

from quillwright.estimate_store import EstimateStore

EST = {
    "job_title": "AC Unit Repair — 123 Maple St",
    "line_items": [
        {
            "description": "Dual run capacitor",
            "quantity": 1,
            "unit": "ea",
            "rate": 24.0,
            "subtotal": 24.0,
            "price_source": "catalog",
        },
    ],
    "subtotal": 24.0,
    "tax_rate": 0.13,
    "tax": 3.12,
    "total": 27.12,
}


@pytest.fixture
def store(tmp_path):
    return EstimateStore(path=str(tmp_path), account_id="demo")


def test_save_returns_id_and_load_round_trips(store):
    rec = store.save(estimate=EST, thread=[])
    assert rec["id"]
    loaded = store.load(rec["id"])
    assert loaded["estimate"]["total"] == 27.12
    assert loaded["estimate"]["job_title"] == EST["job_title"]
    assert loaded["thread"] == []


def test_save_update_in_place_same_id(store):
    rec = store.save(estimate=EST, thread=[])
    updated = {**EST, "total": 99.99}
    rec2 = store.save(estimate=updated, thread=[{"message": "m", "op": "o"}], id=rec["id"])
    assert rec2["id"] == rec["id"]
    assert store.load(rec["id"])["estimate"]["total"] == 99.99
    assert store.load(rec["id"])["thread"] == [{"message": "m", "op": "o"}]
    # still exactly one estimate
    assert len(store.list_estimates()) == 1


def test_list_estimates_newest_first_with_summary(store):
    store.save(estimate={**EST, "job_title": "Job A"}, thread=[])
    store.save(estimate={**EST, "job_title": "Job B", "total": 50.0}, thread=[])
    listed = store.list_estimates()
    assert [e["job_title"] for e in listed] == ["Job B", "Job A"]  # newest first
    assert listed[0]["total"] == 50.0
    assert listed[0]["id"]  # id present for the reopen link


def test_delete_removes(store):
    rec = store.save(estimate=EST, thread=[])
    store.delete(rec["id"])
    assert store.list_estimates() == []
    assert store.load(rec["id"]) is None


def test_accounts_are_isolated(tmp_path):
    a = EstimateStore(path=str(tmp_path), account_id="demo")
    b = EstimateStore(path=str(tmp_path), account_id="other")
    a.save(estimate=EST, thread=[])
    assert len(a.list_estimates()) == 1
    assert b.list_estimates() == []  # other account sees nothing
