# Document Capture via Nemotron Parse, with human-confirmed prices

Quillwright gains a second capture path: a **Document Capture** — a document the
tech or customer hands over (spec sheet, supplier quote, old written estimate) —
read by **Nemotron Parse** (the Extraction Model Role, ADR-0009) into structured
text + tables that feed the same Estimate pipeline as a job-site photo. The document
is entered via its own explicit control ("Add document"), never auto-classified
against a job photo.

The governing decision is how Parse output reconciles with **Facts-from-Tools
(ADR-0004)**. Parse is a model; an OCR error on a decimal ("$42.50" → "$425.0")
would put an unverified, customer-facing number into an Estimate — exactly what
Facts-from-Tools exists to prevent. Resolution: **the document is the _source_, but
any price Parse reads becomes a Proposed Line Item the human confirms or edits
before it enters the Estimate** (reusing the existing Agent Pause / interrupt flow,
ADR-0002). Items (descriptions, model numbers) flow straight through as Observations;
only _prices_ gate on human confirmation. This satisfies the glossary's existing
"user-confirmed data" clause rather than weakening it.

No new storage is introduced: Parse output flows into the in-memory
Observation/Line Item pipeline, and Estimates persist where they already do (the
`memory.py` JSON store). There is no database.

## Considered Options

- **(A) Document prices used directly as facts:** simplest, literally "document is
  the source" — but a VLM's OCR output reaches the customer unverified. Violates the
  honesty thesis the product is built on. Rejected.
- **(B) Parse extracts items only; prices always via `lookup_price`:** safest, fully
  preserves Facts-from-Tools — but it is not "document as source" for prices (the
  catalog is), so it cannot import a priced quote. Kept as the path for the
  text/items half.
- **(C) Document prices become Proposed Line Items, human-confirmed (chosen):** the
  honest reconciliation of "document as source" with Facts-from-Tools — the document
  proposes, the human gates, the customer-facing number is user-confirmed. Reuses the
  Agent Pause mechanism, so it is an extension of the existing supervision model, not
  a new one.

## Consequences

- Adds a **Document Capture** input (its own control) routing to Parse; the photo
  input still routes to MiniCPM-V. No image classifier (the user declares intent).
- Parse-read **items** become Observations (drop into the existing brain→estimate
  flow); Parse-read **prices** become Proposed Line Items surfaced via Agent Pause.
- The standalone "OCR any document" page (framing B from the grill) is a separate,
  lower-priority stretch that does not feed the Estimate.

## Update 2026-06-11 — de-risk outcome: serve on Modal, not on-device

The local-on-Mac path (the original plan, mirroring Audio/Embedding) was de-risked
and **failed on hardware**: `nvidia/NVIDIA-Nemotron-Parse-v1.2` loads and runs
(deps `timm`/`einops`/`open_clip`/`albumentations`/`cv2`; transformers 5.10.2 compat
OK; repo is NOT gated — earlier 401 was transient), but inference on Apple Silicon
spiked **>30GB RAM and took 5+ min/doc** (the C-RADIO encoder + autoregressive mBART
decoder thrash without a real GPU). Not viable locally; no token-trim or warning fixes
a memory problem. The de-risk did its job — ~45 min spent, not a day.

**Decision:** keep Nemotron Parse (the NVIDIA model, ADR-0009 sponsor breadth) but
serve it on **Modal GPU**, like the Best-Stack brain (ADR-0005). Considered + rejected:
**PaddleOCR-VL-MLX** (0.9B, ~4GB, ~2-3s/doc, native Apple-Silicon MLX — runs great
locally) — rejected because it is PaddlePaddle/Baidu, dropping the NVIDIA-Parse sponsor
tie; we accept Modal cost to keep the sponsor model. (If cost becomes a problem, the
MLX path is the documented escape hatch.)

**Modal shape differs from the brain:** Parse is _visual_ (image in), so it does NOT
fit the vLLM OpenAI `/v1/chat/completions` pattern — it gets a **custom FastAPI image
endpoint** (multipart image → `model.generate` → structured text). The C-RADIO vision
stack is baked into the Modal image.

**Cost stance (post the $4.16 brain de-risk lesson):** Modal Parse is built + proven as
a **capability for the demo/video only** — it is deliberately **NOT wired to the live
hosted Space** (no Space secrets for it), to avoid continuous GPU spend from judge
clicks. Test-run spend only.

## Update 2026-06-11 — implementation built (not yet deployed)

Researched the v1.2 model card before writing code, which corrected several
assumptions baked into the first-draft Modal app:

- **Output is token-encoded, not plain markdown.** Parse emits triples
  `<x_><y_>TEXT<x_><y_><class_NAME>` (class names DocLayNet-style capitalized:
  `Table`, `Text`, `Title`, `Caption`, `Formula`, …). Two **repo-shipped files** —
  `postprocessing.py` (`extract_classes_bboxes` / `transform_bbox_to_original` /
  `postprocess_text`) and `latex2html.py` — turn that into structured blocks. They are
  **standalone modules, NOT loaded by `trust_remote_code`**; the Modal app downloads
  them with `hf_hub_download` and imports them. `latex2html.py` needs `beautifulsoup4`.
- **dtype `bfloat16`** (not float16) and **`GenerationConfig.from_pretrained`** per the
  card. Deps pinned to the card: `transformers==5.6.1`, `timm==1.0.22`,
  `albumentations==2.0.8`, `accelerate==1.12.0`.
- **bbox canvas** is fixed at `target_w=1664, target_h=2048`.

**Shape built:** the Modal endpoint runs the full postprocessing server-side and
returns clean `{blocks: [{class, bbox, text}]}`, keeping the on-device client light.
`backends/parse.py` (`ParseModel`) is the client: it POSTs the image, then
`blocks_to_pipeline` splits blocks per decision C — `Table` rows with a price →
`ProposedLineItem` (new model; price gated for human confirm via Agent Pause),
everything else → `Observation(kind="text")`. Confirmed items become a `LineItem`
with the new `price_source="document"`. The `extraction` role resolves to `ParseModel`
for any non-stub backend (single REMOTE serving path, mirroring embedding/audio but
hosted on Modal). 9 unit tests cover `blocks_to_pipeline` against the real token format.

**Still not deployed** — awaiting the user's go-ahead to `modal deploy` and run the
mock quote through it (test-only, per the cost stance above). Considered an alternative
path: NVIDIA's hosted `build.nvidia.com` chat-completions API exposes Parse via a
`markdown_bbox` tool — rejected because it is an external API, defeating the
"we self-host the NVIDIA model on Modal" thesis (ADR-0005).
