"""Rendering layer for synthetic trade invoice images.

Pipeline:
    job dict  ->  Jinja2 HTML  ->  WeasyPrint PDF  ->  pdf2image PNG  ->  Augraphy PNG bytes

System deps required in the Modal debian_slim image:
    apt: see RENDER_APT_DEPS
    pip: see RENDER_PIP_DEPS

Both lists are consumed by generate.py's Modal image builder — do NOT inline them there.

Degradation severity:
    0.0  = clean (no Augraphy — useful for debug / visual QA)
    0.5  = light (default, recommended for training data)
    1.0  = heavy (max degradation)
"""

from __future__ import annotations

import io
import random
import string
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# Dep manifests — consumed by generate.py's Modal image builder
# ---------------------------------------------------------------------------

RENDER_APT_DEPS: list[str] = [
    # WeasyPrint rendering chain
    "libpango-1.0-0",
    "libpangoft2-1.0-0",
    "libgdk-pixbuf2.0-0",
    "libffi-dev",
    "shared-mime-info",
    "libcairo2",
    "libxml2",
    # pdf2image / poppler
    "poppler-utils",
]

RENDER_PIP_DEPS: list[str] = [
    "weasyprint>=61.0",
    "pdf2image>=1.17.0",
    "augraphy>=8.2.6",
    "Faker>=19.0.0",
    "Jinja2>=3.1.0",
    "Pillow>=10.0.0",
]

# ---------------------------------------------------------------------------
# Template environment
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_TEMPLATE_NAMES: list[str] = [
    "modern_saas",
    "classic_letterhead",
    "bare_bones_table",
    "quickbooks_export",
    "carbon_copy",
    "thermal_narrow",
    "bold_header_contractor",
    "handwritten_fillable",
]


def list_templates() -> list[str]:
    """Return the list of available template names (no .html extension)."""
    return list(_TEMPLATE_NAMES)


# ---------------------------------------------------------------------------
# Fake header data helpers
# ---------------------------------------------------------------------------

_TRADE_COMPANY_WORDS = {
    "hvac": ["Air", "Climate", "Comfort", "Cool", "Breeze", "Thermal"],
    "plumbing": ["Flow", "Pipe", "Stream", "Aqua", "Water", "Drain"],
    "electrical": ["Volt", "Spark", "Power", "Current", "Circuit", "Amp"],
    "roofing": ["Peak", "Roof", "Shield", "Summit", "Cover", "Cap"],
    "carpentry": ["Craft", "Beam", "Wood", "Frame", "Timber", "Joinery"],
    "painting": ["Color", "Coat", "Brush", "Finish", "Hue", "Palette"],
    "landscaping": ["Green", "Lawn", "Garden", "Turf", "Bloom", "Terra"],
    "general": ["Pro", "First", "Premier", "Elite", "Quality", "Precision"],
}

_SUFFIXES = [
    "Services LLC",
    "Contractors Inc.",
    "& Sons",
    "Solutions",
    "Pros",
    "Group",
    "Co.",
    "Enterprises",
]

_CITIES = [
    "Austin, TX",
    "Phoenix, AZ",
    "Tampa, FL",
    "Denver, CO",
    "Nashville, TN",
    "Charlotte, NC",
    "Las Vegas, NV",
    "Raleigh, NC",
    "Columbus, OH",
    "Indianapolis, IN",
]

_STREETS = [
    "Industrial Pkwy",
    "Commerce Dr",
    "Trade Center Blvd",
    "Service Rd",
    "Contractor Way",
    "Business Loop",
]

_CUSTOMER_LAST = [
    "Johnson",
    "Williams",
    "Martinez",
    "Brown",
    "Davis",
    "Garcia",
    "Miller",
    "Wilson",
    "Moore",
    "Taylor",
    "Anderson",
    "Thomas",
]

_CUSTOMER_FIRST = [
    "James",
    "Mary",
    "Robert",
    "Patricia",
    "Michael",
    "Jennifer",
    "Linda",
    "Barbara",
    "Richard",
    "Susan",
    "David",
    "Jessica",
]


