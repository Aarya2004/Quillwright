"""Tests for finetune/synth/render.py.

Strategy
--------
The Jinja2 layer (HTML generation) is pure Python — tested fully here.
The PNG rendering chain (WeasyPrint + pdf2image + Augraphy) needs system libs
that may not be present locally; those tests are guarded by pytest.importorskip
so the suite stays green in a plain venv.

Run:
    python -m pytest finetune/synth/test_render.py -v
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Sample job fixture — realistic HVAC invoice
# ---------------------------------------------------------------------------

SAMPLE_JOB: dict = {
    "trade": "hvac",
    "job_type": "repair",
    "line_items": [
        {
            "description": "HVAC diagnostic / service call (first hour)",
            "quantity": 1,
            "unit": "lot",
            "rate": 125.00,
            "amount": 125.00,
        },
        {
            "description": "Genteq 45/5 MFD 440V dual run capacitor (round) 97F9851",
            "quantity": 1,
            "unit": "ea",
            "rate": 28.50,
            "amount": 28.50,
        },
        {
            "description": "Capacitor replacement (part + labor flat rate)",
            "quantity": 1,
            "unit": "lot",
            "rate": 225.00,
            "amount": 225.00,
        },
        {
            "description": "R-410A refrigerant (per pound, contractor billed rate)",
            "quantity": 2.5,
            "unit": "lb",
            "rate": 65.00,
            "amount": 162.50,
        },
    ],
    "total": 541.00,
}

SAMPLE_JOB_PLUMBING: dict = {
    "trade": "plumbing",
    "job_type": "installation",
    "line_items": [
        {
            "description": "Plumber labor (per hour)",
            "quantity": 3,
            "unit": "hr",
            "rate": 110.00,
            "amount": 330.00,
        },
        {
            "description": "1/2 in. copper pipe (per foot)",
            "quantity": 12,
            "unit": "ft",
            "rate": 4.50,
            "amount": 54.00,
        },
    ],
    "total": 384.00,
}


# ---------------------------------------------------------------------------
# list_templates() tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_list():
    from render import list_templates  # noqa: PLC0415

    result = list_templates()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_templates_expected_names():
    from render import list_templates  # noqa: PLC0415

    names = list_templates()
    expected = {
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    }
    assert expected == set(names), f"Missing or extra templates: {set(names) ^ expected}"


def test_list_templates_returns_eight():
    from render import list_templates  # noqa: PLC0415

    assert len(list_templates()) == 8


def test_list_templates_no_extension():
    from render import list_templates  # noqa: PLC0415

    for name in list_templates():
        assert not name.endswith(".html"), f"Template name should not have .html: {name}"


# ---------------------------------------------------------------------------
# Template file existence tests
# ---------------------------------------------------------------------------


def test_all_template_files_exist():
    """Each name in list_templates() must correspond to a real .html file."""
    from pathlib import Path  # noqa: PLC0415

    from render import list_templates  # noqa: PLC0415

    templates_dir = Path(__file__).parent / "templates"
    for name in list_templates():
        path = templates_dir / f"{name}.html"
        assert path.exists(), f"Missing template file: {path}"
        assert path.stat().st_size > 200, f"Template file suspiciously small: {path}"


# ---------------------------------------------------------------------------
# Jinja2 render tests — pure Python, no system deps
# ---------------------------------------------------------------------------


def _render_to_html(job: dict, template_name: str, seed: int = 0) -> str:
    """Helper that calls the internal _render_html function."""
    from render import _render_html  # noqa: PLC0415

    return _render_html(job, template_name, seed=seed)


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_renders_non_empty_html(template_name: str):
    html = _render_to_html(SAMPLE_JOB, template_name, seed=42)
    assert isinstance(html, str)
    assert len(html) > 500, f"{template_name}: rendered HTML is suspiciously short"


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_contains_all_line_item_descriptions(template_name: str):
    """Every line-item description must appear in the rendered HTML."""
    html = _render_to_html(SAMPLE_JOB, template_name, seed=42)
    for item in SAMPLE_JOB["line_items"]:
        # Jinja2 autoescape will HTML-escape special chars — check plain substring
        # for descriptions that have no special chars (all catalog items are safe)
        assert item["description"] in html, (
            f"{template_name}: description not found in HTML: {item['description']!r}"
        )


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_contains_total(template_name: str):
    """The grand total must appear somewhere in the rendered HTML."""
    html = _render_to_html(SAMPLE_JOB, template_name, seed=42)
    # total is 541.00 — rendered as $541.00
    assert "541.00" in html, f"{template_name}: total '541.00' not found in rendered HTML"


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_contains_rates(template_name: str):
    """Each line-item rate must appear in the rendered HTML."""
    html = _render_to_html(SAMPLE_JOB, template_name, seed=42)
    for item in SAMPLE_JOB["line_items"]:
        rate_str = f"{item['rate']:.2f}"
        assert rate_str in html, f"{template_name}: rate '{rate_str}' not found in HTML"


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_seeded_render_is_deterministic(template_name: str):
    """Same seed must produce identical HTML (reproducible renders)."""
    html1 = _render_to_html(SAMPLE_JOB, template_name, seed=7)
    html2 = _render_to_html(SAMPLE_JOB, template_name, seed=7)
    assert html1 == html2, f"{template_name}: seeded render is not deterministic"


@pytest.mark.parametrize(
    "template_name",
    [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ],
)
def test_template_different_seeds_differ(template_name: str):
    """Different seeds should produce different header data (invoice#, company)."""
    html1 = _render_to_html(SAMPLE_JOB, template_name, seed=1)
    html2 = _render_to_html(SAMPLE_JOB, template_name, seed=999)
    assert html1 != html2, f"{template_name}: different seeds produced identical output"


def test_template_renders_plumbing_job():
    """Non-HVAC trade renders correctly with all items present."""
    html = _render_to_html(SAMPLE_JOB_PLUMBING, "modern_saas", seed=1)
    assert "Plumber labor (per hour)" in html
    assert "1/2 in. copper pipe (per foot)" in html
    assert "384.00" in html


def test_unknown_template_raises_value_error():
    from render import _render_html  # noqa: PLC0415

    with pytest.raises(ValueError, match="Unknown template"):
        _render_html(SAMPLE_JOB, "does_not_exist", seed=0)


def test_template_has_html_doctype():
    """Each template must be a valid HTML document (starts with DOCTYPE or html tag)."""
    for name in [
        "modern_saas",
        "classic_letterhead",
        "bare_bones_table",
        "quickbooks_export",
        "carbon_copy",
        "thermal_narrow",
        "bold_header_contractor",
        "handwritten_fillable",
    ]:
        html = _render_to_html(SAMPLE_JOB, name, seed=0)
        lower = html.lstrip().lower()
        assert lower.startswith("<!doctype") or lower.startswith("<html"), (
            f"{name}: rendered HTML doesn't start with DOCTYPE or <html>"
        )


# ---------------------------------------------------------------------------
# Module-level constants tests
# ---------------------------------------------------------------------------


def test_render_pip_deps_is_list():
    from render import RENDER_PIP_DEPS  # noqa: PLC0415

    assert isinstance(RENDER_PIP_DEPS, list)
    assert len(RENDER_PIP_DEPS) >= 4


def test_render_apt_deps_is_list():
    from render import RENDER_APT_DEPS  # noqa: PLC0415

    assert isinstance(RENDER_APT_DEPS, list)
    assert len(RENDER_APT_DEPS) >= 3


def test_render_pip_deps_includes_key_packages():
    from render import RENDER_PIP_DEPS  # noqa: PLC0415

    joined = " ".join(RENDER_PIP_DEPS).lower()
    assert "weasyprint" in joined
    assert "augraphy" in joined
    assert "jinja2" in joined


def test_render_apt_deps_includes_poppler():
    from render import RENDER_APT_DEPS  # noqa: PLC0415

    joined = " ".join(RENDER_APT_DEPS).lower()
    assert "poppler" in joined


def test_render_apt_deps_includes_pango():
    from render import RENDER_APT_DEPS  # noqa: PLC0415

    joined = " ".join(RENDER_APT_DEPS).lower()
    assert "pango" in joined


# ---------------------------------------------------------------------------
# PNG render tests — guarded by importorskip (needs system libs)
# ---------------------------------------------------------------------------


def test_render_invoice_clean_mode_returns_png_bytes():
    """Clean-mode render (no Augraphy) — skipped if WeasyPrint/pdf2image absent."""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pdf2image")

    from render import render_invoice  # noqa: PLC0415

    png = render_invoice(SAMPLE_JOB, "bare_bones_table", degradation=0.0, seed=42)
    assert isinstance(png, bytes)
    # PNG magic bytes: \x89PNG
    assert png[:4] == b"\x89PNG", "Output is not a valid PNG"
    assert len(png) > 10_000, "PNG is suspiciously small (< 10 KB)"


def test_render_invoice_with_degradation_returns_png_bytes():
    """Degraded render — skipped if WeasyPrint/pdf2image/augraphy absent."""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pdf2image")
    pytest.importorskip("augraphy")

    from render import render_invoice  # noqa: PLC0415

    png = render_invoice(SAMPLE_JOB, "modern_saas", degradation=0.5, seed=42)
    assert isinstance(png, bytes)
    assert png[:4] == b"\x89PNG"
    assert len(png) > 10_000


def test_render_invoice_all_templates_clean():
    """Smoke-render all templates in clean mode — skipped if libs absent."""
    pytest.importorskip("weasyprint")
    pytest.importorskip("pdf2image")

    from render import list_templates, render_invoice  # noqa: PLC0415

    for name in list_templates():
        png = render_invoice(SAMPLE_JOB, name, degradation=0.0, seed=0)
        assert png[:4] == b"\x89PNG", f"{name}: output is not a PNG"
