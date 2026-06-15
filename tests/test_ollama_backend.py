from quillwright.backends.ollama import OllamaModel


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_generate_text_calls_ollama_and_returns_response(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp({"response": "hello from nemotron"})

    monkeypatch.setattr("quillwright.backends.ollama.requests.post", fake_post)
    m = OllamaModel("nemotron-3-nano:4b")
    out = m.generate("Say hello")
    assert out == "hello from nemotron"
    assert captured["json"]["model"] == "nemotron-3-nano:4b"
    assert captured["json"]["prompt"] == "Say hello"
    assert captured["json"]["stream"] is False


def test_generate_with_image_path_attaches_base64(monkeypatch, tmp_path):
    img = tmp_path / "unit.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeResp({"response": "[]"})

    monkeypatch.setattr("quillwright.backends.ollama.requests.post", fake_post)
    m = OllamaModel("minicpm-v")
    m.generate("describe this", image_path=str(img))
    # image is sent as a base64 string in the images list
    assert "images" in captured["json"] and len(captured["json"]["images"]) == 1
    assert isinstance(captured["json"]["images"][0], str) and captured["json"]["images"][0]


def test_name_is_the_model_id():
    assert OllamaModel("minicpm-v").name == "minicpm-v"


def test_chat_sends_messages_and_tools_and_returns_message(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp(
            {"message": {"role": "assistant", "tool_calls": [{"function": {"name": "finish"}}]}}
        )

    monkeypatch.setattr("quillwright.backends.ollama.requests.post", fake_post)
    m = OllamaModel("nemotron-3-nano:4b")
    msg = m.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["tools"] == [{"type": "function"}]
    assert msg["tool_calls"][0]["function"]["name"] == "finish"
