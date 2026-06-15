"""ModalModel: the Best-Stack hosted-compute client (ADR-0005 / ADR-0009).

Same interface as OllamaModel (name + generate + chat, plus transcribe for the
Audio role) so the resolver can swap to it with `backend="modal"`. It calls the
vLLM OpenAI-compatible server deployed by the role's modal app and adapts the
response back to our internal contract:

  - chat() returns {"content": str, "tool_calls": [{"function": {"name", "arguments"}}]}
    where `arguments` is a DICT (vLLM/OpenAI gives it as a JSON string — we parse it),
    matching what brain_loop.py expects from OllamaModel.chat().
  - generate() takes an optional image_path (Best-Stack Perception via Omni) sent
    as an OpenAI data-URL image_url content part.
  - transcribe() sends a voice note as OpenAI input_audio (Best-Stack Audio via the
    SAME Omni deployment — it is omnimodal, so one app serves two Model Roles).

Each role reads its own base URL env (printed by `modal deploy` of its app):
brain -> modal_app.py, perception/audio -> modal_omni_app.py,
multilingual -> modal_aya_app.py.
"""

import base64
import json
import os
from pathlib import Path

import requests

# role -> (url env, served-model override env, default served model repo id).
# The deployed vLLM server pins the real repo; the env override exists for the
# day a variant swap shouldn't need a redeploy of this client.
ROLE_ENDPOINTS = {
    "brain": (
        "FF_MODAL_BRAIN_URL",
        "FF_MODAL_BRAIN_MODEL",
        "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
    ),
    "perception": (
        "FF_MODAL_OMNI_URL",
        "FF_MODAL_OMNI_MODEL",
        "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-FP8",
    ),
    "audio": (
        "FF_MODAL_OMNI_URL",
        "FF_MODAL_OMNI_MODEL",
        "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-FP8",
    ),
    "multilingual": (
        "FF_MODAL_AYA_URL",
        "FF_MODAL_AYA_MODEL",
        "CohereLabs/aya-expanse-8b",
    ),
}


class ModalModel:
    def __init__(
        self,
        model: str,
        role: str = "brain",
        base_url: str | None = None,
        timeout: float = 300.0,
    ):
        # `model` is the label/role tag; the deployed server already pins the real
        # repo id, so we send a model field vLLM accepts (the served model name).
        self.name = model
        url_env, model_env, default_model = ROLE_ENDPOINTS[role]
        self._base = (base_url or os.environ.get(url_env, "")).rstrip("/")
        if not self._base:
            raise RuntimeError(
                f"{url_env} is not set — deploy the Modal app for role '{role}' and "
                "export the URL it prints (see quillwright/backends/modal_*.py)."
            )
        self._served_model = os.environ.get(model_env, default_model)
        self._timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(f"{self._base}{path}", json=body, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Tool-calling chat via vLLM's OpenAI API; adapt to our message contract."""
        body = {
            "model": self._served_model,
            "messages": _to_openai_messages(messages),
            "tools": tools,
            "tool_choice": "auto",
            "stream": False,
        }
        data = self._post("/v1/chat/completions", body)
        msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
        return {
            "content": msg.get("content") or "",
            "tool_calls": [_adapt_tool_call(tc) for tc in (msg.get("tool_calls") or [])],
        }

    def generate(self, prompt: str, image_path: str | None = None) -> str:
        """Completion via the OpenAI chat API; an image (Best-Stack Perception via
        Omni) rides as a data-URL image_url content part."""
        content: str | list = prompt
        if image_path:
            suffix = Path(image_path).suffix.lstrip(".").lower() or "png"
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{suffix};base64,{_b64(image_path)}"},
                },
            ]
        body = {
            "model": self._served_model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        data = self._post("/v1/chat/completions", body)
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""

    def transcribe(self, audio_path: str) -> str:
        """Transcribe a voice note (Best-Stack Audio via Omni): OpenAI input_audio
        content in, plain transcript out. Same contract as AudioModel.transcribe."""
        fmt = Path(audio_path).suffix.lstrip(".").lower() or "wav"
        body = {
            "model": self._served_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": _b64(audio_path), "format": fmt},
                        },
                        {"type": "text", "text": "Transcribe this voice note verbatim."},
                    ],
                }
            ],
            "stream": False,
        }
        data = self._post("/v1/chat/completions", body)
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def _b64(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _adapt_tool_call(tc: dict) -> dict:
    """OpenAI tool_call -> our shape. `arguments` arrives as a JSON string; parse it."""
    fn = tc.get("function", {}) or {}
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    return {"function": {"name": fn.get("name", ""), "arguments": args}}


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Sanitize our internal message list into valid OpenAI chat format.

    vLLM's OpenAI endpoint is stricter than Ollama, which our brain_loop targets:
      - assistant tool_calls need a string `arguments` (we carry a dict) + an `id`;
      - each `tool` reply needs a `tool_call_id` matching its assistant tool_call.
    We assign deterministic ids and thread them to the following tool messages, so
    brain_loop.py / the Ollama path stay untouched.
    """
    out: list[dict] = []
    pending_ids: list[str] = []  # tool_call ids awaiting their tool replies, in order
    counter = 0

    for m in messages:
        role = m.get("role")
        # A message carrying tool_calls is an assistant turn — even if it has no
        # `role` (our chat() return value is appended verbatim by brain_loop and
        # lacks one). vLLM requires role + string args + ids; normalize all of it.
        if m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {}) or {}
                args = fn.get("arguments", {})
                if not isinstance(args, str):
                    args = json.dumps(args)
                tc_id = tc.get("id") or f"call_{counter}"
                counter += 1
                pending_ids.append(tc_id)
                calls.append(
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": fn.get("name", ""), "arguments": args},
                    }
                )
            out.append(
                {"role": "assistant", "content": m.get("content") or None, "tool_calls": calls}
            )
        elif role == "tool":
            tc_id = m.get("tool_call_id") or (pending_ids.pop(0) if pending_ids else "call_0")
            out.append({"role": "tool", "tool_call_id": tc_id, "content": m.get("content", "")})
        else:
            out.append(m)
    return out
