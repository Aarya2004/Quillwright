"""Tests for catalog_loader — pure, deterministic catalog access + validation.

The catalog (finetune/synth/catalog/catalog.json) is the grounded source of every
price in the synthetic invoices. These tests pin the loader's contract: it reads the
real 381-row file, filters by trade, and validates the row shape + price invariants
so a malformed catalog fails loudly here instead of producing garbage invoices.
"""

import os

import pytest
from catalog_loader import ALLOWED_TRADES, by_trade, load_catalog, validate_catalog

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog", "catalog.json")


def test_load_catalog_reads_the_real_381_row_file():
    catalog = load_catalog(CATALOG_PATH)
    assert isinstance(catalog, list)
    assert len(catalog) == 381
    assert all(isinstance(row, dict) for row in catalog)


def test_load_catalog_rows_have_the_expected_fields():
    catalog = load_catalog(CATALOG_PATH)
    expected = {"trade", "kind", "description", "unit", "price_low", "price_high", "source"}
    for row in catalog:
        assert expected <= set(row), f"row missing fields: {row}"


def test_by_trade_filters_to_one_trade():
    catalog = load_catalog(CATALOG_PATH)
    hvac = by_trade(catalog, "hvac")
    assert len(hvac) == 72
    assert all(row["trade"] == "hvac" for row in hvac)


def test_by_trade_unknown_trade_returns_empty():
    catalog = load_catalog(CATALOG_PATH)
    assert by_trade(catalog, "landscaping") == []


def test_allowed_trades_is_the_five_trades():
    assert ALLOWED_TRADES == {"carpentry", "electrical", "hvac", "plumbing", "roofing"}


def test_validate_catalog_accepts_the_real_catalog():
    catalog = load_catalog(CATALOG_PATH)
    validate_catalog(catalog)  # must not raise


def test_validate_catalog_rejects_missing_field():
    bad = [{"trade": "hvac", "kind": "labor", "description": "x", "unit": "hr", "price_low": 1.0}]
    with pytest.raises(ValueError, match="price_high"):
        validate_catalog(bad)


def test_validate_catalog_rejects_nonpositive_price():
    bad = [_row(price_low=0.0, price_high=10.0)]
    with pytest.raises(ValueError, match="price"):
        validate_catalog(bad)


def test_validate_catalog_rejects_low_ge_high():
    bad = [_row(price_low=50.0, price_high=50.0)]
    with pytest.raises(ValueError, match="price_low"):
        validate_catalog(bad)


def test_validate_catalog_rejects_unknown_trade():
    bad = [_row(trade="landscaping")]
    with pytest.raises(ValueError, match="trade"):
        validate_catalog(bad)


def _row(**overrides):
    base = {
        "trade": "hvac",
        "kind": "labor",
        "description": "x",
        "unit": "hr",
        "price_low": 10.0,
        "price_high": 20.0,
        "source": "test",
    }
    base.update(overrides)
    return base