def _make_header_context(job: dict, rng: random.Random) -> dict:
    """Generate cosmetic header fields from a seeded RNG — NOT ground truth."""
    trade = job.get("trade", "general").lower()
    words = _TRADE_COMPANY_WORDS.get(trade, _TRADE_COMPANY_WORDS["general"])
    company_name = f"{rng.choice(words)} {rng.choice(_SUFFIXES)}"

    city = rng.choice(_CITIES)
    street_num = rng.randint(100, 9999)
    street = rng.choice(_STREETS)
    company_address = f"{street_num} {street}, {city}"

    area = rng.randint(200, 989)
    n1 = rng.randint(200, 999)
    n2 = rng.randint(1000, 9999)
    company_phone = f"({area}) {n1}-{n2}"
    domain = company_name.split()[0].lower().replace("&", "and")
    company_email = f"info@{domain}contractors.com"

    # Invoice number: letter prefix + digits
    prefix = rng.choice(["INV", "WO", "EST", "SVC"])
    inv_num = f"{prefix}-{rng.randint(1000, 99999):05d}"

    # Dates — roughly realistic (2024-2026 range)
    year = rng.randint(2024, 2026)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    invoice_date = f"{month:02d}/{day:02d}/{year}"
    due_month = month + 1 if month < 12 else 1
    due_year = year if month < 12 else year + 1
    due_date = f"{due_month:02d}/{day:02d}/{due_year}"

    first = rng.choice(_CUSTOMER_FIRST)
    last = rng.choice(_CUSTOMER_LAST)
    customer_name = f"{first} {last}"
    cust_num = rng.randint(100, 9999)
    cust_street = rng.choice(_STREETS)
    customer_address = f"{cust_num} {cust_street}, {city}"

    license_number = "".join(rng.choices(string.ascii_uppercase, k=2)) + str(
        rng.randint(100000, 999999)
    )
    established_year = rng.randint(1978, 2015)

    return {
        "company_name": company_name,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_email": company_email,
        "company_city": city,
        "invoice_number": inv_num,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "customer_name": customer_name,
        "customer_address": customer_address,
        "license_number": license_number,
        "established_year": established_year,
    }


# ---------------------------------------------------------------------------
# Core rendering
# ---------------------------------------------------------------------------


def _render_html(job: dict, template_name: str, seed: int | None = None) -> str:
    """Render job dict to an HTML string via Jinja2. Pure Python, no system deps."""
    if template_name not in _TEMPLATE_NAMES:
        raise ValueError(f"Unknown template {template_name!r}. Available: {_TEMPLATE_NAMES}")
    rng = random.Random(seed)
    context = {**job, **_make_header_context(job, rng)}
    tmpl = _jinja_env.get_template(f"{template_name}.html")
    return tmpl.render(**context)


def render_invoice(
    job: dict,
    template_name: str,
    degradation: float = 0.5,
    seed: int | None = None,
) -> bytes:
    """Render a job dict to PNG image bytes.

    Parameters
    ----------
    job:
        Dict with keys: trade, job_type, line_items, total.
        line_items is a list of {description, quantity, unit, rate, amount}.
    template_name:
        One of the names returned by list_templates().
    degradation:
        0.0 = clean PNG (no Augraphy); 0.5 = light scan/photo look (default);
        1.0 = heavy degradation.
    seed:
        RNG seed for reproducible header data and Augraphy noise. None = random.

    Returns
    -------
    bytes
        PNG image bytes.
    """
    # Late imports so the module stays importable even without system libs
    # (tests exercise the Jinja2 layer directly via _render_html).
    try:
        import weasyprint  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for render_invoice(). "
            "Install RENDER_APT_DEPS + RENDER_PIP_DEPS (see render.py header)."
        ) from exc

    try:
        from pdf2image import convert_from_bytes  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "pdf2image + poppler-utils are required for render_invoice(). "
            "Install RENDER_APT_DEPS + RENDER_PIP_DEPS (see render.py header)."
        ) from exc

    html_str = _render_html(job, template_name, seed=seed)

    # HTML -> PDF (in memory)
    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()

    # PDF -> PIL Image (first page only)
    images = convert_from_bytes(
        pdf_bytes,
        dpi=150,
        first_page=1,
        last_page=1,
        fmt="png",
    )
    pil_img = images[0]

    if degradation <= 0.0:
        # Clean mode: skip Augraphy, return PIL image directly as PNG bytes
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()

    # Apply Augraphy degradation pipeline
    png_bytes = _apply_augraphy(pil_img, degradation=degradation, seed=seed)
    return png_bytes


