"""Assemble grounded synthetic trade-invoice JOBS from the catalog (Facts-from-Tools).

This is the heart of the synthetic-data generator. An LLM never sees a number: code picks
real catalog entries for a realistic job archetype (e.g. "AC capacitor replacement" pulls a
capacitor part + a diagnostic labor line), samples a sane quantity for each entry's unit,
samples a rate UNIFORMLY inside the entry's grounded [price_low, price_high] band, and
computes amount = qty*rate and total = sum(amounts) — all deterministically from a seeded
`random.Random`. The resulting job converts (to_target) into the EXACT scorer/training shape
({"menu":[{"nm","cnt","price"}], "total"}), so the ground truth round-trips through
scorer.parse_items by construction (see test_jobs.py contract test).

JOB_TYPES maps each trade to realistic archetypes; each archetype is a list of 2-6 COMPONENT
SELECTORS. A selector is {"match": <substring(s) required in the catalog description>,
optionally "kind": <"labor"|"part"|"material">, optionally "qty": (lo, hi) or a fixed int}.
Matching is case-insensitive substring containment; ties are broken by the seeded rng so the
same seed always picks the same entry.
"""

import random

from catalog_loader import by_trade

# Quantity ranges per UNIT used when a selector does not override `qty`. Tuples are
# (low, high) inclusive integer ranges; a bare int is a fixed quantity. These keep
# quantities physically sensible: one big part/lot, a few labor hours, tens of feet
# of pipe/wire/gutter, a handful of sheets/squares, a few pounds of refrigerant.
_DEFAULT_QTY_BY_UNIT = {
    "lot": 1,  # flat-rate jobs / whole-task labor: always quantity 1
    "ea": 1,  # a discrete part/fixture: usually 1 (selectors override for fasteners)
    "hr": (1, 4),  # labor by the hour
    "ft": (10, 40),  # pipe, wire, molding, linear-foot labor
    "sq": (1, 4),  # roofing squares (overridden large for reroofs)
    "sheet": (4, 12),  # drywall / decking / sheathing panels
    "lb": (2, 6),  # refrigerant, solder
    "bdft": (6, 30),  # hardwood board feet
}


def _sample_qty(rng: random.Random, unit: str, override) -> int:
    """Sample an integer quantity for a unit, honoring a selector override if present."""
    spec = override if override is not None else _DEFAULT_QTY_BY_UNIT.get(unit, 1)
    if isinstance(spec, int):
        return spec
    lo, hi = spec
    return rng.randint(lo, hi)


def _pick_entry(rng: random.Random, rows: list[dict], selector: dict) -> dict:
    """Pick one catalog row matching a selector's keyword(s) + optional kind.

    `match` may be a string or a list of strings; ALL must appear (case-insensitive)
    in the description. Among all matches the rng picks one deterministically.
    """
    needles = selector["match"]
    if isinstance(needles, str):
        needles = [needles]
    needles = [n.lower() for n in needles]
    kind = selector.get("kind")

    candidates = [
        row
        for row in rows
        if (kind is None or row["kind"] == kind)
        and all(n in row["description"].lower() for n in needles)
    ]
    if not candidates:
        raise LookupError(f"no catalog entry matches selector {selector!r}")
    return rng.choice(candidates)


def assemble_job(catalog: list[dict], trade: str, job_type: str, rng: random.Random) -> dict:
    """Build one grounded job: pick entries, sample qty + rate, compute amounts + total.

    Deterministic given `rng`. Returns:
        {"trade", "job_type", "line_items": [{description, quantity, unit, rate, amount}],
         "total"}
    Raises KeyError for an unknown trade/job_type, LookupError if a selector matches nothing.
    """
    selectors = JOB_TYPES[trade][job_type]  # KeyError on unknown archetype (intended)
    rows = by_trade(catalog, trade)

    line_items = []
    for selector in selectors:
        entry = _pick_entry(rng, rows, selector)
        qty = _sample_qty(rng, entry["unit"], selector.get("qty"))
        rate = round(rng.uniform(entry["price_low"], entry["price_high"]), 2)
        amount = round(qty * rate, 2)
        line_items.append(
            {
                "description": entry["description"],
                "quantity": qty,
                "unit": entry["unit"],
                "rate": rate,
                "amount": amount,
            }
        )

    total = round(sum(li["amount"] for li in line_items), 2)
    return {"trade": trade, "job_type": job_type, "line_items": line_items, "total": total}


