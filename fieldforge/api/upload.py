"""Save uploaded job photos to a temp dir so perception can read them by path."""

import base64
import hashlib
import os

UPLOAD_DIR = "/tmp/fieldforge_uploads"


def save_upload(data: str, filename: str) -> str:
    """Decode a (possibly data-URL) base64 image and write it; return the file path."""
    if "," in data and data.strip().startswith("data:"):
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ".png"
    digest = hashlib.sha1(raw).hexdigest()[:16]
    path = os.path.join(UPLOAD_DIR, f"{digest}{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path
