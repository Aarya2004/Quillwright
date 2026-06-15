from quillwright.catalog import Catalog
from quillwright.resolver import StubModel
from quillwright.tools import compute, lookup_price, perceive, draft_line_item, flag_for_human
from quillwright.models import Observation, LineItem


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


def test_perceive_extracts_json_from_markdown_fence_with_prose():
    # MiniCPM-V often wraps the array in a ```json fence with a prose preamble — the
    # real cause of "found 0 observations". The parser must dig the array out.
    raw = (
        "Based on my analysis, here is the requested information:\n\n"
        "```json\n"
        '[{"kind":"equipment","text":"Carrier AC unit"},'
        '{"kind":"part","text":"dual run capacitor"}]\n'
        "```\n"
    )
    obs = perceive("/tmp/a.jpg", StubModel(responses=[raw]))
    assert [o.text for o in obs] == ["Carrier AC unit", "dual run capacitor"]
    assert obs[1].confidence == 1.0  # missing confidence defaults, doesn't crash


def test_perceive_skips_bad_rows_keeps_good_ones():
    raw = '[{"kind":"part","text":"capacitor"},{"kind":"NONSENSE","text":"x"}]'
    obs = perceive("/tmp/a.jpg", StubModel(responses=[raw]))
    assert [o.text for o in obs] == ["capacitor"]  # bad-kind row dropped, not a crash


def test_perceive_returns_empty_on_pure_prose():
    obs = perceive("/tmp/a.jpg", StubModel(responses=["I see an air conditioner."]))
    assert obs == []  # no array at all → empty, never an exception


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
