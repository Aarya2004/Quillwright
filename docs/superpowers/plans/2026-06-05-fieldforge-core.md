# FieldForge Irreducible Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Irreducible Core (ADR-0007): Capture (photos + voice) → a LangGraph supervised agent builds a correct itemized Estimate live (Facts-from-Tools) → one Agent Pause + one human Interrupt → inline-editable Estimate → PDF export, on the Private Stack only.

**Architecture:** A Gradio app whose two-panel Workspace streams a LangGraph agent's Trace (left) while the Estimate builds (right). The agent calls typed Tools through a Model **resolver** (so models are stubbable in tests and swappable to Modal/HF later). Numbers come only from `lookup_price`/`compute` or user-confirmed edits (Facts-from-Tools, ADR-0004). Human-in-the-loop via LangGraph `interrupt` + InMemorySaver checkpointer (ADR-0002/0008).

**Tech Stack:** Python 3.11, Gradio, LangGraph (+ langchain-core), pytest, Pydantic (data models), ReportLab (PDF). Models via a resolver backed by local/HF inference or a stub; Modal deferred (ADR-0005).

**Spec & decisions:** [`../specs/2026-06-05-fieldforge-design.md`](../specs/2026-06-05-fieldforge-design.md) · [`CONTEXT.md`](../../../CONTEXT.md) · ADRs 0001–0008.

---

## File structure

```
fieldforge/
├── __init__.py
├── models.py            # Pydantic data models: Capture, Observation, LineItem, Estimate, TraceStep
├── resolver.py          # ModelResolver: Model Role -> callable; StubModel for tests (ADR-0001/0005)
├── catalog.py           # sample pricing catalog + lookup (backs lookup_price)
├── tools.py             # the core tools: perceive, lookup_price, compute, draft_line_item, flag_for_human
├── agent.py             # LangGraph graph: plan->act->self-check loop, interrupt, Trace emission (ADR-0002/0008)
├── pdf.py               # Estimate -> PDF (ReportLab)
└── app.py               # Gradio two-panel Workspace wiring (ADR-0007 §5)

tests/
├── test_models.py
├── test_resolver.py
├── test_catalog.py
├── test_tools.py
├── test_agent.py
└── test_pdf.py

data/
└── sample_catalog.json  # curated, clearly-labeled SAMPLE pricing (HVAC demo trade)

pyproject.toml           # deps + pytest config
```

Each file has one responsibility. `models.py` is the shared contract every other module imports. Tests never need a GPU: the resolver returns a `StubModel` in tests.

---

## Task 1: Project scaffold + data models

**Files:**
- Create: `pyproject.toml`, `fieldforge/__init__.py`, `fieldforge/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "fieldforge"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "gradio>=4.44",
  "langgraph>=0.2",
  "langchain-core>=0.3",
  "pydantic>=2.7",
  "reportlab>=4.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
```

- [ ] **Step 2: Create `fieldforge/__init__.py` (empty)**

```python
```

- [ ] **Step 3: Write the failing test for the data models**

```python
# tests/test_models.py
from fieldforge.models import Capture, Observation, LineItem, Estimate, TraceStep


def test_line_item_subtotal_is_qty_times_rate():
    item = LineItem(description="Capacitor", quantity=2, unit="ea", rate=24.0)
    assert item.subtotal == 48.0


def test_estimate_total_sums_subtotals_with_tax():
    est = Estimate(
        job_title="AC repair",
        line_items=[
            LineItem(description="Capacitor", quantity=1, unit="ea", rate=24.0),
            LineItem(description="Labor", quantity=2, unit="hr", rate=90.0),
        ],
        tax_rate=0.13,
    )
    assert est.subtotal == 204.0
    assert round(est.tax, 2) == 26.52
    assert round(est.total, 2) == 230.52


def test_observation_and_capture_and_tracestep_construct():
    obs = Observation(kind="part", text="dual run capacitor 45/5 uF", confidence=0.82)
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="replaced the capacitor", trade_hint="hvac")
    step = TraceStep(action="perceive", model="StubModel", detail="found 1 part", confidence=0.82)
    assert obs.kind == "part" and cap.trade_hint == "hvac" and step.action == "perceive"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.models'`

- [ ] **Step 5: Implement `fieldforge/models.py`**

