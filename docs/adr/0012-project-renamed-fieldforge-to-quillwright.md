# Project renamed: FieldForge → Quillwright

The project was renamed from **FieldForge** to **Quillwright** (tagline: _"Tell it
about the job. Quillwright drafts the estimate."_). This ADR exists so future sessions
are not confused by the name mismatch that the rename deliberately left in place.

## What was renamed

Only **live, user-facing branding** was changed to Quillwright:

- `README.md` title/copy, `Dockerfile` header comment, `quillwright/theme.css` header.
- `package.json` / `package-lock.json` package name (`fieldforge-web` → `quillwright-web`).
- The Python package directory was already `quillwright/`.
- HF Space `short_description` / branding assets (favicons, logos) under `quillwright/web/img/`.

## What was deliberately NOT renamed (and why)

- **The `FF_` environment-variable prefix** (`FF_REAL_MODELS`, `FF_BACKEND`,
  `FF_MODAL_BRAIN_URL`, `FF_MODAL_PARSE_URL`, …) stays as-is across ~18 code files.
  Renaming to `QW_` would break every existing `.env` and any deployed HF Space /
  Modal secret until re-set — risk not worth it mid-build. **These are the same vars
  documented in the README; `FF` no longer stands for FieldForge, treat it as an
  opaque prefix.**
- **The git branch `design/fieldforge`** keeps its name; renaming a shared branch is a
  guarded action and offers no value.
- **Historical prose in earlier ADRs (0001, 0003, 0010, …), `docs/research/`, plans,
  and `docs/PROGRESS.md`** still says "FieldForge". ADRs are immutable decision records
  describing what was named at the time; rewriting them would falsify the history. Read
  "FieldForge" in any pre-2026-06-11 document as "Quillwright".

## Consequence

The canonical product name is **Quillwright** everywhere a human sees it. The `FF_`
prefix and the `design/fieldforge` branch are the two intentional leftovers — they are
not bugs or oversights, and should not be "fixed" without a deliberate reason.
