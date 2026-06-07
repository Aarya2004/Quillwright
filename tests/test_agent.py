from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent


def _run(agent, capture, thread="t1"):
    cfg = {"configurable": {"thread_id": thread}}
    return agent.invoke(
        {"capture": capture, "observations": [], "line_items": [], "trace": [], "estimate": None},
        cfg,
    )


def test_agent_builds_estimate_when_all_prices_found():
    perception = StubModel(
        responses=[
            '[{"kind":"part","text":"capacitor","confidence":0.9},'
            ' {"kind":"part","text":"labor","confidence":0.9}]'
        ]
    )
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(perception_model=perception, catalog=cat, checkpointer=InMemorySaver())
    cap = Capture(
        image_paths=["/tmp/a.jpg"], transcript="replaced capacitor, 1h labor", trade_hint="hvac"
    )
    out = _run(agent, cap)
    est = out["estimate"]
    assert est is not None
    descs = [li.description.lower() for li in est.line_items]
    assert any("capacitor" in d for d in descs)
    # Facts-from-Tools: every line item price came from catalog/computed, never the LLM
    assert all(li.price_source in ("catalog", "computed", "user") for li in est.line_items)
    # Trace recorded the perceive + pricing steps
    assert any(s.action == "perceive" for s in out["trace"])


def test_agent_pauses_when_price_missing():
    perception = StubModel(responses=['[{"kind":"part","text":"unobtainium","confidence":0.9}]'])
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(perception_model=perception, catalog=cat, checkpointer=InMemorySaver())
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="installed unobtainium", trade_hint="hvac")
    cfg = {"configurable": {"thread_id": "t2"}}
    out = agent.invoke(
        {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None}, cfg
    )
    # LangGraph surfaces an interrupt rather than finishing
    assert "__interrupt__" in out


def _tc(name, **args):
    return {"tool_calls": [{"function": {"name": name, "arguments": args}}]}


def test_agent_uses_llm_brain_when_provided():
    perception = StubModel(responses=['[{"kind":"part","text":"capacitor","confidence":0.9}]'])
    brain = StubModel(
        responses=[],
        chats=[_tc("add_priced_item", item="capacitor"), _tc("finish")],
        name="nemotron-test",
    )
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(
        perception_model=perception, catalog=cat, checkpointer=InMemorySaver(), brain_model=brain
    )
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="fixed capacitor", trade_hint="hvac")
    out = _run(agent, cap, thread="brain1")
    est = out["estimate"]
    assert est is not None
    assert any("capacitor" in li.description.lower() for li in est.line_items)
    assert any(s.action == "add_priced_item" for s in out["trace"])


def test_agent_resumes_after_human_supplies_price():
    perception = StubModel(responses=['[{"kind":"part","text":"unobtainium","confidence":0.9}]'])
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(perception_model=perception, catalog=cat, checkpointer=InMemorySaver())
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="installed unobtainium", trade_hint="hvac")
    cfg = {"configurable": {"thread_id": "t3"}}
    agent.invoke(
        {"capture": cap, "observations": [], "line_items": [], "trace": [], "estimate": None}, cfg
    )  # pauses
    out = agent.invoke(Command(resume=55.0), cfg)  # human supplies $55
    est = out["estimate"]
    assert est is not None
    assert any(li.price_source == "user" and li.rate == 55.0 for li in est.line_items)
