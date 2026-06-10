"""AudioModel: local speech-to-text for the spoken voice note (ADR-0009).

Wraps CohereLabs/cohere-transcribe-03-2026 (2B, #1 WER, on-device) via transformers'
canonical path — AutoProcessor + CohereAsrForConditionalGeneration, the approach the
model card documents (the generic `pipeline()` API errors on this model). Verified
locally: a trade note transcribes cleanly.

Heavy (torch + a 2B model), so the import + load are LAZY — importing this module
costs nothing; the model loads on first `.transcribe()`. Keeps the spoken note inside
the on-device Private Stack (🔌 Off the Grid). Gated repo: needs HF access + token.
"""

DEFAULT_MODEL = "CohereLabs/cohere-transcribe-03-2026"


class AudioModel:
    def __init__(self, model: str = DEFAULT_MODEL, language: str = "en"):
        self.name = model
        self._language = language
        self._processor = None
        self._model = None

    def _load(self):
        if self._model is None:
            from transformers import AutoProcessor, CohereAsrForConditionalGeneration

            self._processor = AutoProcessor.from_pretrained(self.name)
            self._model = CohereAsrForConditionalGeneration.from_pretrained(
                self.name, device_map="auto"
            )
        return self._processor, self._model

    def transcribe(self, path: str) -> str:
        from transformers.audio_utils import load_audio

        processor, model = self._load()
        audio = load_audio(path, sampling_rate=16000)
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt", language=self._language)
        inputs.to(model.device, dtype=model.dtype)
        outputs = model.generate(**inputs, max_new_tokens=256)
        decoded = processor.decode(outputs, skip_special_tokens=True)
        # decode() returns a list (one string per batch item); we transcribe one clip.
        if isinstance(decoded, list):
            decoded = decoded[0] if decoded else ""
        return decoded
