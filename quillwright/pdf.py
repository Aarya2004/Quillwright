from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from quillwright.models import Estimate


def estimate_to_pdf(est: Estimate, path: str) -> None:
    c = canvas.Canvas(path, pagesize=LETTER)
    width, height = LETTER
    y = height - inch
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, f"Estimate — {est.job_title}")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(inch, y - 14, "AI-generated draft — review before sending. Sample pricing.")
    y -= 48
    c.setFont("Helvetica-Bold", 10)
    c.drawString(inch, y, "Description")
    c.drawString(4.2 * inch, y, "Qty")
    c.drawString(4.9 * inch, y, "Rate")
    c.drawString(5.9 * inch, y, "Subtotal")
    y -= 16
    c.setFont("Helvetica", 10)
    for li in est.line_items:
        c.drawString(inch, y, li.description[:40])
        c.drawString(4.2 * inch, y, f"{li.quantity:g} {li.unit}")
        c.drawString(4.9 * inch, y, f"${li.rate:.2f}")
        c.drawString(5.9 * inch, y, f"${li.subtotal:.2f}")
        y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(4.9 * inch, y, "Subtotal:")
    c.drawString(5.9 * inch, y, f"${est.subtotal:.2f}")
    y -= 14
    c.drawString(4.9 * inch, y, f"Tax ({est.tax_rate:.0%}):")
    c.drawString(5.9 * inch, y, f"${est.tax:.2f}")
    y -= 14
    c.drawString(4.9 * inch, y, "Total:")
    c.drawString(5.9 * inch, y, f"${est.total:.2f}")
    c.showPage()
    c.save()
