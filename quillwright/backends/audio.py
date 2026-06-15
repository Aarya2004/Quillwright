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


def to_wav_16k_mono(path: str) -> str:
    """Return a path to a 16kHz mono WAV for `path`.

    Browser/phone MediaRecorder emits a **webm** container (Opus), which librosa /
    transformers' `load_audio` cannot decode ("appears to be a video file"). Twilio call
    recordings can be `.mp3` too. We normalize anything that isn't already a `.wav` to
    16kHz mono PCM WAV with ffmpeg first — the format the ASR model wants, and a safer
    container all round. A `.wav` input is returned unchanged (no needless transcode).

    Raises RuntimeError with a clear message if ffmpeg isn't installed.
    """
    import os
    import shutil
    import subprocess
    import tempfile

    if path.lower().endswith(".wav"):
        return path
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required to transcode the voice note (browser/phone records webm, "
            "which the ASR model can't read). Install it (e.g. `brew install ffmpeg`)."
        )
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out = tmp.name
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1", "-f", "wav", out],
        check=True,
        capture_output=True,
    )
    if not os.path.getsize(out):
        raise RuntimeError(f"ffmpeg produced an empty WAV transcoding {path!r}.")
    return out


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
        import os

        from transformers.audio_utils import load_audio

        processor, model = self._load()
        # Normalize webm/m4a/mp3 → 16kHz mono WAV (load_audio can't decode webm). Clean up
        # any temp file we created (but never the caller's original .wav).
        wav = to_wav_16k_mono(path)
        try:
            audio = load_audio(wav, sampling_rate=16000)
        finally:
            if wav != path:
                try:
                    os.unlink(wav)
                except OSError:
                    pass
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt", language=self._language)
        inputs.to(model.device, dtype=model.dtype)
        outputs = model.generate(**inputs, max_new_tokens=256)
        decoded = processor.decode(outputs, skip_special_tokens=True)
        # decode() returns a list (one string per batch item); we transcribe one clip.
        if isinstance(decoded, list):
            decoded = decoded[0] if decoded else ""
        return decoded
