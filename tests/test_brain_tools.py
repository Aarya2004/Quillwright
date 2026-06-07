from fieldforge.brain_tools import BRAIN_TOOLS, dispatch
from fieldforge.catalog import Catalog
from fieldforge.models import LineItem

CAT = Catalog.from_file("data/sample_catalog.json")


def test_brain_tools_schema_exposes_add_and_finish():
    names = {t["function"]["name"] for t in BRAIN_TOOLS}
    assert names == {"add_priced_item", "finish"}


def test_dispatch_add_priced_item_hit_returns_line_item():
    result = dispatch("add_priced_item", {"item": "capacitor"}, CAT)
    assert result["status"] == "added"
    assert isinstance(result["line_item"], LineItem)
    assert result["line_item"].rate == 24.0
    assert result["line_item"].price_source == "catalog"


def test_dispatch_add_priced_item_miss_signals_need_price():
    result = dispatch("add_priced_item", {"item": "unobtainium"}, CAT)
    assert result["status"] == "need_price"
    assert result["item"] == "unobtainium"


def test_dispatch_finish_signals_done():
    assert dispatch("finish", {}, CAT)["status"] == "done"


def test_dispatch_unknown_tool_returns_error():
    assert dispatch("bogus", {}, CAT)["status"] == "error"
