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
    model = StubModel(responses=['[{"kind":"part","text":"dual run capacitor","confidence":0.8}]'])
    obs = perceive("/tmp/a.jpg", model)
    assert len(obs) == 1 and isinstance(obs[0], Observation) and obs[0].kind == "part"


def test_perceive_passes_image_path_to_vision_capable_model():
    seen = {}

    class VisionStub:
        name = "vision"

        def generate(self, prompt, image_path=None):
            seen["image_path"] = image_path
            return "[]"

    perceive("/tmp/unit.png", VisionStub())
    assert seen["image_path"] == "/tmp/unit.png"


def test_draft_line_item_marks_source_and_computes_subtotal():
    item = draft_line_item("Capacitor", qty=2, unit="ea", rate=24.0, source="catalog")
    assert isinstance(item, LineItem) and item.subtotal == 48.0 and item.price_source == "catalog"


def test_flag_for_human_returns_pause_payload():
    payload = flag_for_human("No price for 'unobtainium'")
    assert payload["pause"] is True and "unobtainium" in payload["reason"]
