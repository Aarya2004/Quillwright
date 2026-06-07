"""Ollama-backed Model: real local inference via llama.cpp under the hood.

Implements the same interface as StubModel (name + generate) so it drops into
the resolver. Genuinely local / no third-party cloud API.
"""

import base64

import requests

DEFAULT_HOST = "http://localhost:11434"


class OllamaModel:
    def __init__(self, model: str, host: str = DEFAULT_HOST, timeout: float = 120.0):
        self.name = model
        self._host = host
        self._timeout = timeout

    def generate(self, prompt: str, image_path: str | None = None) -> str:
        payload = {"model": self.name, "prompt": prompt, "stream": False}
        if image_path:
            with open(image_path, "rb") as f:
                payload["images"] = [base64.b64encode(f.read()).decode("ascii")]
        resp = requests.post(f"{self._host}/api/generate", json=payload, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Native tool-calling chat. Returns the assistant message (may hold tool_calls)."""
        payload = {"model": self.name, "messages": messages, "tools": tools, "stream": False}
        resp = requests.post(f"{self._host}/api/chat", json=payload, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json().get("message", {})
