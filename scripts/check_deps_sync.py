"""Fail if pyproject.toml [project.dependencies] and requirements.txt drift.

The HF Space installs from requirements.txt; dev/tests install from pyproject.
They are hand-kept mirrors of the *core* runtime deps — nothing enforced the
match, which once left `requests` undeclared in pyproject (ADR-0012). This is the
hard gate the PostToolUse reminder hook can only nudge toward: run in CI and
locally, exit non-zero on any mismatch.

Scope: only pyproject's core [project.dependencies] is compared. The optional
extras ([project.optional-dependencies]: embed, audio) are deliberately NOT in
requirements.txt (stub-mode Space has no torch) and are excluded here.

Comparison is exact on the normalized requirement string (name + version spec,
lowercased, whitespace-stripped), so `requests>=2.31` must appear verbatim in
both. Run: `python scripts/check_deps_sync.py`
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"


def _normalize(req: str) -> str:
    """Canonical form for comparison: drop whitespace, lowercase the package name.

    Version specifiers stay as written (they must match verbatim across files).
    """
    return req.replace(" ", "").strip().lower()


def _pyproject_core_deps() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data.get("project", {}).get("dependencies", [])
    return {_normalize(d) for d in deps}


def _requirements_deps() -> set[str]:
    deps = set()
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        deps.add(_normalize(line))
    return deps


def main() -> int:
    pyproject = _pyproject_core_deps()
    requirements = _requirements_deps()

    only_pyproject = sorted(pyproject - requirements)
    only_requirements = sorted(requirements - pyproject)

    if not only_pyproject and not only_requirements:
        print("✓ pyproject.toml [project.dependencies] and requirements.txt are in sync.")
        return 0

    print("✗ Dependency lists have drifted:\n")
    if only_pyproject:
        print("  In pyproject.toml [project.dependencies] but NOT requirements.txt:")
        for d in only_pyproject:
            print(f"    - {d}")
    if only_requirements:
        print("  In requirements.txt but NOT pyproject.toml [project.dependencies]:")
        for d in only_requirements:
            print(f"    - {d}")
    print(
        "\nThese two lists are hand-kept mirrors of the core runtime deps. Add the "
        "missing entry to whichever file lacks it (optional extras like embed/audio "
        "are intentionally pyproject-only — don't add those to requirements.txt)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
