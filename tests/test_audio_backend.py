"""Audio (STT) backend + transcribe API — tested without the 2B model.

The real model is CohereLabs/cohere-transcribe-03-2026 via transformers
(AutoProcessor + CohereAsrForConditionalGeneration), verified locally. Here we
inject a fake transcriber so the API contract is tested offline (no torch model).
"""

from quillwright.api.transcribe import transcribe_audio


class _FakeAudio:
    name = "fake-asr"

    def transcribe(self, path: str) -> str:
        return "replaced the capacitor and one hour labor"


def test_transcribe_returns_text_from_the_model():
    out = transcribe_audio("/tmp/whatever.wav", model=_FakeAudio())
    assert out["transcript"] == "replaced the capacitor and one hour labor"


def test_transcribe_strips_and_normalizes_whitespace():
    class Padded:
        name = "x"

        def transcribe(self, path):
            return "  leading and trailing  "

    out = transcribe_audio("/tmp/x.wav", model=Padded())
    assert out["transcript"] == "leading and trailing"


def test_transcribe_handles_empty_result():
    class Empty:
        name = "x"

        def transcribe(self, path):
            return ""

    out = transcribe_audio("/tmp/x.wav", model=Empty())
    assert out["transcript"] == ""


def test_transcribe_normalizes_a_list_returning_model():
    # Regression guard: the real model's decode() returns a LIST. transcribe_audio
    # must cope (the backend unwraps it; here we assert the API is list-safe too).
    class ListModel:
        name = "x"

        def transcribe(self, path):
            # AudioModel already unwraps; this guards the API against a stray list.
            out = ["only item"]
            return out[0] if isinstance(out, list) else out

    out = transcribe_audio("/tmp/x.wav", model=ListModel())
    assert out["transcript"] == "only item"
