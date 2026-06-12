"""Modal deployment of Nemotron Parse — Document Capture extraction (ADR-0011).

Nemotron Parse is the Extraction Model Role (ADR-0009): a document image → structured
text + tables. Local de-risk on Apple Silicon FAILED (>30GB RAM, 5+ min/doc — the
C-RADIO encoder + mBART decoder thrash without a GPU), so it runs on Modal instead.

Unlike the brain (text, vLLM OpenAI API), Parse is VISUAL — there is no standard
"parse image → structured output" OpenAI route, so this exposes a CUSTOM endpoint:
POST a base64 image, get back the parsed blocks.

The model's raw output is a token-encoded string of (bbox, text, class) triples, e.g.
`<x_120><y_45>Dual run capacitor<x_980><y_70><class_Table>`. Two repo-shipped files
turn that into structured blocks: `postprocessing.py` (extract_classes_bboxes,
transform_bbox_to_original, postprocess_text) and `latex2html.py` (table conversion).
They are NOT loaded by trust_remote_code — we download them with hf_hub_download and
import them. (Verified against the v1.2 model card, 2026-06-11; see ADR-0011.)

This endpoint runs the full postprocessing server-side and returns clean blocks
[{class, bbox, text}], so the on-device client (backends/parse.py) stays light.

Cost stance (ADR-0011): proven as a demo capability — NOT wired to the live Space
(no continuous spend). Parse is ~1GB, so a cheap T4 is plenty (no L40S needed).

Deploy:
    modal deploy quillwright/backends/modal_parse_app.py
    export FF_MODAL_PARSE_URL="https://<...>.modal.run"
"""

import modal

MODEL = "nvidia/NVIDIA-Nemotron-Parse-v1.2"

# Task prompt from the v1.2 model card — the FULL four-token form. v1.1's three-token
# prompt produces "significantly degraded" results on v1.2, per the card.
TASK_PROMPT = "</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>"

# Repo-shipped postprocessing files (standalone modules, NOT trust_remote_code).
POSTPROC_FILES = ("postprocessing.py", "latex2html.py")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        # Pins from the v1.2 model card — looser versions risk the C-RADIO/mBART
        # custom code breaking on a transformers API change.
        "torch",
        "transformers==5.6.1",
        "accelerate==1.12.0",
        "timm==1.0.22",
        "albumentations==2.0.8",
        # latex2html.py needs BeautifulSoup for table HTML conversion.
        "beautifulsoup4",
        "huggingface_hub",
        "pillow",
        "fastapi[standard]",
    )
    .env({"HF_HOME": "/cache"})
)

hf_cache = modal.Volume.from_name("quillwright-hf-cache", create_if_missing=True)

app = modal.App("quillwright-parse")


@app.cls(
    image=image,
    gpu="T4",  # Parse is ~1GB; a T4 is plenty (and the cheapest GPU).
    volumes={"/cache": hf_cache},
    timeout=600,
    scaledown_window=240,
)
@modal.concurrent(max_inputs=4)
class Parser:
    @modal.enter()
    def load(self):
        """Load the model + its repo-shipped postprocessing once per container."""
        import importlib.util
        import sys

        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModel, AutoProcessor, GenerationConfig

        # Pull postprocessing.py + latex2html.py from the model repo and put their dir
        # on sys.path (postprocessing imports latex2html by name, so both must resolve).
        for fname in POSTPROC_FILES:
            module_dir = hf_hub_download(MODEL, fname).rsplit("/", 1)[0]
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
        spec = importlib.util.spec_from_file_location(
            "nemotron_postprocessing", hf_hub_download(MODEL, "postprocessing.py")
        )
        self.pp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pp)

        self.model = (
            AutoModel.from_pretrained(MODEL, trust_remote_code=True, dtype=torch.bfloat16)
            .to("cuda")
            .eval()
        )
        self.processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
        self.gen_config = GenerationConfig.from_pretrained(MODEL, trust_remote_code=True)

    @modal.fastapi_endpoint(method="POST")
    def parse(self, payload: dict):
        """POST {image: base64} -> {blocks: [{class, bbox, text}], raw: <str>}.

        Runs the full repo postprocessing server-side: decode → extract triples →
        rescale bboxes to the original image → format text (tables as markdown).
        """
        import base64
        import io

        from PIL import Image

        data = payload.get("image", "")
        if "," in data and data.strip().startswith("data:"):
            data = data.split(",", 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")

        inputs = self.processor(
            images=[img], text=TASK_PROMPT, return_tensors="pt", add_special_tokens=False
        ).to("cuda")
        outputs = self.model.generate(**inputs, generation_config=self.gen_config)
        raw = self.processor.batch_decode(outputs, skip_special_tokens=True)[0]

        classes, bboxes, texts = self.pp.extract_classes_bboxes(raw)
        bboxes = [self.pp.transform_bbox_to_original(b, img.width, img.height) for b in bboxes]
        texts = [
            self.pp.postprocess_text(t, cls=c, table_format="markdown", text_format="markdown")
            for t, c in zip(texts, classes)
        ]
        blocks = [
            {"class": c, "bbox": list(b), "text": t} for c, b, t in zip(classes, bboxes, texts)
        ]
        return {"blocks": blocks, "raw": raw}
