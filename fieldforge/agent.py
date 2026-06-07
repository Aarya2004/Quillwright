from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from fieldforge.models import Capture, Observation, LineItem, Estimate, TraceStep
from fieldforge.catalog import Catalog
from fieldforge.resolver import Model
from fieldforge.tools import perceive, lookup_price, compute, draft_line_item
from fieldforge.brain_loop import run_brain


class AgentState(TypedDict):
    capture: Capture
    observations: list[Observation]
    line_items: list[LineItem]
    trace: list[TraceStep]
    estimate: Optional[Estimate]


def build_agent(perception_model: Model, catalog: Catalog, checkpointer, brain_model=None):
    def perceive_node(state: AgentState) -> dict:
        obs: list[Observation] = []
        for path in state["capture"].image_paths:
            obs.extend(perceive(path, perception_model))
        trace = state["trace"] + [
            TraceStep(
                action="perceive",
                model=getattr(perception_model, "name", "model"),
                detail=f"found {len(obs)} observation(s)",
            )
        ]
        return {"observations": obs, "trace": trace}

    def deterministic_price(state: AgentState) -> dict:
        items = list(state["line_items"])
        trace = list(state["trace"])
        for ob in state["observations"]:
            res = lookup_price(ob.text, catalog)
            if not res["found"]:
                # Agent Pause: ask the human for a price; resumed value comes back here.
                human_rate = interrupt({"reason": f"No price for '{ob.text}'", "item": ob.text})
                items.append(
                    draft_line_item(
                        ob.text, qty=1, unit="ea", rate=float(human_rate), source="user"
                    )
                )
                trace.append(
                    TraceStep(action="price", detail=f"user priced {ob.text}", status="ok")
                )
                continue
            subtotal = compute(f"1 * {res['rate']}")  # qty defaults to 1 in the core
            items.append(
                draft_line_item(
                    res["description"], qty=1, unit=res["unit"], rate=res["rate"], source="catalog"
                )
            )
            trace.append(
                TraceStep(
                    action="price",
                    model="lookup_price",
                    detail=f"{res['description']} -> {subtotal}",
                )
            )
        return {"line_items": items, "trace": trace}

    def brain_price(state: AgentState) -> dict:
        # The LLM brain decides which items to add; deterministic tools own the numbers.
        obs_text = ", ".join(ob.text for ob in state["observations"])
        priced_extra: list[LineItem] = []
        while True:
            items, brain_trace, pause = run_brain(
                brain_model,
                catalog,
                observations_text=obs_text,
                transcript=state["capture"].transcript,
            )
            if pause is None:
                trace = state["trace"] + brain_trace
                return {"line_items": list(state["line_items"]) + priced_extra + items, "trace": trace}
            # Missing price -> ask the human, record it on the catalog, then re-run the brain.
            human_rate = interrupt({"reason": f"No price for '{pause['item']}'", "item": pause["item"]})
            priced_extra.append(
                draft_line_item(
                    pause["item"], qty=1, unit="ea", rate=float(human_rate), source="user"
                )
            )
            catalog.add(pause["item"], pause["item"], "ea", float(human_rate))

    price_node = brain_price if brain_model is not None else deterministic_price

    def assemble_node(state: AgentState) -> dict:
        est = Estimate(
            job_title=state["capture"].trade_hint or "Job",
            line_items=state["line_items"],
            tax_rate=0.13,
        )
        trace = state["trace"] + [TraceStep(action="assemble", detail=f"total {est.total}")]
        return {"estimate": est, "trace": trace}

    g = StateGraph(AgentState)
    g.add_node("perceive", perceive_node)
    g.add_node("price", price_node)
    g.add_node("assemble", assemble_node)
    g.add_edge(START, "perceive")
    g.add_edge("perceive", "price")
    g.add_edge("price", "assemble")
    g.add_edge("assemble", END)
    return g.compile(checkpointer=checkpointer)
