import base64

from fieldforge.api.upload import save_upload


def test_save_upload_writes_file_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("fieldforge.api.upload.UPLOAD_DIR", str(tmp_path))
    data = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    path = save_upload(data, "unit.png")
    assert path.endswith(".png")
    with open(path, "rb") as f:
        assert f.read().startswith(b"\x89PNG")


def test_save_upload_strips_data_url_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr("fieldforge.api.upload.UPLOAD_DIR", str(tmp_path))
    raw = base64.b64encode(b"\xff\xd8\xffjpeg").decode("ascii")
    path = save_upload(f"data:image/jpeg;base64,{raw}", "p.jpg")
    with open(path, "rb") as f:
        assert f.read().startswith(b"\xff\xd8\xff")