def _apply_augraphy(pil_img, degradation: float = 0.5, seed: int | None = None) -> bytes:
    """Apply Augraphy scan/photo degradation to a PIL image; return PNG bytes."""
    try:
        import numpy as np  # noqa: PLC0415
        from augraphy import (  # noqa: PLC0415
            AugraphyPipeline,
            BadPhotoCopy,
            DirtyDrum,
            InkBleed,
            LightingGradient,
            LowInkRandomLines,
            NoiseTexturize,
            ShadowCast,
        )
    except ImportError as exc:
        raise ImportError(
            "augraphy + numpy required for degradation. "
            "Install RENDER_PIP_DEPS or set degradation=0.0 for clean mode."
        ) from exc

    import numpy as np  # noqa: PLC0415 (already imported above, needed for type)

    rng_seed = seed if seed is not None else 42

    # Scale severity 0..1 to concrete parameter ranges
    # low = gentle, high = harsh
    d = max(0.0, min(1.0, degradation))

    ink_intensity_range = (max(0, 0.1 - d * 0.05), 0.2 + d * 0.1)
    shadow_intensity = (0.3 + d * 0.3, 0.5 + d * 0.3)

    ink_phase = [
        InkBleed(
            intensity_range=ink_intensity_range,
            p=0.5 + d * 0.3,
        ),
        LowInkRandomLines(
            count_range=(1, max(2, int(4 * d))),
            p=0.3 + d * 0.3,
        ),
    ]

    paper_phase = [
        NoiseTexturize(
            sigma_range=(1, max(2, int(3 * d))),
            turbulence_range=(2, max(3, int(5 * d))),
            p=0.4 + d * 0.3,
        ),
        DirtyDrum(
            line_width_range=(1, max(2, int(3 * d))),
            p=0.3 * d,
        ),
    ]

    post_phase = [
        LightingGradient(
            light_position=None,
            direction=None,
            max_brightness=max(200, int(220 + d * 30)),
            min_brightness=max(80, int(100 - d * 30)),
            mode="gaussian",
            p=0.4 + d * 0.2,
        ),
        ShadowCast(
            shadow_side="bottom",
            shadow_vertices_range=(1, 2),
            shadow_width_range=(0.3, 0.6),
            shadow_height_range=(0.1, 0.3 + d * 0.2),
            shadow_color=(0, 0, 0),
            shadow_opacity_range=shadow_intensity,
            p=0.3 * d,
        ),
        BadPhotoCopy(
            noise_mask=None,
            noise_type=-1,
            noise_side="random",
            noise_iteration=(1, max(2, int(2 * d))),
            noise_size=(1, max(2, int(3 * d))),
            noise_value=(32, max(64, int(128 * d))),
            noise_sparsity=(0.3, 0.6),
            noise_concentration=(0.1, 0.3 + d * 0.2),
            p=0.2 + d * 0.3,
        ),
    ]

    pipeline = AugraphyPipeline(
        ink_phase=ink_phase,
        paper_phase=paper_phase,
        post_phase=post_phase,
        random_seed=rng_seed,
    )

    img_array = np.array(pil_img.convert("RGB"))
    augmented = pipeline(img_array)

    # Convert numpy result back to PNG bytes
    from PIL import Image  # noqa: PLC0415

    result_img = Image.fromarray(augmented)
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    return buf.getvalue()
