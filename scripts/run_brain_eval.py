"""Run the brain over the eval set and print accuracy. Requires FF_REAL_MODELS=1 + Ollama.

Usage: FF_REAL_MODELS=1 .venv/bin/python scripts/run_brain_eval.py
"""

import sys

from fieldforge.brain_eval import load_cases, score_case
from fieldforge.brain_loop import run_brain
from fieldforge.catalog import Catalog
from fieldforge.resolver import ModelResolver


def main():
    cases = load_cases("data/brain_evalset.json")
    catalog = Catalog.from_file("data/sample_catalog.json")
    brain = ModelResolver(mode="private", backend="ollama").for_role("brain")
    print(f"Running {len(cases)} cases against {brain.name}\n")

    f1s, qtys = [], []
    for i, case in enumerate(cases, 1):
        # fresh catalog per case so user-priced items don't leak across cases
        cat = Catalog.from_file("data/sample_catalog.json")
        items, _trace, pause = run_brain(
            brain, cat, observations_text=case["transcript"], transcript=case["transcript"]
        )
        produced = [{"description": li.description, "quantity": li.quantity} for li in items]
        s = score_case(produced, case["expected"])
        f1s.append(s["item_f1"])
        qtys.append(s["qty_accuracy"])
        flag = "" if (s["item_f1"] == 1.0 and s["qty_accuracy"] == 1.0) else "  <-- imperfect"
        print(f"{i:2}. f1={s['item_f1']:.2f} qty={s['qty_accuracy']:.2f}  {case['transcript'][:55]}{flag}")

    print(f"\nMean item F1:       {sum(f1s) / len(f1s):.3f}")
    print(f"Mean qty accuracy:  {sum(qtys) / len(qtys):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