def to_target(job: dict) -> dict:
    """Convert a job to the SCORER/training target shape.

    {"menu": [{"nm": <description>, "cnt": <qty>, "price": <amount>}], "total": <total>}.
    Round-trips through scorer.parse_items by construction (price is the line AMOUNT, the
    same number a real receipt prints per line — not the unit rate).
    """
    return {
        "menu": [
            {"nm": li["description"], "cnt": li["quantity"], "price": li["amount"]}
            for li in job["line_items"]
        ],
        "total": job["total"],
    }


# --- realistic long-tail job mix ----------------------------------------------
#
# Real trade businesses run MOSTLY small service calls and repairs, with the occasional
# big install/replacement. We model that with explicit weights: each (trade, job_type)
# carries a weight; small/repair archetypes get large weights, big installs get small
# ones. Trades are sampled in proportion to the sum of their archetype weights, then an
# archetype within the trade in proportion to its weight. Weights are documented inline
# below in JOB_WEIGHTS (higher = more common). Sampling uses the passed seeded rng.


def realistic_job_mix(rng: random.Random) -> tuple[str, str]:
    """Sample a (trade, job_type) with a long-tail distribution (mostly small jobs)."""
    flat = [
        (trade, job_type, weight)
        for trade, types in JOB_WEIGHTS.items()
        for job_type, weight in types.items()
    ]
    population = [(t, j) for (t, j, _w) in flat]
    weights = [w for (_t, _j, w) in flat]
    return rng.choices(population, weights=weights, k=1)[0]


# ==============================================================================
# JOB_TYPES — realistic archetypes per trade. Each is a list of 2-6 component
# selectors. Keywords are chosen to match grounded catalog descriptions.
# ==============================================================================

