# FieldForge HF Space — Docker SDK.
# Runs the bespoke gr.Server (FastAPI) app in STUB mode (no GPU, no Ollama): the contest
# requires a Gradio Space underneath, and Docker SDK is sanctioned. Real models reach the
# hosted Space via Modal later (ADR-0005); this image needs neither GPU nor model weights.
FROM python:3.12-slim

# HF Spaces run as a non-root user (uid 1000) and expose port 7860.
ENV PORT=7860 \
    FF_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/tmp/hf

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App + bundled sample data (catalog + evalset) + the web frontend.
COPY quillwright/ ./quillwright/
COPY data/ ./data/

EXPOSE 7860

# gr.Server is a FastAPI app; launch via uvicorn (NOT .launch()). server.py's __main__
# binds $FF_HOST:$PORT, so `python -m quillwright.server` serves all routes.
CMD ["python", "-m", "quillwright.server"]
