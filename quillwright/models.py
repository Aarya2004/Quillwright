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
    # "document" = a price Parse read from a Document Capture that the human has
    # confirmed verbatim through the Agent Pause (ADR-0011). The document is the
    # source, but the number is still user-gated — it never enters an Estimate
    # straight from the model.
    price_source: Literal["catalog", "user", "computed", "document"] = "catalog"

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.rate, 2)


class ProposedLineItem(BaseModel):
    """A priced row Parse read from a Document Capture, awaiting human confirmation.

    Not an Estimate line yet: per Facts-from-Tools (ADR-0004) + ADR-0011, a price
    a model read off a document is *proposed*, not a fact. The human confirms or
    edits it via the Agent Pause; on confirm it becomes a LineItem with
    price_source="document". `source_text` is the raw cell the price came from, so
    the human can spot an OCR slip (e.g. "$42.50" misread as "$425.0").
    """

    description: str
    quantity: float = 1.0
    unit: str = "ea"
    rate: float
    source_text: str = ""


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
    status: Literal["ok", "active", "paused", "error"] = "ok"
