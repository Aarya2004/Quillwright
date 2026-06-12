"""Unit tests for the Modal client's response adaptation — no network needed.

The only real logic in ModalModel is translating vLLM's OpenAI-style response back
to the {content, tool_calls:[{function:{name, arguments(dict)}}]} contract that
brain_loop.py / chat.py expect. We test that translation directly.
"""

import json

from quillwright.backends.modal import ModalModel, _adapt_tool_call, _to_openai_messages


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _capture_post(captured, content="ok"):
    def post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp({"choices": [{"message": {"content": content}}]})

    return post


def test_generate_with_image_sends_openai_image_content(monkeypatch, tmp_path):
    # Best-Stack Perception (Omni): an image rides the OpenAI multimodal content
    # shape — a data-URL image_url part next to the text part.
    img = tmp_path / "unit.png"
    img.write_bytes(b"\x89PNGfake")
    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    captured = {}
    monkeypatch.setattr("quillwright.backends.modal.requests.post", _capture_post(captured))

    model = ModalModel("nemotron-3-nano-omni-30b-a3b", role="perception")
    out = model.generate("What parts do you see?", image_path=str(img))

    assert out == "ok"
    parts = captured["body"]["messages"][0]["content"]
    kinds = {p["type"] for p in parts}
    assert kinds == {"text", "image_url"}
    image_part = next(p for p in parts if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_generate_without_image_keeps_plain_string_content(monkeypatch):
    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    captured = {}
    monkeypatch.setattr("quillwright.backends.modal.requests.post", _capture_post(captured))

    model = ModalModel("nemotron-3-nano-omni-30b-a3b", role="perception")
    model.generate("plain prompt")
    assert captured["body"]["messages"][0]["content"] == "plain prompt"


def test_transcribe_sends_input_audio_and_returns_text(monkeypatch, tmp_path):
    # Best-Stack Audio (Omni): a voice note goes up as OpenAI input_audio (base64 +
    # format) and the transcript comes back as plain content.
    wav = tmp_path / "note.wav"
    wav.write_bytes(b"RIFFfakewav")
    monkeypatch.setenv("FF_MODAL_OMNI_URL", "https://example--omni")
    captured = {}
    monkeypatch.setattr(
        "quillwright.backends.modal.requests.post",
        _capture_post(captured, content="replaced the capacitor"),
    )

    model = ModalModel("nemotron-3-nano-omni-30b-a3b", role="audio")
    text = model.transcribe(str(wav))

    assert text == "replaced the capacitor"
    parts = captured["body"]["messages"][0]["content"]
    audio_part = next(p for p in parts if p["type"] == "input_audio")
    assert audio_part["input_audio"]["format"] == "wav"
    assert audio_part["input_audio"]["data"]  # base64 payload present


def test_each_role_reads_its_own_url_env(monkeypatch):
    # multilingual must point at the Aya app, never silently reuse the brain URL.
    monkeypatch.delenv("FF_MODAL_AYA_URL", raising=False)
    monkeypatch.setenv("FF_MODAL_BRAIN_URL", "https://example--brain")
    try:
        ModalModel("aya-expanse-8b", role="multilingual")
        assert False, "expected RuntimeError when the role's own URL is unset"
    except RuntimeError as exc:
        assert "FF_MODAL_AYA_URL" in str(exc)


def test_chat_unchanged_for_brain_role(monkeypatch):
    # The original brain contract must survive the per-role refactor.
    monkeypatch.setenv("FF_MODAL_BRAIN_URL", "https://example--brain")
    captured = {}

    def post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "finish",
                                        "arguments": json_dumps_empty,
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )

    json_dumps_empty = json.dumps({})
    monkeypatch.setattr("quillwright.backends.modal.requests.post", post)
    model = ModalModel("nemotron-3-nano-30b-a3b")
    out = model.chat([{"role": "user", "content": "x"}], tools=[])
    assert captured["url"].endswith("/v1/chat/completions")
    assert out["tool_calls"][0]["function"]["arguments"] == {}


def test_adapt_parses_json_string_arguments():
    # vLLM/OpenAI hands `arguments` as a JSON STRING; we must return a dict.
    tc = {"function": {"name": "add_item", "arguments": '{"item": "contactor", "quantity": 2}'}}
    out = _adapt_tool_call(tc)
    assert out["function"]["name"] == "add_item"
    assert out["function"]["arguments"] == {"item": "contactor", "quantity": 2}


def test_adapt_handles_already_dict_arguments():
    tc = {"function": {"name": "finish", "arguments": {}}}
    out = _adapt_tool_call(tc)
    assert out["function"]["arguments"] == {}


def test_adapt_tolerates_bad_json_without_crashing():
    tc = {"function": {"name": "x", "arguments": "{not valid json"}}
    out = _adapt_tool_call(tc)
    assert out["function"]["arguments"] == {}


def test_adapt_handles_missing_arguments():
    tc = {"function": {"name": "finish"}}
    out = _adapt_tool_call(tc)
    assert out["function"]["name"] == "finish"
    assert out["function"]["arguments"] == {}


# --- Message sanitization: our internal shape -> valid OpenAI format ---
# vLLM's OpenAI endpoint is stricter than Ollama: assistant tool_calls need string
# `arguments` + an `id`, and each `tool` reply needs a matching `tool_call_id`.


def test_sanitize_passes_through_plain_messages():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    out = _to_openai_messages(msgs)
    assert out == msgs


def test_sanitize_assistant_toolcall_gets_id_and_string_args():
    msgs = [
        {"role": "user", "content": "add a capacitor"},
        # our internal assistant message: arguments is a DICT, no id
        {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "add_item", "arguments": {"item": "capacitor"}}}],
        },
        # our internal tool reply: no tool_call_id
        {"role": "tool", "content": "added capacitor"},
    ]
    out = _to_openai_messages(msgs)
    asst = out[1]
    tc = asst["tool_calls"][0]
    assert tc["id"]  # an id was assigned
    assert tc["type"] == "function"
    assert isinstance(tc["function"]["arguments"], str)  # serialized to a JSON string
    # the following tool message references that id
    assert out[2]["tool_call_id"] == tc["id"]


def test_sanitize_threads_multiple_toolcalls_to_their_replies():
    msgs = [
        {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "add_item", "arguments": {"item": "a"}}},
                {"function": {"name": "add_item", "arguments": {"item": "b"}}},
            ],
        },
        {"role": "tool", "content": "added a"},
        {"role": "tool", "content": "added b"},
    ]
    out = _to_openai_messages(msgs)
    ids = [tc["id"] for tc in out[0]["tool_calls"]]
    assert out[1]["tool_call_id"] == ids[0]
    assert out[2]["tool_call_id"] == ids[1]


def test_sanitize_treats_roleless_toolcall_msg_as_assistant():
    # brain_loop appends our chat() RETURN value verbatim — it has tool_calls but
    # NO role. vLLM rejects role-less messages; the sanitizer must fix it.
    msgs = [
        {"role": "user", "content": "x"},
        {
            "content": "",
            "tool_calls": [
                {"function": {"name": "add_priced_item", "arguments": {"item": "capacitor"}}}
            ],
        },
        {"role": "tool", "content": "added"},
    ]
    out = _to_openai_messages(msgs)
    assert out[1]["role"] == "assistant"
    assert isinstance(out[1]["tool_calls"][0]["function"]["arguments"], str)
    assert out[2]["tool_call_id"] == out[1]["tool_calls"][0]["id"]