```python
from typing import Literal
from pydantic import BaseModel, computed_field


class Observation(BaseModel):
    kind: Literal["equipment", "part", "damage", "text", "other"]
    text: str
    confidence: float = 1.0


class Capture(BaseModel):
    image_paths: list[str] = []
    transcript: str = ""
    trade_hint: str | None = None


class LineItem(BaseModel):
    description: str
    quantity: float
    unit: str
    rate: float
    price_source: Literal["catalog", "user", "computed"] = "catalog"

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.rate, 2)


class Estimate(BaseModel):
    job_title: str
    line_items: list[LineItem] = []
    tax_rate: float = 0.0

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(sum(i.subtotal for i in self.line_items), 2)

    @computed_field
    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @computed_field
    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax, 2)


class TraceStep(BaseModel):
    action: str
    model: str | None = None
    detail: str = ""
    confidence: float | None = None
    status: Literal["ok", "paused", "error"] = "ok"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml fieldforge/__init__.py fieldforge/models.py tests/test_models.py
git commit -m "feat: project scaffold and core data models"
```

---

## Task 2: Model resolver + stub model

**Files:**
- Create: `fieldforge/resolver.py`
- Test: `tests/test_resolver.py`

The resolver maps a Model Role to a callable. In tests/dev it returns a `StubModel` with scripted outputs; later a real backend (HF/Modal) fills the same interface (ADR-0001/0005).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py
from fieldforge.resolver import ModelResolver, StubModel


def test_stub_model_returns_scripted_response():
    stub = StubModel(responses=["hello"])
    assert stub.generate("anything") == "hello"


def test_resolver_returns_model_for_role():
    resolver = ModelResolver(mode="private", overrides={"perception": StubModel(responses=["ok"])})
    model = resolver.for_role("perception")
    assert model.generate("x") == "ok"


def test_resolver_unknown_role_raises():
    resolver = ModelResolver(mode="private")
    try:
        resolver.for_role("nope")
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.resolver'`

- [ ] **Step 3: Implement `fieldforge/resolver.py`**

```python
from typing import Protocol


class Model(Protocol):
    name: str
    def generate(self, prompt: str) -> str: ...


class StubModel:
    """Deterministic model for tests/dev. Pops scripted responses in order."""
    def __init__(self, responses: list[str], name: str = "StubModel"):
        self._responses = list(responses)
        self.name = name

    def generate(self, prompt: str) -> str:
        if not self._responses:
            return ""
        return self._responses.pop(0)


# Which concrete model fills each role per Mode. Real backends wired later (ADR-0005).
PRIVATE_STACK = {
    "perception": "MiniCPM-V-4.6",
    "audio": "whisper-local",
    "brain": "gpt-oss-20b",
}
BEST_STACK = {
    "perception": "Nemotron-3-Nano-Omni",
    "audio": "Nemotron-3-Nano-Omni",
    "brain": "gpt-oss-20b",
}


class ModelResolver:
    def __init__(self, mode: str = "private", overrides: dict[str, Model] | None = None):
        self.mode = mode
        self._overrides = overrides or {}
        self._roles = PRIVATE_STACK if mode == "private" else BEST_STACK

    def for_role(self, role: str) -> Model:
        if role in self._overrides:
            return self._overrides[role]
        if role not in self._roles:
            raise KeyError(f"unknown role: {role}")
        # No real backend yet in the core plan: a named stub stands in.
        return StubModel(responses=[""], name=self._roles[role])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_resolver.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add fieldforge/resolver.py tests/test_resolver.py
git commit -m "feat: model resolver with stub model for role resolution"
```

---

## Task 3: Sample pricing catalog

