"""Tests for jobs.py — the deterministic, code-owned number path (Facts-from-Tools).

Every price/quantity/total here is computed by code from the grounded catalog with a
SEEDED rng — no LLM ever touches a number. These tests pin the contract that makes the
synthetic data trustworthy ground truth:
  - each job has 2-6 line items
  - arithmetic is exact: amount == round(qty*rate, 2), total == round(sum(amounts), 2)
  - quantities are sane for the unit (1 big part, a few labor hours, tens of feet, ...)
  - identical seed -> identical job (reproducible datasets)
  - to_target round-trips through the REAL scorer.parse_items (train/eval same shape)
  - realistic_job_mix is long-tailed (mostly small jobs), not uniform
"""

import json
import random

import pytest
from catalog_loader import load_catalog
from jobs import (
    JOB_TYPES,
    assemble_job,
    realistic_job_mix,
    to_target,
)

# real scorer (finetune/ is on sys.path via conftest.py)
from scorer import parse_items  # noqa: E402

import os

CATALOG = load_catalog(os.path.join(os.path.dirname(__file__), "catalog", "catalog.json"))


def _all_job_types():
    for trade, types in JOB_TYPES.items():
        for job_type in types:
            yield trade, job_type


# --- JOB_TYPES structure -------------------------------------------------------


def test_job_types_cover_all_five_trades():
    assert set(JOB_TYPES) == {"carpentry", "electrical", "hvac", "plumbing", "roofing"}


def test_every_job_type_has_2_to_6_component_selectors():
    for trade, job_type in _all_job_types():
        selectors = JOB_TYPES[trade][job_type]
        assert 2 <= len(selectors) <= 6, f"{trade}/{job_type} has {len(selectors)} selectors"


# --- assemble_job: shape + arithmetic -----------------------------------------


def test_assemble_job_every_archetype_produces_2_to_6_items():
    for trade, job_type in _all_job_types():
        job = assemble_job(CATALOG, trade, job_type, random.Random(0))
        assert 2 <= len(job["line_items"]) <= 6, f"{trade}/{job_type}: {len(job['line_items'])}"
        assert job["trade"] == trade
        assert job["job_type"] == job_type


def test_assemble_job_line_item_arithmetic_is_exact():
    for trade, job_type in _all_job_types():
        job = assemble_job(CATALOG, trade, job_type, random.Random(7))
        for li in job["line_items"]:
            assert li["amount"] == round(li["quantity"] * li["rate"], 2), li
            assert {"description", "quantity", "unit", "rate", "amount"} <= set(li)


def test_assemble_job_total_is_sum_of_amounts():
    for trade, job_type in _all_job_types():
        job = assemble_job(CATALOG, trade, job_type, random.Random(11))
        assert job["total"] == round(sum(li["amount"] for li in job["line_items"]), 2)


def test_assemble_job_rate_is_within_catalog_band():
    # rates are sampled uniformly within [price_low, price_high] of the picked entry.
    by_desc = {r["description"]: r for r in CATALOG}
    for trade, job_type in _all_job_types():
        job = assemble_job(CATALOG, trade, job_type, random.Random(3))
        for li in job["line_items"]:
            entry = by_desc[li["description"]]
            assert entry["price_low"] <= li["rate"] <= entry["price_high"], li


def test_assemble_job_quantities_are_sane_per_unit():
    # qty must respect the unit: 1 for big single parts/lots, small for hours, tens for ft.
    for trade, job_type in _all_job_types():
        for seed in range(5):
            job = assemble_job(CATALOG, trade, job_type, random.Random(seed))
            for li in job["line_items"]:
                q, unit = li["quantity"], li["unit"]
                assert q > 0, li
                if unit in ("lot",):
                    assert q == 1, li
                if unit == "hr":
                    assert 1 <= q <= 8, li
                if unit == "ft":
                    # ft covers both linear feet (pipe/wire/gutter) and per-sq-ft
                    # area labor (deck/subfloor build) — a deck can be a few hundred sq ft.
                    assert 1 <= q <= 400, li
                if unit == "sq":
                    assert 1 <= q <= 50, li
                if unit == "lb":
                    assert 1 <= q <= 12, li


def test_assemble_job_is_deterministic_under_fixed_seed():
    for trade, job_type in _all_job_types():
        a = assemble_job(CATALOG, trade, job_type, random.Random(42))
        b = assemble_job(CATALOG, trade, job_type, random.Random(42))
        assert a == b, f"{trade}/{job_type} not deterministic"


def test_assemble_job_different_seeds_can_differ():
    # not a hard guarantee per archetype, but across the whole set seeds must matter.
    jobs_seed0 = [assemble_job(CATALOG, t, j, random.Random(0)) for t, j in _all_job_types()]
    jobs_seed1 = [assemble_job(CATALOG, t, j, random.Random(1)) for t, j in _all_job_types()]
    assert jobs_seed0 != jobs_seed1


def test_assemble_job_rejects_unknown_archetype():
    with pytest.raises(KeyError):
        assemble_job(CATALOG, "hvac", "not_a_real_job", random.Random(0))


# --- to_target: scorer round-trip CONTRACT ------------------------------------


def test_to_target_has_scorer_shape():
    job = assemble_job(CATALOG, "hvac", "ac_capacitor_replacement", random.Random(0))
    target = to_target(job)
    assert set(target) == {"menu", "total"}
    assert isinstance(target["menu"], list)
    for m in target["menu"]:
        assert set(m) == {"nm", "cnt", "price"}


def test_to_target_round_trips_through_scorer():
    # The deliverable contract: scorer.parse_items(json.dumps(to_target(job))) must
    # recover exactly the job's items (name, qty, amount-as-price).
    for trade, job_type in _all_job_types():
        job = assemble_job(CATALOG, trade, job_type, random.Random(5))
        target = to_target(job)
        parsed = parse_items(json.dumps(target))

        expected = [
            {
                "name": li["description"].strip().lower(),
                "qty": li["quantity"],
                "price": li["amount"],
            }
            for li in job["line_items"]
        ]
        # parse_items lowercases + collapses whitespace; normalize expected the same way.
        import re

        for e in expected:
            e["name"] = re.sub(r"\s+", " ", e["name"]).strip()
        assert parsed == expected, f"{trade}/{job_type} did not round-trip"


# --- realistic_job_mix: long-tail distribution --------------------------------


def test_realistic_job_mix_returns_valid_trade_and_job_type():
    rng = random.Random(0)
    for _ in range(50):
        trade, job_type = realistic_job_mix(rng)
        assert trade in JOB_TYPES
        assert job_type in JOB_TYPES[trade]


def test_realistic_job_mix_is_deterministic_under_seed():
    a = [realistic_job_mix(random.Random(123)) for _ in range(1)]
    b = [realistic_job_mix(random.Random(123)) for _ in range(1)]
    assert a == b


def test_realistic_job_mix_skews_small():
    # Long tail: small service calls / repairs should dominate big installs.
    # We classify by total dollar value and assert small jobs are the majority.
    rng = random.Random(2024)
    smalls = bigs = 0
    for _ in range(2000):
        trade, job_type = realistic_job_mix(rng)
        job = assemble_job(CATALOG, trade, job_type, rng)
        if job["total"] < 1000:
            smalls += 1
        elif job["total"] > 5000:
            bigs += 1
    # Mostly small: small jobs should massively outnumber the big-install tail.
    assert smalls > bigs * 3, f"not long-tailed: smalls={smalls} bigs={bigs}"
