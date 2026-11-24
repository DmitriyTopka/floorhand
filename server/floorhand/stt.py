"""Speech to text on our own server (faster-whisper). Audio never leaves the shop's server."""
import threading

import numpy as np

from . import config

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        return _model


def transcribe_pcm16(pcm: bytes, language: str | None = config.WHISPER_LANGUAGE or None) -> str:
    """PCM s16le, 16 kHz, mono, as the G2 microphone sends it."""
    if len(pcm) < 3200:  # under 0.1 s
        return ""
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = _get_model().transcribe(audio, language=language, beam_size=1, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()
