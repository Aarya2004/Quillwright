from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from fieldforge.models import Capture, Observation, LineItem, Estimate, TraceStep
from fieldforge.catalog import Catalog
from fieldforge.resolver import Model
from fieldforge.tools import perceive, lookup_price, compute, draft_line_item


class AgentState(TypedDict):
    capture: Capture
    observations: list[Observation]
    line_items: list[LineItem]
    trace: list[TraceStep]
    estimate: Optional[Estimate]


def build_agent(perception_model: Model, catalog: Catalog, checkpointer):
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

    def price_node(state: AgentState) -> dict:
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