JOB_TYPES: dict[str, dict[str, list[dict]]] = {
    "hvac": {
        # small repairs / service calls (the bread and butter)
        "ac_capacitor_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "run capacitor", "kind": "part"},
            {"match": "Capacitor replacement", "kind": "labor"},
        ],
        "ac_tuneup": [
            {"match": "tune-up", "kind": "labor"},
            {"match": "pleated air filter", "kind": "part", "qty": (1, 2)},
        ],
        "contactor_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "contactor", "kind": "part"},
            {"match": "Contactor replacement", "kind": "labor"},
        ],
        "thermostat_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "programmable thermostat", "kind": "part"},
            {"match": "Thermostat replacement", "kind": "labor"},
        ],
        "refrigerant_recharge": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "R-410A refrigerant", "kind": "material", "qty": (2, 6)},
            {"match": "leak repair", "kind": "labor"},
        ],
        "blower_motor_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "blower motor", "kind": "part"},
            {"match": "Blower motor replacement", "kind": "labor"},
        ],
        "furnace_ignitor_repair": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "ignitor", "kind": "part"},
            {"match": "ignitor replacement", "kind": "labor"},
        ],
        # big installs (the rare tail)
        "ac_condenser_replacement": [
            {"match": ["Goodman", "condenser unit"], "kind": "part"},
            {"match": "line set", "kind": "material", "qty": (15, 35)},
            {"match": "condenser installation", "kind": "labor"},
            {"match": "R-410A refrigerant", "kind": "material", "qty": (4, 8)},
        ],
        "furnace_replacement": [
            {"match": "gas furnace", "kind": "part"},
            {"match": "Furnace installation", "kind": "labor"},
            {"match": "control board", "kind": "part"},
        ],
        "mini_split_install": [
            {"match": "mini-split heat pump", "kind": "part"},
            {"match": "Mini-split", "kind": "labor"},
            {"match": "line set", "kind": "material", "qty": (10, 25)},
        ],
    },
    "electrical": {
        "outlet_install": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "duplex outlet", "kind": "part"},
            {"match": "outlet installation", "kind": "labor"},
        ],
        "gfci_outlet_install": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "GFCI duplex outlet", "kind": "part"},
            {"match": "GFCI outlet installation", "kind": "labor"},
        ],
        "dimmer_switch_install": [
            {"match": "dimmer switch", "kind": "part"},
            {"match": "Dimmer switch installation", "kind": "labor"},
        ],
        "ceiling_fan_install": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "Ceiling fan installation", "kind": "labor"},
        ],
        "breaker_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "circuit breaker", "kind": "part"},
            {"match": "breaker replacement", "kind": "labor"},
        ],
        "surge_protector_install": [
            {"match": "surge protector", "kind": "part"},
            {"match": "surge protector installation", "kind": "labor"},
        ],
        # big installs (tail)
        "panel_upgrade": [
            {"match": "main breaker load center", "kind": "part"},
            {"match": "panel upgrade", "kind": "labor"},
            {"match": "Romex", "kind": "material", "qty": (40, 120)},
        ],
        "ev_charger_install": [
            {"match": "EVSE Level 2 charger", "kind": "part"},
            {"match": "EV charger Level 2 installation", "kind": "labor"},
            {"match": "Romex", "kind": "material", "qty": (20, 60)},
        ],
        "recessed_lighting": [
            {"match": "Recessed light installation", "kind": "labor", "qty": (3, 8)},
            {"match": "Romex", "kind": "material", "qty": (40, 100)},
            {"match": "dimmer switch", "kind": "part"},
        ],
    },
    "plumbing": {
        "drain_cleaning": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "Drain cleaning (cable snake", "kind": "labor"},
        ],
        "toilet_repair": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "fill valve + flapper kit", "kind": "part"},
            {"match": "Toilet rebuild", "kind": "labor"},
        ],
        "faucet_replacement": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "bathroom faucet", "kind": "part"},
            {"match": "Bathroom faucet replacement", "kind": "labor"},
        ],
        "garbage_disposal_install": [
            {"match": "garbage disposal", "kind": "part"},
            {"match": "Garbage disposal installation", "kind": "labor"},
        ],
        "pipe_leak_repair": [
            {"match": "diagnostic / service call", "kind": "labor"},
            {"match": "copper sweat 90-degree elbow", "kind": "part", "qty": (1, 4)},
            {"match": "Pipe leak repair (exposed copper", "kind": "labor"},
        ],
        "toilet_replacement": [
            {"match": "elongated toilet", "kind": "part"},
            {"match": "wax ring", "kind": "part"},
            {"match": "Toilet replacement", "kind": "labor"},
        ],
        # big installs (tail)
        "water_heater_replacement": [
            {"match": "gas water heater", "kind": "part"},
            {"match": "T&P relief valve", "kind": "part"},
            {"match": "expansion tank", "kind": "part"},
            {"match": "Tank water heater installation", "kind": "labor"},
        ],
        "tankless_water_heater_install": [
            {"match": "tankless gas water heater", "kind": "part"},
            {"match": "Tankless water heater installation", "kind": "labor"},
        ],
        "repipe": [
            {"match": "PEX-A pipe", "kind": "part", "qty": (8, 20)},
            {"match": "push-to-connect elbow", "kind": "part", "qty": (6, 16)},
            {"match": "Whole-house repipe (1-bath", "kind": "labor"},
        ],
    },
    "carpentry": {
        "door_install": [
            {"match": "Prehung interior", "kind": "material"},
            {"match": "door knob set", "kind": "material"},
            {"match": "Interior door install", "kind": "labor"},
        ],
        "baseboard_trim": [
            {"match": "Base molding", "kind": "material", "qty": (40, 120)},
            {"match": "baseboard/door casing install", "kind": "labor", "qty": (40, 120)},
            {"match": "Finish carpenter — general finish work", "kind": "labor"},
        ],
        "closet_shelving": [
            {"match": "Closet shelving installation", "kind": "labor"},
            {"match": "Carpentry helper", "kind": "labor"},
        ],
        "window_replacement": [
            {"match": "replacement window", "kind": "material", "qty": (1, 3)},
            {"match": "Window installation", "kind": "labor", "qty": (1, 3)},
            {"match": "Window trim set", "kind": "material"},  # unit=lot -> qty 1
        ],
        "drywall_repair": [
            {"match": "drywall panel", "kind": "material", "qty": (2, 6)},
            {"match": "joint compound", "kind": "material", "qty": (1, 2)},
            {"match": "Drywall installation", "kind": "labor", "qty": (2, 6)},
        ],
        # big builds (tail)
        "deck_build": [
            {"match": "deck board", "kind": "material", "qty": (20, 60)},
            {"match": "deck post", "kind": "material", "qty": (4, 10)},
            {"match": "Deck build", "kind": "labor", "qty": (120, 320)},
            {"match": "ledger board attachment", "kind": "labor"},
        ],
        "kitchen_cabinets": [
            {"match": "base cabinet", "kind": "material", "qty": (3, 8)},
            {"match": "wall cabinet", "kind": "material", "qty": (3, 8)},
            {"match": "Cabinet installation", "kind": "labor", "qty": (10, 24)},
            {"match": "countertop", "kind": "material", "qty": (10, 24)},
        ],
        "subfloor_install": [
            {"match": "tongue-and-groove OSB subfloor", "kind": "material", "qty": (8, 20)},
            {"match": "Subfloor installation", "kind": "labor", "qty": (120, 320)},
        ],
    },
    "roofing": {
        "roof_repair": [
            {"match": "Emergency roof repair", "kind": "labor"},
            {"match": "architectural shingles — per bundle", "kind": "material", "qty": (1, 4)},
            {"match": "Roofing caulk", "kind": "material", "qty": (1, 3)},
        ],
        "shingle_repair": [
            {"match": "Minor shingle repair", "kind": "labor"},
            {"match": "architectural shingles — per bundle", "kind": "material", "qty": (1, 3)},
        ],
        "pipe_boot_reflash": [
            {"match": "Pipe boot flashing install", "kind": "labor", "qty": (1, 4)},
            {"match": "pipe boot", "kind": "material", "qty": (1, 4)},
        ],
        "gutter_install": [
            {"match": "Gutter installation", "kind": "labor", "qty": (40, 120)},
            {"match": "downspout installation", "kind": "labor", "qty": (15, 50)},
            {
                "match": "K-style, per linear foot (material only)",
                "kind": "material",
                "qty": (40, 120),
            },
        ],
        "gutter_cleaning": [
            {"match": "Gutter cleaning", "kind": "labor"},
            {"match": "Roofing laborer", "kind": "labor"},
        ],
        # big installs (tail)
        "reroof": [
            {"match": "Tear-off / removal", "kind": "labor", "qty": (15, 35)},
            {
                "match": "Timberline HDZ architectural laminated shingles (per square",
                "kind": "material",
                "qty": (15, 35),
            },
            {
                "match": "synthetic roofing underlayment, per square",
                "kind": "material",
                "qty": (15, 35),
            },
            {"match": "architectural shingle installation", "kind": "labor", "qty": (15, 35)},
            {"match": "debris haul-away", "kind": "labor"},
        ],
        "full_reroof_allin": [
            {"match": "Full reroof — tear-off", "kind": "labor", "qty": (15, 35)},
            {"match": "ridge vent installation", "kind": "labor", "qty": (20, 60)},
            {"match": "Drip edge installation", "kind": "labor", "qty": (60, 160)},
        ],
    },
}


