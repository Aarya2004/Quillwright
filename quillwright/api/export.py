"""Export an estimate as machine-readable JSON — the "no lock-in" counterpart to
the PDF. Totals go through the same server-authoritative recalc (Facts-from-Tools),
so the exported numbers match exactly what the customer-facing PDF shows.
"""

from quillwright.api.recalc import recalc_estimate

DISCLAIMER = "AI-generated draft — review before sending. Sample pricing."


def estimate_to_json_payload(rows: list[dict], job_title: str, tax_rate: float) -> dict:
    """Return a self-describing JSON payload for the (possibly edited) estimate."""
    est = recalc_estimate(rows, job_title=job_title, tax_rate=tax_rate)
    return {
        "format": "quillwright.estimate.v1",
        "disclaimer": DISCLAIMER,
        **est,
    }
