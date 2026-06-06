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
    status: Literal["ok", "active", "paused", "error"] = "ok"