**Files:**
- Create: `data/sample_catalog.json`, `fieldforge/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write `data/sample_catalog.json` (clearly-labeled SAMPLE data)**

```json
{
  "_note": "SAMPLE pricing for demo only. Not real market prices.",
  "items": [
    {"key": "capacitor", "description": "Dual run capacitor", "unit": "ea", "rate": 24.0},
    {"key": "contactor", "description": "Compressor contactor", "unit": "ea", "rate": 38.0},
    {"key": "refrigerant_r410a", "description": "R-410A refrigerant", "unit": "lb", "rate": 30.0},
    {"key": "labor", "description": "Labor", "unit": "hr", "rate": 90.0}
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_catalog.py
from fieldforge.catalog import Catalog


def test_lookup_exact_key():
    cat = Catalog.from_file("data/sample_catalog.json")
    hit = cat.lookup("capacitor")
    assert hit is not None and hit["rate"] == 24.0 and hit["unit"] == "ea"


def test_lookup_is_case_insensitive_and_trims():
    cat = Catalog.from_file("data/sample_catalog.json")
    assert cat.lookup("  Capacitor ")["rate"] == 24.0


def test_lookup_miss_returns_none():
    cat = Catalog.from_file("data/sample_catalog.json")
    assert cat.lookup("flux capacitor") is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.catalog'`

- [ ] **Step 4: Implement `fieldforge/catalog.py`**

```python
import json


class Catalog:
    def __init__(self, items: list[dict]):
        self._by_key = {i["key"].lower(): i for i in items}

    @classmethod
    def from_file(cls, path: str) -> "Catalog":
        with open(path) as f:
            data = json.load(f)
        return cls(data["items"])

    def lookup(self, key: str) -> dict | None:
        return self._by_key.get(key.strip().lower())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_catalog.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add data/sample_catalog.json fieldforge/catalog.py tests/test_catalog.py
git commit -m "feat: sample pricing catalog with lookup"
```

---

## Task 4: Core tools (Facts-from-Tools)

**Files:**
- Create: `fieldforge/tools.py`
- Test: `tests/test_tools.py`

Tools are pure functions. `compute` does all arithmetic (never the LLM). `lookup_price` returns catalog data or signals a miss → `flag_for_human`. `perceive` calls the perception model via the resolver and parses Observations.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools.py
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.tools import compute, lookup_price, perceive, draft_line_item, flag_for_human
from fieldforge.models import Observation, LineItem


def test_compute_evaluates_arithmetic_safely():
    assert compute("2 * 90") == 180.0
    assert compute("24 * 1 + 90 * 2") == 204.0


def test_compute_rejects_non_arithmetic():
    try:
        compute("__import__('os').system('echo hi')")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_lookup_price_hit_returns_priced_dict():
    cat = Catalog.from_file("data/sample_catalog.json")
    res = lookup_price("capacitor", cat)
    assert res["found"] is True and res["rate"] == 24.0 and res["unit"] == "ea"


def test_lookup_price_miss_flags_for_human():
    cat = Catalog.from_file("data/sample_catalog.json")
    res = lookup_price("unobtainium", cat)
    assert res["found"] is False


def test_perceive_parses_observations_from_model_json():
    model = StubModel(responses=[
        '[{"kind":"part","text":"dual run capacitor","confidence":0.8}]'
    ])
    obs = perceive("/tmp/a.jpg", model)
    assert len(obs) == 1 and isinstance(obs[0], Observation) and obs[0].kind == "part"


def test_draft_line_item_marks_source_and_computes_subtotal():
    item = draft_line_item("Capacitor", qty=2, unit="ea", rate=24.0, source="catalog")
    assert isinstance(item, LineItem) and item.subtotal == 48.0 and item.price_source == "catalog"


def test_flag_for_human_returns_pause_payload():
    payload = flag_for_human("No price for 'unobtainium'")
    assert payload["pause"] is True and "unobtainium" in payload["reason"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.tools'`

- [ ] **Step 3: Implement `fieldforge/tools.py`**

```python
import ast
import json
import operator
from fieldforge.models import Observation, LineItem
from fieldforge.catalog import Catalog
from fieldforge.resolver import Model

# Safe arithmetic evaluator — the ONLY place numbers are computed (Facts-from-Tools, ADR-0004).
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def compute(expr: str) -> float:
    try:
        tree = ast.parse(expr, mode="eval")
        return round(float(_eval(tree.body)), 2)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"bad expression: {expr}") from e


def lookup_price(item_key: str, catalog: Catalog) -> dict:
    hit = catalog.lookup(item_key)
    if hit is None:
        return {"found": False, "item": item_key}
    return {"found": True, "description": hit["description"], "unit": hit["unit"], "rate": hit["rate"]}


def perceive(image_path: str, model: Model) -> list[Observation]:
    raw = model.generate(f"List observations as JSON for image: {image_path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [Observation(**o) for o in data]


def draft_line_item(description: str, qty: float, unit: str, rate: float, source: str = "catalog") -> LineItem:
    return LineItem(description=description, quantity=qty, unit=unit, rate=rate, price_source=source)


def flag_for_human(reason: str) -> dict:
    return {"pause": True, "reason": reason}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_tools.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add fieldforge/tools.py tests/test_tools.py
git commit -m "feat: core tools with safe compute (Facts-from-Tools)"
```

---

## Task 5: LangGraph agent loop with Trace + Agent Pause

**Files:**
- Create: `fieldforge/agent.py`
- Test: `tests/test_agent.py`

A LangGraph graph over shared state. Nodes: `perceive_node` → `price_node` (per observation: lookup → compute → draft, or `interrupt` via flag) → `assemble_node` (builds the Estimate). State holds `capture`, `observations`, `line_items`, `trace`, `estimate`. `interrupt` (ADR-0002/0008) raises an Agent Pause; resuming with a human-supplied price continues. The Trace is appended at every step.

- [ ] **Step 1: Write the failing test (happy path: all prices found)**

```python
# tests/test_agent.py
from langgraph.checkpoint.memory import InMemorySaver
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent


def _run(agent, capture, thread="t1"):
    cfg = {"configurable": {"thread_id": thread}}
    return agent.invoke({"capture": capture, "observations": [], "line_items": [],
                         "trace": [], "estimate": None}, cfg)


def test_agent_builds_estimate_when_all_prices_found():
    perception = StubModel(responses=[
        '[{"kind":"part","text":"capacitor","confidence":0.9},'
        ' {"kind":"part","text":"labor","confidence":0.9}]'
    ])
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(perception_model=perception, catalog=cat, checkpointer=InMemorySaver())
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="replaced capacitor, 1h labor", trade_hint="hvac")
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
    out = agent.invoke({"capture": cap, "observations": [], "line_items": [],
                        "trace": [], "estimate": None}, cfg)
    # LangGraph surfaces an interrupt rather than finishing
    assert "__interrupt__" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.agent'`

- [ ] **Step 3: Implement `fieldforge/agent.py`**

```python
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
        trace = state["trace"] + [TraceStep(
            action="perceive", model=getattr(perception_model, "name", "model"),
            detail=f"found {len(obs)} observation(s)",
        )]
        return {"observations": obs, "trace": trace}

    def price_node(state: AgentState) -> dict:
        items = list(state["line_items"])
        trace = list(state["trace"])
        for ob in state["observations"]:
            res = lookup_price(ob.text, catalog)
            if not res["found"]:
                # Agent Pause: ask the human for a price; resumed value comes back here.
                human_rate = interrupt({"reason": f"No price for '{ob.text}'", "item": ob.text})
                items.append(draft_line_item(ob.text, qty=1, unit="ea",
                                             rate=float(human_rate), source="user"))
                trace.append(TraceStep(action="price", detail=f"user priced {ob.text}",
                                       status="ok"))
                continue
            subtotal = compute(f"1 * {res['rate']}")  # qty defaults to 1 in the core
            items.append(draft_line_item(res["description"], qty=1, unit=res["unit"],
                                         rate=res["rate"], source="catalog"))
            trace.append(TraceStep(action="price", model="lookup_price",
                                   detail=f"{res['description']} -> {subtotal}"))
        return {"line_items": items, "trace": trace}

    def assemble_node(state: AgentState) -> dict:
        est = Estimate(job_title=state["capture"].trade_hint or "Job",
                       line_items=state["line_items"], tax_rate=0.13)
        trace = state["trace"] + [TraceStep(action="assemble",
                                            detail=f"total {est.total}")]
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_agent.py -v`
Expected: PASS (2 tests). If the interrupt key differs by LangGraph version, inspect `out.keys()` and adjust the assertion to the actual interrupt surface (documented in the LangGraph human-in-the-loop guide).

- [ ] **Step 5: Add the resume (human-answered pause) test**

```python
# append to tests/test_agent.py
from langgraph.types import Command


def test_agent_resumes_after_human_supplies_price():
    perception = StubModel(responses=['[{"kind":"part","text":"unobtainium","confidence":0.9}]'])
    cat = Catalog.from_file("data/sample_catalog.json")
    agent = build_agent(perception_model=perception, catalog=cat, checkpointer=InMemorySaver())
    cap = Capture(image_paths=["/tmp/a.jpg"], transcript="installed unobtainium", trade_hint="hvac")
    cfg = {"configurable": {"thread_id": "t3"}}
    agent.invoke({"capture": cap, "observations": [], "line_items": [],
                  "trace": [], "estimate": None}, cfg)  # pauses
    out = agent.invoke(Command(resume=55.0), cfg)        # human supplies $55
    est = out["estimate"]
    assert est is not None
    assert any(li.price_source == "user" and li.rate == 55.0 for li in est.line_items)
```

- [ ] **Step 6: Run the resume test to verify it passes**

Run: `pytest tests/test_agent.py::test_agent_resumes_after_human_supplies_price -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add fieldforge/agent.py tests/test_agent.py
git commit -m "feat: LangGraph agent loop with Trace and Agent Pause/resume"
```

---

## Task 6: Estimate → PDF export

**Files:**
- Create: `fieldforge/pdf.py`
- Test: `tests/test_pdf.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf.py
import os
from fieldforge.models import Estimate, LineItem
from fieldforge.pdf import estimate_to_pdf


def test_pdf_is_written_and_nonempty(tmp_path):
    est = Estimate(job_title="AC repair",
                   line_items=[LineItem(description="Capacitor", quantity=1, unit="ea", rate=24.0)],
                   tax_rate=0.13)
    out = tmp_path / "est.pdf"
    estimate_to_pdf(est, str(out))
    assert os.path.exists(out) and os.path.getsize(out) > 500
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.pdf'`

- [ ] **Step 3: Implement `fieldforge/pdf.py`**

```python
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from fieldforge.models import Estimate


def estimate_to_pdf(est: Estimate, path: str) -> None:
    c = canvas.Canvas(path, pagesize=LETTER)
    width, height = LETTER
    y = height - inch
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, f"Estimate — {est.job_title}")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(inch, y - 14, "AI-generated draft — review before sending. Sample pricing.")
    y -= 48
    c.setFont("Helvetica-Bold", 10)
    c.drawString(inch, y, "Description"); c.drawString(4.2 * inch, y, "Qty")
    c.drawString(4.9 * inch, y, "Rate"); c.drawString(5.9 * inch, y, "Subtotal")
    y -= 16
    c.setFont("Helvetica", 10)
    for li in est.line_items:
        c.drawString(inch, y, li.description[:40])
        c.drawString(4.2 * inch, y, f"{li.quantity:g} {li.unit}")
        c.drawString(4.9 * inch, y, f"${li.rate:.2f}")
        c.drawString(5.9 * inch, y, f"${li.subtotal:.2f}")
        y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(4.9 * inch, y, "Subtotal:"); c.drawString(5.9 * inch, y, f"${est.subtotal:.2f}"); y -= 14
    c.drawString(4.9 * inch, y, f"Tax ({est.tax_rate:.0%}):"); c.drawString(5.9 * inch, y, f"${est.tax:.2f}"); y -= 14
    c.drawString(4.9 * inch, y, "Total:"); c.drawString(5.9 * inch, y, f"${est.total:.2f}")
    c.showPage()
    c.save()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_pdf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fieldforge/pdf.py tests/test_pdf.py
git commit -m "feat: estimate to PDF export with honesty banner"
```

---

## Task 7: Workspace UI — theme, render helpers, and presenters

**Design target:** [`docs/design/frontend-core-workspace.md`](../../design/frontend-core-workspace.md). Build the user's mockup faithfully in Gradio with custom CSS: a dark streaming **AI Forge log** (left, 40%) and a light **Draft Estimate** (right, 60%), job-title-only top bar, footer with language dropdown + Finalize. Non-functional elements (side/mobile nav, top-bar notifications/settings/avatar, LIVE SYNC pill, Edit Manual) are intentionally omitted.

**Files:**
- Create: `fieldforge/ui.py` (pure render helpers — unit-testable, no Gradio)
- Test: `tests/test_ui.py`

The HTML-producing presenters live in `ui.py` so they can be tested without launching Gradio. `app.py` (Task 7b) only wires them.

- [ ] **Step 1: Write the failing test for the presenters**

```python
# tests/test_ui.py
from fieldforge.models import LineItem, Estimate, TraceStep
from fieldforge.ui import trace_html, estimate_rows, summary_text


def test_trace_html_marks_done_and_active_steps():
    steps = [
        TraceStep(action="perceive", model="MiniCPM-V-4.6", detail="found 2", status="ok"),
        TraceStep(action="price", model="lookup_price", detail="pricing…", status="active"),
    ]
    html = trace_html(steps)
    assert "check_circle" in html          # done step gets the check icon
    assert "terminal-cursor" in html       # active step gets the blinking cursor
    assert "MiniCPM-V-4.6" in html          # model badge surfaced inline


def test_trace_html_empty_shows_waiting():
    assert "Waiting" in trace_html([])


def test_estimate_rows_maps_line_items_to_table_rows():
    est = Estimate(job_title="AC repair", line_items=[
        LineItem(description="Capacitor", quantity=1, unit="ea", rate=42.5),
    ], tax_rate=0.09)
    rows = estimate_rows(est)
    assert rows == [["Capacitor", "1 ea", "$42.50", "$42.50"]]


def test_summary_text_formats_subtotal_tax_total():
    est = Estimate(job_title="x", line_items=[
        LineItem(description="a", quantity=1, unit="ea", rate=100.0),
    ], tax_rate=0.09)
    assert summary_text(est) == "Subtotal $100.00 · Tax (9%) $9.00 · Total $109.00"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_ui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fieldforge.ui'`

- [ ] **Step 3: Implement `fieldforge/ui.py`**

```python
from fieldforge.models import Estimate, TraceStep

# Status drives the icon: done -> check, active -> pulsing dot + cursor, error -> warning.
def _step_html(s: TraceStep) -> str:
    badge = f'<span class="ff-badge">{s.model}</span>' if s.model else ""
    if s.status == "active":
        marker = '<span class="ff-dot"></span>'
        cursor = '<span class="terminal-cursor"></span>'
    elif s.status == "error":
        marker = '<span class="material-symbols-outlined ff-err">error</span>'
        cursor = ""
    else:
        marker = '<span class="material-symbols-outlined ff-ok">check_circle</span>'
        cursor = ""
    return (f'<div class="ff-step">{marker}'
            f'<div class="ff-step-body"><p>{s.action}: {s.detail}{cursor}</p>{badge}</div></div>')


def trace_html(steps: list[TraceStep]) -> str:
    if not steps:
        return '<div class="ff-log"><p class="ff-wait">Waiting for capture…</p></div>'
    return '<div class="ff-log">' + "".join(_step_html(s) for s in steps) + "</div>"


def estimate_rows(est: Estimate | None) -> list[list[str]]:
    if est is None:
        return []
    return [[li.description, f"{li.quantity:g} {li.unit}", f"${li.rate:.2f}", f"${li.subtotal:.2f}"]
            for li in est.line_items]


def summary_text(est: Estimate | None) -> str:
    if est is None:
        return "Subtotal $0.00 · Tax (0%) $0.00 · Total $0.00"
    return (f"Subtotal ${est.subtotal:.2f} · Tax ({est.tax_rate:.0%}) ${est.tax:.2f} "
            f"· Total ${est.total:.2f}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_ui.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Create the CSS theme `fieldforge/theme.css`**

```css
/* FieldForge — industrial precision. Source: docs/design/frontend-core-workspace.md */
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@700;800;900&family=Inter:wght@400;700&family=JetBrains+Mono:wght@500&family=Material+Symbols+Outlined&display=swap');
:root { --ff-primary:#964900; --ff-accent:#f57c00; --ff-log-bg:#10191E; --ff-log-border:#1C2931; --ff-ok:#22c55e; }
.ff-title { font-family:'Hanken Grotesk'; font-weight:900; color:var(--ff-primary); font-size:24px; letter-spacing:-0.01em; }
.ff-log { background:var(--ff-log-bg); color:#cdd6db; font-family:'JetBrains Mono',monospace; font-size:13px; padding:24px; min-height:420px; border-radius:8px; }
.ff-step { display:flex; gap:12px; padding:8px 0; align-items:flex-start; }
.ff-step-body p { color:#fff; opacity:.92; margin:0; }
.ff-badge { display:inline-block; margin-top:4px; color:var(--ff-accent); font-size:11px; }
.ff-ok { color:var(--ff-ok); font-variation-settings:'FILL' 1; }
.ff-err { color:#ba1a1a; }
.ff-dot { width:8px; height:8px; border-radius:50%; background:var(--ff-accent); display:inline-block; margin-top:6px; animation:ff-pulse 2s infinite; }
.ff-wait { color:#546E7A; }
.terminal-cursor { display:inline-block; width:8px; height:16px; background:var(--ff-accent); margin-left:4px; vertical-align:middle; animation:ff-blink 1s step-end infinite; }
@keyframes ff-blink { 50% { opacity:0; } }
@keyframes ff-pulse { 50% { opacity:.4; transform:scale(1.15); } }
.material-symbols-outlined { font-family:'Material Symbols Outlined'; font-size:20px; vertical-align:middle; }
.ff-pane-head { font-family:'Hanken Grotesk'; font-weight:700; }
```

- [ ] **Step 6: Commit**

```bash
git add fieldforge/ui.py fieldforge/theme.css tests/test_ui.py
git commit -m "feat: workspace UI presenters + industrial CSS theme"
```

---

## Task 7b: Gradio Workspace app (wiring)

**Files:**
- Create: `fieldforge/app.py`
- Test: manual (Gradio UI) — verified by launch.

Wires Capture → agent Run (streaming Trace left, editable Estimate right) → Agent-Pause card → PDF. Uses the StubModel-backed perception so it runs without a GPU; real models swap in via the resolver later. The language dropdown and "Finalize & Send" are rendered now; multilingual activates in the post-core layer (ADR-0007).

- [ ] **Step 1: Implement `fieldforge/app.py`**

```python
from pathlib import Path
import gradio as gr
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent
from fieldforge.pdf import estimate_to_pdf
from fieldforge.ui import trace_html, estimate_rows, summary_text

CATALOG = Catalog.from_file("data/sample_catalog.json")
CSS = (Path(__file__).parent / "theme.css").read_text()
# Demo stub perception; real runs use the resolver's perception model.
DEMO_PERCEPTION = lambda: StubModel(responses=[
    '[{"kind":"part","text":"capacitor","confidence":0.9},'
    ' {"kind":"part","text":"labor","confidence":0.9}]'
])
THREAD = {"configurable": {"thread_id": "ui"}}


def run_job(transcript, trade):
    agent = build_agent(DEMO_PERCEPTION(), CATALOG, InMemorySaver())
    cap = Capture(image_paths=["demo.jpg"], transcript=transcript, trade_hint=trade or "Job")
    out = agent.invoke({"capture": cap, "observations": [], "line_items": [],
                        "trace": [], "estimate": None}, THREAD)
    est = out.get("estimate")
    pdf = None
    if est is not None:
        pdf = "/tmp/fieldforge_estimate.pdf"
        estimate_to_pdf(est, pdf)
    return trace_html(out["trace"]), estimate_rows(est), summary_text(est), pdf


with gr.Blocks(title="FieldForge", css=CSS, theme=gr.themes.Soft(
        primary_hue="orange")) as demo:
    gr.HTML('<div class="ff-title">Forge Estimate: AC Unit Repair — 123 Maple St</div>')
    with gr.Row():
        transcript = gr.Textbox(label="Voice note (transcript)", lines=2,
                                placeholder="e.g. replaced the capacitor, one hour labor")
        trade = gr.Textbox(label="Trade", value="hvac")
    run_btn = gr.Button("Forge estimate", variant="primary")
    with gr.Row(equal_height=True):
        with gr.Column(scale=4):
            gr.HTML('<div class="ff-pane-head">⌁ AI Forge</div>')
            trace_out = gr.HTML(trace_html([]))
        with gr.Column(scale=6):
            gr.HTML('<div class="ff-pane-head">Draft Estimate</div>')
            est_table = gr.Dataframe(headers=["Description", "Qty", "Rate", "Amount"],
                                     datatype=["str", "str", "str", "str"],
                                     interactive=True, wrap=True)
            summary = gr.Markdown(summary_text(None))
            pdf_btn = gr.Button("Preview PDF")
    pdf_out = gr.File(label="Estimate PDF")
    with gr.Row():
        lang = gr.Dropdown(["English", "Spanish (Español)", "French (Français)"],
                           value="English", label="Generate Customer Copy")
        gr.Button("Discard Draft")
        gr.Button("Finalize & Send", variant="primary")
    run_btn.click(run_job, [transcript, trade], [trace_out, est_table, summary, pdf_out])

if __name__ == "__main__":
    demo.launch()
```

- [ ] **Step 2: Launch and verify manually**

Run: `python -m fieldforge.app`
Expected: Gradio opens with the dark AI-Forge pane (left) and the editable estimate table (right); clicking "Forge estimate" streams the trace steps, fills the estimate table, shows the subtotal/tax/total line, and produces a downloadable PDF. Verify the total matches line items + 13% tax. (Live token-by-token streaming of the trace is added in the post-core polish; for now the trace renders on completion.)

- [ ] **Step 3: Commit**

```bash
git add fieldforge/app.py
git commit -m "feat: Gradio Workspace wiring the core flow to the design"
```

---

## Task 8: End-to-end core smoke test + README note

**Files:**
- Create: `tests/test_e2e_core.py`, `README.md`

- [ ] **Step 1: Write the end-to-end test**

```python
# tests/test_e2e_core.py
from langgraph.checkpoint.memory import InMemorySaver
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent
from fieldforge.pdf import estimate_to_pdf


def test_capture_to_pdf_end_to_end(tmp_path):
    perception = StubModel(responses=['[{"kind":"part","text":"capacitor","confidence":0.9}]'])
    agent = build_agent(perception, Catalog.from_file("data/sample_catalog.json"), InMemorySaver())
    cfg = {"configurable": {"thread_id": "e2e"}}
    out = agent.invoke({"capture": Capture(image_paths=["a.jpg"], transcript="cap", trade_hint="hvac"),
                        "observations": [], "line_items": [], "trace": [], "estimate": None}, cfg)
    est = out["estimate"]
    assert est is not None and est.total > 0
    pdf = tmp_path / "e2e.pdf"
    estimate_to_pdf(est, str(pdf))
    assert pdf.read_bytes()[:4] == b"%PDF"
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: ALL pass (models, resolver, catalog, tools, agent ×3, pdf, e2e).

- [ ] **Step 3: Write `README.md`**

```markdown
# FieldForge

Capture a job (photos + voice) → a supervised small-model agent forges an itemized estimate. Build Small Hackathon entry. See `docs/superpowers/specs/` and `docs/adr/`.

## Run
```
pip install -e ".[dev]"
python -m fieldforge.app
```

## Test
```
pytest -v
```

Models are stubbed in the core build; real Private/Best stacks wire in via `fieldforge/resolver.py`. Pricing is clearly-labeled sample data.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_core.py README.md
git commit -m "test: end-to-end core smoke test + README"
```

---

## Self-review notes (for the executor)

- **Spec coverage (Irreducible Core):** Capture (T1/T7) · perception (T4) · agent loop + Trace (T5) · Facts-from-Tools via compute/lookup_price (T3/T4/T5) · Agent Pause + resume = the human Interrupt path (T5) · editable/rendered Estimate (T7) · PDF (T6) · two-panel Workspace (T7). Out of core (separate plans): multilingual, memory/Recall, second Mode + JSON, fine-tune, service report, video, FLUX, Modal deployment.
- **Type consistency:** `Capture`, `Observation`, `LineItem` (with `price_source` + `subtotal`), `Estimate` (`subtotal`/`tax`/`total`), `TraceStep` defined in T1 and used unchanged in T4/T5/T6/T7. `StubModel.generate`, `ModelResolver.for_role`, `Catalog.lookup`, tool signatures, `build_agent(perception_model, catalog, checkpointer)`, `estimate_to_pdf(est, path)` consistent across tasks.
- **Inline-edit Interrupt note:** the core ships the *agent-pause* interrupt (T5) as the human-in-the-loop proof; richer inline table editing of line items in the Gradio UI (an Interrupt on an already-drafted item) is the first polish item after the core runs (spec §2.2 / ADR-0007) — keep it small, not a rewrite.
- **LangGraph version caveat:** the interrupt surface (`__interrupt__` key, `Command(resume=...)`) follows the LangChain human-in-the-loop docs; if the installed version differs, adjust the two interrupt assertions in T5 to the actual API and keep the behavior (pause → resume with a value).
