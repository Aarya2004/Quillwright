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


# --- Rate edits: a user-confirmed price is allowed (Facts-from-Tools: the NUMBER
#     comes from the user, never the model). The apprentice must ask whether the
#     change is just this estimate or the whole catalog before applying. ---


def test_change_rate_estimate_scope_updates_only_this_row():
    # User gave an explicit number ($30) AND the scope (just this estimate).
    model = StubModel(
        responses=[],
        chats=[_tc("change_rate", item="capacitor", rate=30.0, scope="estimate")],
    )
    out = chat_about_estimate("set the capacitor rate to $30 here", _rows(), model=model)
    cap = next(r for r in out["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert cap["rate"] == 30.0
    # It is a user-confirmed edit, so provenance is "user" (not catalog/computed).
    assert cap["price_source"] == "user"
    # The UI is told which row changed so it can pulse that cell.
    assert out["changed"] == "Dual run capacitor"
    # totals recomputed server-side
    assert out["estimate"]["subtotal"] == round(30.0 + 90.0, 2)


def test_change_rate_without_scope_asks_and_does_not_apply():
    # Model called change_rate but the user never said estimate-vs-catalog -> the
    # apprentice ASKS and leaves the rate untouched until told.
    model = StubModel(
        responses=[],
        chats=[_tc("change_rate", item="capacitor", rate=30.0)],  # no scope
    )
    out = chat_about_estimate("make the capacitor $30", _rows(), model=model)
    cap = next(r for r in out["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert cap["rate"] == 24.0  # UNCHANGED — waiting on the scope answer
    assert "catalog" in out["reply"].lower() and "estimate" in out["reply"].lower()
    assert out.get("changed") is None


def test_change_rate_catalog_scope_updates_catalog_and_estimate():
    # scope="catalog": the row changes AND the in-session catalog price changes, so a
    # later add of the same part picks up the new rate.
    rows = _rows()
    set_model = StubModel(
        responses=[],
        chats=[_tc("change_rate", item="capacitor", rate=30.0, scope="catalog")],
    )
    out = chat_about_estimate("set the capacitor to $30 in the catalog", rows, model=set_model)
    cap = next(r for r in out["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert cap["rate"] == 30.0

    # A subsequent add of "capacitor" now prices at the updated catalog rate.
    add_model = StubModel(responses=[], chats=[_tc("add_item", item="capacitor")])
    out2 = chat_about_estimate(
        "add another capacitor", out["estimate"]["line_items"], model=add_model
    )
    added = [r for r in out2["estimate"]["line_items"] if r["description"] == "Dual run capacitor"]
    assert any(r["rate"] == 30.0 for r in added)


def test_change_rate_never_invents_a_number_when_user_is_vague():
    # THE INVARIANT GUARD. The user asks vaguely ("make it cheaper") with NO number.
    # The model must NOT pick a price; it answers (asks for a number) and changes
    # nothing. We give a model that — correctly — returns a question, not a tool call.
    model = StubModel(
        responses=[],
        chats=[{"content": "What rate would you like for the capacitor? I won't guess a price."}],
    )
    out = chat_about_estimate("make the capacitor cheaper", _rows(), model=model)
    cap = next(r for r in out["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert cap["rate"] == 24.0  # untouched — no LLM-invented number entered
    assert out.get("changed") is None
    assert "rate" in out["reply"].lower() or "price" in out["reply"].lower()


def test_keyword_path_change_rate_applies_explicit_dollar_amount():
    # Zero-model fallback (stub Space): "set the capacitor rate to $30" with an
    # explicit $ amount applies it. No scope given in keyword mode -> estimate-only
    # (the keyword path can't hold a follow-up turn; it takes the conservative scope).
    out = chat_about_estimate("set the capacitor rate to $30", _rows(), tax_rate=0.13)
    cap = next(r for r in out["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert cap["rate"] == 30.0
    assert cap["price_source"] == "user"
    assert out["changed"] == "Dual run capacitor"


# --- Refinement Thread (ADR-0013): chat records sanitized ops into a thread ---

ROWS = [
    {"description": "Dual run capacitor", "quantity": 1, "unit": "ea", "rate": 24.0},
    {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
]


def test_chat_returns_updated_thread_with_op():
    out = chat_about_estimate("add a contactor", [dict(r) for r in ROWS], thread=[])
    assert "thread" in out
    assert len(out["thread"]) == 1
    assert out["thread"][0]["message"] == "add a contactor"
    assert out["thread"][0]["op"]  # a non-empty intent line
    assert "$" not in out["thread"][0]["op"]  # invariant: no dollars in the op


def test_chat_thread_accumulates_across_turns():
    out1 = chat_about_estimate("add a contactor", [dict(r) for r in ROWS], thread=[])
    out2 = chat_about_estimate(
        "remove the capacitor",
        out1["estimate"]["line_items"],
        thread=out1["thread"],
    )
    assert len(out2["thread"]) == 2


def test_chat_thread_default_empty_when_omitted():
    out = chat_about_estimate("change labor to 2 hours", [dict(r) for r in ROWS])
    assert out["thread"][0]["op"]


# --- pending rate-change scope follow-up: "make it $20" → ask → "the catalog" applies it ---


def test_change_rate_scope_followup_applies_pending_change():
    # Turn 1: user states a rate without scope → bot asks, returns a pending change.
    model = StubModel(responses=[], chats=[_tc("change_rate", item="capacitor", rate=20)])
    out1 = chat_about_estimate("make the capacitor $20", _rows(), model=model)
    assert "pending" in out1 and out1["pending"]  # a pending rate change is carried out
    # the rate is NOT applied yet (still asking scope)
    c1 = next(r for r in out1["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert c1["rate"] != 20.0

    # Turn 2: user answers "the catalog" → the pending change applies, no model needed.
    out2 = chat_about_estimate(
        "the catalog",
        out1["estimate"]["line_items"],
        thread=out1["thread"],
        pending=out1["pending"],
    )
    c2 = next(r for r in out2["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert c2["rate"] == 20.0
    assert c2["price_source"] == "user"
    assert not out2.get("pending")  # cleared after applying


def test_change_rate_scope_followup_this_estimate():
    model = StubModel(responses=[], chats=[_tc("change_rate", item="capacitor", rate=20)])
    out1 = chat_about_estimate("set the capacitor rate to $20", _rows(), model=model)
    out2 = chat_about_estimate(
        "just this estimate",
        out1["estimate"]["line_items"],
        thread=out1["thread"],
        pending=out1["pending"],
    )
    c = next(r for r in out2["estimate"]["line_items"] if r["description"] == "Dual run capacitor")
    assert c["rate"] == 20.0


# --- keyword path: "N dollars/bucks" (no $ sign) is a RATE, not a quantity ---


def test_keyword_dollars_word_is_a_rate_not_a_quantity():
    out = chat_about_estimate("set the contactor to 45 dollars", _rows_with_contactor())
    c = next(r for r in out["estimate"]["line_items"] if r["description"] == "Compressor contactor")
    assert c["rate"] == 45.0  # applied as a rate
    assert c["quantity"] == 1.0  # NOT read as quantity 45
    assert c["price_source"] == "user"


def test_keyword_bucks_word_is_a_rate():
    out = chat_about_estimate("make the labor 80 bucks an hour", _rows_with_contactor())
    labor = next(r for r in out["estimate"]["line_items"] if r["description"] == "Labor")
    assert labor["rate"] == 80.0


def _rows_with_contactor():
    return [
        {"description": "Compressor contactor", "quantity": 1, "unit": "ea", "rate": 38.0},
        {"description": "Labor", "quantity": 1, "unit": "hr", "rate": 90.0},
    ]


# --- answer read-only questions about the estimate (total / what's on it) ---


def test_keyword_answers_whats_the_total():
    out = chat_about_estimate("what's the total", _rows_with_contactor())
    # 38 + 90 = 128, * 1.13 = 144.64
    assert "144.64" in out["reply"]
    # a question doesn't change the estimate
    assert len(out["estimate"]["line_items"]) == 2


def test_keyword_answers_whats_on_the_estimate():
    out = chat_about_estimate("what's on the estimate", _rows_with_contactor())
    assert "contactor" in out["reply"].lower() and "labor" in out["reply"].lower()


def test_keyword_question_records_no_edit_op():
    out = chat_about_estimate("how much is it", _rows_with_contactor())
    # asking is not an edit; thread gets a question turn at most, estimate unchanged
    assert len(out["estimate"]["line_items"]) == 2


def test_chat_falls_back_to_keyword_when_model_errors():
    class BoomBrain:
        name = "boom"

        def chat(self, messages, tools):
            raise RuntimeError("500 from Ollama")

    out = chat_about_estimate("add a contactor", _rows_with_contactor(), model=BoomBrain())
    # Degrades to the keyword path → still adds the contactor, no exception.
    descs = [r["description"] for r in out["estimate"]["line_items"]]
    assert descs.count("Compressor contactor") == 2  # the add succeeded via fallback