# Long-tail weights: small repairs/service calls common (high weight), big installs rare.
# Tuned so realistic_job_mix yields mostly sub-$1k jobs with an occasional large install.
JOB_WEIGHTS: dict[str, dict[str, int]] = {
    "hvac": {
        "ac_capacitor_replacement": 18,
        "ac_tuneup": 16,
        "contactor_replacement": 12,
        "thermostat_replacement": 12,
        "refrigerant_recharge": 10,
        "blower_motor_replacement": 7,
        "furnace_ignitor_repair": 10,
        "ac_condenser_replacement": 2,
        "furnace_replacement": 2,
        "mini_split_install": 1,
    },
    "electrical": {
        "outlet_install": 16,
        "gfci_outlet_install": 14,
        "dimmer_switch_install": 14,
        "ceiling_fan_install": 12,
        "breaker_replacement": 12,
        "surge_protector_install": 8,
        "panel_upgrade": 3,
        "ev_charger_install": 2,
        "recessed_lighting": 4,
    },
    "plumbing": {
        "drain_cleaning": 18,
        "toilet_repair": 16,
        "faucet_replacement": 14,
        "garbage_disposal_install": 10,
        "pipe_leak_repair": 12,
        "toilet_replacement": 8,
        "water_heater_replacement": 4,
        "tankless_water_heater_install": 2,
        "repipe": 1,
    },
    "carpentry": {
        "door_install": 16,
        "baseboard_trim": 12,
        "closet_shelving": 14,
        "window_replacement": 10,
        "drywall_repair": 14,
        "deck_build": 3,
        "kitchen_cabinets": 2,
        "subfloor_install": 4,
    },
    "roofing": {
        "roof_repair": 16,
        "shingle_repair": 16,
        "pipe_boot_reflash": 12,
        "gutter_install": 8,
        "gutter_cleaning": 16,
        "reroof": 2,
        "full_reroof_allin": 1,
    },
}
