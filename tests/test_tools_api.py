"""Quillwright tool endpoints for the ElevenLabs voice agent.

The agent owns the call + dialogue + TTS; these tools forge/refine the estimate and
return structured data. Facts-from-Tools holds — every number is a tool response, never
the agent's speech. Tested without network: the SMS provider is injectable.
"""

import pytest
from fastapi.testclient import TestClient

import quillwright.api.estimate as est_api
from quillwright.api import tools_api
from quillwright.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("FF_ESTIMATE_STORE", str(tmp_path))
    est_api.reset_estimate_store()
    tools_api.reset_sessions()
    yield
    est_api.reset_estimate_store()
    tools_api.reset_sessions()


def test_forge_returns_items_and_total():
    out = tools_api.forge("S1", "replaced the capacitor and contactor, one hour labor")
    assert out["ok"] is True
    assert out["item_count"] >= 2
    assert out["total"] > 0
    descs = [i["description"] for i in out["items"]]
    assert any("capacitor" in d.lower() for d in descs)


def test_edit_adds_a_catalog_priced_line_and_updates_total():
    tools_api.forge("S2", "replaced the capacitor, one hour labor")
    out = tools_api.edit("S2", "add a refrigerant")
    assert out["ok"] is True
    descs = [i["description"] for i in out["items"]]
    assert any("refrigerant" in d.lower() for d in descs)  # catalog-priced add
    assert out["total"] > 0


def test_edit_shares_session_state_with_forge():
    tools_api.forge("S3", "one hour labor")
    n0 = tools_api.forge("S3", "one hour labor")["item_count"]
    out = tools_api.edit("S3", "add a contactor")
    assert out["item_count"] == n0 + 1  # the edit built on the forged rows


def test_lookup_price_hits_and_misses():
    hit = tools_api.lookup_price("capacitor")
    assert hit["found"] is True and hit["rate"] > 0
    # A part genuinely not in the sample catalog (fuzzy lookup won't match it).
    miss = tools_api.lookup_price("smoke detector")
    assert miss["found"] is False


def test_text_estimate_sends_via_injected_provider():
    tools_api.forge("S4", "replaced the capacitor and contactor, one hour labor")
    sent = {}
    out = tools_api.text_estimate(
        "S4",
        to="+15551234567",
        base_url="https://demo.example.com",
        sms=lambda **kw: sent.update(kw) or {"sid": "SM"},
    )
    assert out["ok"] is True and out["sent"] is True
    assert sent["recipient"] == "+15551234567"
    assert sent["media_url"].startswith("https://demo.example.com/api/estimate_pdf/")


def test_text_estimate_without_estimate_is_refused():
    out = tools_api.text_estimate("S_empty", to="+15551234567", sms=lambda **kw: None)
    assert out["ok"] is False


def test_tool_endpoints_are_wired():
    r = client.post("/api/tools/forge", json={"session_id": "H1", "description": "one hour labor"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r2 = client.post("/api/tools/lookup_price", json={"item": "capacitor"})
    assert r2.status_code == 200 and r2.json()["found"] is True
    r3 = client.post("/api/tools/edit", json={"session_id": "H1", "request": "add a contactor"})
    assert r3.status_code == 200 and r3.json()["total"] > 0


def test_tool_endpoint_accepts_body_without_json_content_type():
    # ElevenLabs / webhook callers don't always send Content-Type: application/json.
    # The tool must still parse the JSON body (not 422).
    import json as _json

    r = client.post(
        "/api/tools/forge",
        content=_json.dumps({"session_id": "H2", "description": "one hour labor"}),
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 200 and r.json()["ok"] is True
