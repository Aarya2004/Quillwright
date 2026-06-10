"""Unit tests for the Modal client's response adaptation — no network needed.

The only real logic in ModalModel is translating vLLM's OpenAI-style response back
to the {content, tool_calls:[{function:{name, arguments(dict)}}]} contract that
brain_loop.py / chat.py expect. We test that translation directly.
"""

from quillwright.backends.modal import _adapt_tool_call, _to_openai_messages


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
