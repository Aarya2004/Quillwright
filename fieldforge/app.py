from pathlib import Path
import gradio as gr
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from fieldforge.catalog import Catalog
from fieldforge.resolver import StubModel
from fieldforge.models import Capture
from fieldforge.agent import build_agent
from fieldforge.pdf import estimate_to_pdf
from fieldforge.ui import trace_html, estimate_rows, summary_text

CATALOG = Catalog.from_file("data/sample_catalog.json")
CSS = (Path(__file__).parent / "theme.css").read_text()
# Demo stub perception; real runs use the resolver's perception model.
DEMO_PERCEPTION = lambda: StubModel(responses=[
    '[{"kind":"part","text":"capacitor","confidence":0.9},'
    ' {"kind":"part","text":"labor","confidence":0.9}]'
])
THREAD = {"configurable": {"thread_id": "ui"}}


def run_job(transcript, trade):
    agent = build_agent(DEMO_PERCEPTION(), CATALOG, InMemorySaver())
    cap = Capture(image_paths=["demo.jpg"], transcript=transcript, trade_hint=trade or "Job")
    out = agent.invoke({"capture": cap, "observations": [], "line_items": [],
                        "trace": [], "estimate": None}, THREAD)
    est = out.get("estimate")
    pdf = None
    if est is not None:
        pdf = "/tmp/fieldforge_estimate.pdf"
        estimate_to_pdf(est, pdf)
    return trace_html(out["trace"]), estimate_rows(est), summary_text(est), pdf


with gr.Blocks(title="FieldForge") as demo:
    gr.HTML('<div class="ff-title">Forge Estimate: AC Unit Repair — 123 Maple St</div>')
    with gr.Row():
        transcript = gr.Textbox(label="Voice note (transcript)", lines=2,
                                placeholder="e.g. replaced the capacitor, one hour labor")
        trade = gr.Textbox(label="Trade", value="hvac")
    run_btn = gr.Button("Forge estimate", variant="primary")
    with gr.Row(equal_height=True):
        with gr.Column(scale=4):
            gr.HTML('<div class="ff-pane-head">⌁ AI Forge</div>')
            trace_out = gr.HTML(trace_html([]))
        with gr.Column(scale=6):
            gr.HTML('<div class="ff-pane-head">Draft Estimate</div>')
            est_table = gr.Dataframe(headers=["Description", "Qty", "Rate", "Amount"],
                                     datatype=["str", "str", "str", "str"],
                                     interactive=True, wrap=True)
            summary = gr.Markdown(summary_text(None))
            pdf_btn = gr.Button("Preview PDF")
    pdf_out = gr.File(label="Estimate PDF")
    with gr.Row():
        lang = gr.Dropdown(["English", "Spanish (Español)", "French (Français)"],
                           value="English", label="Generate Customer Copy")
        gr.Button("Discard Draft")
        gr.Button("Finalize & Send", variant="primary")
    run_btn.click(run_job, [transcript, trade], [trace_out, est_table, summary, pdf_out])

if __name__ == "__main__":
    demo.launch(css=CSS, theme=gr.themes.Soft(primary_hue="orange"))
