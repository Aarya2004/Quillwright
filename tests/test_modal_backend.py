"""Unit tests for the Modal client's response adaptation — no network needed.

The only real logic in ModalModel is translating vLLM's OpenAI-style response back
to the {content, tool_calls:[{function:{name, arguments(dict)}}]} contract that
brain_loop.py / chat.py expect. We test that translation directly.
"""

from quillwright.backends.modal import _adapt_tool_call


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
