from fieldforge.models import Estimate, TraceStep

# Status drives the icon: done -> check, active -> pulsing dot + cursor, error -> warning.
def _step_html(s: TraceStep) -> str:
    badge = f'<span class="ff-badge">{s.model}</span>' if s.model else ""
    if s.status == "active":
        marker = '<span class="ff-dot"></span>'
        cursor = '<span class="terminal-cursor"></span>'
    elif s.status == "error":
        marker = '<span class="material-symbols-outlined ff-err">error</span>'
        cursor = ""
    else:
        marker = '<span class="material-symbols-outlined ff-ok">check_circle</span>'
        cursor = ""
    return (f'<div class="ff-step">{marker}'
            f'<div class="ff-step-body"><p>{s.action}: {s.detail}{cursor}</p>{badge}</div></div>')


def trace_html(steps: list[TraceStep]) -> str:
    if not steps:
        return '<div class="ff-log"><p class="ff-wait">Waiting for capture…</p></div>'
    return '<div class="ff-log">' + "".join(_step_html(s) for s in steps) + "</div>"


def estimate_rows(est: Estimate | None) -> list[list[str]]:
    if est is None:
        return []
    return [[li.description, f"{li.quantity:g} {li.unit}", f"${li.rate:.2f}", f"${li.subtotal:.2f}"]
            for li in est.line_items]


def summary_text(est: Estimate | None) -> str:
    if est is None:
        return "Subtotal $0.00 · Tax (0%) $0.00 · Total $0.00"
    return (f"Subtotal ${est.subtotal:.2f} · Tax ({est.tax_rate:.0%}) ${est.tax:.2f} "
            f"· Total ${est.total:.2f}")
