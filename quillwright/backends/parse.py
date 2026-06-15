"""ParseModel: the Document Capture client (ADR-0011), backed by Nemotron Parse on Modal.

Parse is the Extraction Model Role (ADR-0009). It is VISUAL, so it does not fit the
vLLM OpenAI route the brain uses — it has its own Modal endpoint (modal_parse_app.py)
that POSTs a base64 image and returns structured blocks [{class, bbox, text}], having
already run the model's repo-shipped postprocessing server-side.

This client is the on-device half: it turns those blocks into the two things the
Estimate pipeline understands, per ADR-0011 decision C —

  - a priced table row  -> ProposedLineItem  (human confirms the price via Agent Pause)
  - everything else      -> Observation(kind="text")  (flows straight through)

The document is the *source*, but any price it read is *proposed*, never a fact: the
human gates every customer-facing number (Facts-from-Tools, ADR-0004).

The base URL (printed by `modal deploy modal_parse_app.py`) comes from FF_MODAL_PARSE_URL.
"""

import base64
import os
import re

import requests

from quillwright.models import Observation, ProposedLineItem

# Parse's table content arrives as markdown. A money cell looks like "$42.50",
# "$1,250.00", or "42.50" — capture the numeric value, tolerating $ and thousands commas.
_MONEY = re.compile(r"\$?\s*([\d,]+\.\d{1,2}|\d[\d,]*)")
# A leading integer/decimal in a cell is the quantity ("2", "4", "1.5").
_QTY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")


class ParseModel:
    name = "nemotron-parse-v1.2"

    def __init__(self, base_url: str | None = None, timeout: float = 180.0):
        self._base = (base_url or os.environ.get("FF_MODAL_PARSE_URL", "")).rstrip("/")
        if not self._base:
            raise RuntimeError(
                "FF_MODAL_PARSE_URL is not set — deploy modal_parse_app.py and export "
                "the URL it prints (see backends/modal_parse_app.py)."
            )
        self._timeout = timeout

    def parse_document(self, image_path: str) -> tuple[list[Observation], list[ProposedLineItem]]:
        """Read a document image; return (observations, proposed_line_items)."""
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        resp = requests.post(f"{self._base}/parse", json={"image": b64}, timeout=self._timeout)
        resp.raise_for_status()
        blocks = resp.json().get("blocks", [])
        return blocks_to_pipeline(blocks)


def blocks_to_pipeline(
    blocks: list[dict],
) -> tuple[list[Observation], list[ProposedLineItem]]:
    """Split Parse blocks into Observations + Proposed Line Items (ADR-0011).

    Pure function (no network) so it can be unit-tested against real Parse output.
    Table blocks become priced ProposedLineItems where a price is present; their
    non-priced rows and every non-table block become text Observations.
    """
    observations: list[Observation] = []
    proposed: list[ProposedLineItem] = []

    for block in blocks:
        cls = block.get("class", "")
        text = (block.get("text") or "").strip()
        if not text:
            continue
        if cls == "Table":
            rows_obs, rows_items = _table_to_items(text)
            observations.extend(rows_obs)
            proposed.extend(rows_items)
        else:
            observations.append(Observation(kind="text", text=text))
    return observations, proposed


def _table_to_items(
    table_md: str,
) -> tuple[list[Observation], list[ProposedLineItem]]:
    """Parse a markdown table into priced line items, gating on a real price.

    A row with a money cell -> ProposedLineItem (description = its longest text
    cell, quantity from a bare-number cell if present, rate from the price).
    A row with no price falls back to an Observation so nothing is silently dropped.
    """
    observations: list[Observation] = []
    proposed: list[ProposedLineItem] = []

    for line in table_md.splitlines():
        line = line.strip()
        if not line or set(line) <= {"|", "-", " ", ":"}:
            continue  # blank or the header separator row (|---|---|)
        cells = [c.strip() for c in line.strip("|").split("|")]
        cells = [c for c in cells if c != ""]
        if not cells:
            continue

        price = _row_price(cells)
        if price is None:
            observations.append(Observation(kind="text", text=" ".join(cells)))
            continue

        # Skip a header row that happens to contain the literal word "price" but no
        # numeric description (e.g. "| Item | Qty | Price |" has no money cell, so it
        # already fell through above — this guards a row that is only labels).
        description = _row_description(cells)
        if not description:
            observations.append(Observation(kind="text", text=" ".join(cells)))
            continue

        proposed.append(
            ProposedLineItem(
                description=description,
                quantity=_row_quantity(cells),
                rate=price,
                source_text=" ".join(cells),
            )
        )
    return observations, proposed


def _row_price(cells: list[str]) -> float | None:
    """The price of a row = the money value in its last cell that has one.

    Scanning right-to-left picks the line *total* / unit price over an earlier
    quantity that also matches the number pattern.
    """
    for cell in reversed(cells):
        if "$" in cell or "." in cell:
            m = _MONEY.search(cell)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def _row_quantity(cells: list[str]) -> float:
    """A standalone integer/decimal cell is the quantity; default 1."""
    for cell in cells:
        m = _QTY.match(cell)
        if m:
            return float(m.group(1))
    return 1.0


def _row_description(cells: list[str]) -> str:
    """The description is the longest cell that is neither a price nor a bare number."""
    candidates = [
        c for c in cells if not _QTY.match(c) and "$" not in c and not _MONEY.fullmatch(c)
    ]
    return max(candidates, key=len) if candidates else ""
