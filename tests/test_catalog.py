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


def test_add_makes_an_item_findable():
    cat = Catalog.from_file("data/sample_catalog.json")
    assert cat.lookup("widget") is None
    cat.add("widget", "Custom widget", "ea", 12.5)
    hit = cat.lookup("widget")
    assert hit["rate"] == 12.5 and hit["description"] == "Custom widget"
