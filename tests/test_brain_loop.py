from fieldforge.brain_loop import run_brain
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel

CAT = Catalog.from_file("data/sample_catalog.json")


def _tc(name, **args):
    return {"tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_brain_adds_items_then_finishes():
    model = StubModel(
        responses=[],
        chats=[
            _tc("add_priced_item", item="capacitor"),
            _tc("add_priced_item", item="labor"),
            _tc("finish"),
        ],
    )
    line_items, trace, pause = run_brain(
        model, CAT, observations_text="capacitor, labor", transcript="fixed it"
    )
    assert pause is None
    descs = [li.description.lower() for li in line_items]
    assert any("capacitor" in d for d in descs) and any("labor" in d for d in descs)
    # every number came from the catalog/compute, never the model
    assert all(li.price_source == "catalog" for li in line_items)
    # the loop recorded a trace step per tool call
    assert any(s.action == "add_priced_item" for s in trace)


def test_brain_pauses_on_missing_price():
    model = StubModel(responses=[], chats=[_tc("add_priced_item", item="unobtainium")])
    line_items, trace, pause = run_brain(
        model, CAT, observations_text="unobtainium", transcript="installed it"
    )
    assert pause is not None and pause["item"] == "unobtainium"


def test_brain_respects_step_budget():
    # A model that never calls finish -> the loop must stop at the budget.
    model = StubModel(
        responses=[],
        chats=[_tc("add_priced_item", item="capacitor")] * 50,
    )
    line_items, trace, pause = run_brain(
        model, CAT, observations_text="capacitor", transcript="x", max_steps=5
    )
    # stopped without running forever
    assert len([s for s in trace if s.action == "add_priced_item"]) <= 5
