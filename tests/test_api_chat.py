from quillwright.api.chat import chat_about_estimate
from quillwright.resolver import StubModel


def _rows():
    return [
        {"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0},
        {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
    ]


def _tc(name, **args):
    """A scripted tool-call chat turn (mirrors brain_loop's StubModel usage)."""
    return {"tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_add_item_appends_a_catalog_priced_row():
    out = chat_about_estimate("add a contactor", _rows(), tax_rate=0.13)
    descs = [r["description"] for r in out["estimate"]["line_items"]]
    assert "Compressor contactor" in descs
    # Facts-from-Tools: the price came from the catalog, not the message.
    contactor = next(
        r for r in out["estimate"]["line_items"] if r["description"] == "Compressor contactor"
    )
    assert contactor["rate"] == 38.0
    assert "contactor" in out["reply"].lower()


def test_add_unknown_item_does_not_invent_a_price():
    # "smoke detector" shares no word with any catalog part -> genuinely unknown.
    out = chat_about_estimate("add a smoke detector", _rows(), tax_rate=0.13)
    # no catalog match -> nothing added, honest reply (never an LLM-guessed price).
    assert len(out["estimate"]["line_items"]) == 2
    assert out["needs_price"] is True or "couldn't find" in out["reply"].lower()


def test_remove_item_drops_the_matching_row():
    out = chat_about_estimate("remove the labor", _rows(), tax_rate=0.13)
    descs = [r["description"] for r in out["estimate"]["line_items"]]
    assert "Labor" not in descs
    assert len(descs) == 1


def test_change_quantity_updates_and_recomputes_total():
    out = chat_about_estimate("change labor to 3 hours", _rows(), tax_rate=0.13)
    labor = next(r for r in out["estimate"]["line_items"] if r["description"] == "Labor")
    assert labor["quantity"] == 3
    # total reflects the new qty through the server-authoritative recalc.
    assert out["estimate"]["subtotal"] == round(24.0 + 3 * 90.0, 2)


def test_totals_are_always_server_authoritative():
    out = chat_about_estimate("add a refrigerant", _rows(), tax_rate=0.13)
    est = out["estimate"]
    recomputed = round(sum(r["subtotal"] for r in est["line_items"]), 2)
    assert est["subtotal"] == recomputed
    assert est["tax"] == round(est["subtotal"] * 0.13, 2)
    assert est["total"] == round(est["subtotal"] + est["tax"], 2)


def test_unclear_message_keeps_estimate_unchanged_and_asks():
    out = chat_about_estimate("hello there", _rows(), tax_rate=0.13)
    assert len(out["estimate"]["line_items"]) == 2  # untouched
    assert out["reply"]  # a non-empty, helpful reply


# --- Real-model path: the LLM picks the operation, the catalog owns the price ---


def test_model_add_routes_through_catalog_not_the_model():
    # The model only chose add_item("contactor"); the price must come from the catalog.
    model = StubModel(responses=[], chats=[_tc("add_item", item="contactor")])
    out = chat_about_estimate("I also swapped the contactor", _rows(), tax_rate=0.13, model=model)
    contactor = next(
        r for r in out["estimate"]["line_items"] if r["description"] == "Compressor contactor"
    )
    assert contactor["rate"] == 38.0  # catalog price, not model-invented


def test_model_change_quantity_recomputes_server_side():
    model = StubModel(responses=[], chats=[_tc("change_quantity", item="labor", quantity=3)])
    out = chat_about_estimate("make the labor three hours", _rows(), tax_rate=0.13, model=model)
    labor = next(r for r in out["estimate"]["line_items"] if r["description"] == "Labor")
    assert labor["quantity"] == 3
    assert out["estimate"]["subtotal"] == round(24.0 + 3 * 90.0, 2)


def test_model_remove_drops_the_row():
    model = StubModel(responses=[], chats=[_tc("remove_item", item="capacitor")])
    out = chat_about_estimate("take the capacitor off", _rows(), tax_rate=0.13, model=model)
    descs = [r["description"] for r in out["estimate"]["line_items"]]
    assert "Dual run capacitor" not in descs


def test_model_unknown_part_does_not_invent_a_price():
    model = StubModel(responses=[], chats=[_tc("add_item", item="smoke detector")])
    out = chat_about_estimate("add a smoke detector", _rows(), tax_rate=0.13, model=model)
    assert len(out["estimate"]["line_items"]) == 2  # nothing added
    assert out["needs_price"] is True or "couldn't find" in out["reply"].lower()


def test_model_plain_text_answer_leaves_estimate_unchanged():
    # The model can also just answer a question (no tool call) — estimate untouched.
    model = StubModel(
        responses=[],
        chats=[{"content": "R-410A is the modern refrigerant; R-22 is phased out."}],
    )
    out = chat_about_estimate("why R-410A not R-22?", _rows(), tax_rate=0.13, model=model)
    assert len(out["estimate"]["line_items"]) == 2
    assert "R-410A" in out["reply"]
