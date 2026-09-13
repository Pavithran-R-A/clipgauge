"""ClipGauge-owned loading for normalized analysis audio."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .. import config

MAX_ANALYSIS_WAV_BYTES = 512 * 1024 * 1024


class AnalysisAudioError(ValueError):
    """A normalized analysis WAV failed validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def load_analysis_audio(path: Path) -> np.ndarray:
    """Load a validated 16 kHz mono PCM WAV into float32 samples."""
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise AnalysisAudioError("WAV_MISSING", "analysis audio is unavailable") from exc
    if file_size <= 0:
        raise AnalysisAudioError("WAV_MALFORMED", "analysis audio is empty")
    if file_size > MAX_ANALYSIS_WAV_BYTES:
        raise AnalysisAudioError("WAV_TOO_LARGE", "analysis audio exceeds the memory safety limit")

    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getcomptype() != "NONE":
                raise AnalysisAudioError(
                    "WAV_UNSUPPORTED", "analysis audio is not uncompressed PCM"
                )
            if (
                handle.getnchannels() != 1
                or handle.getsampwidth() != 2
                or handle.getframerate() != config.AUDIO_SR
            ):
                raise AnalysisAudioError(
                    "WAV_FORMAT_UNSUPPORTED",
                    "analysis audio must be 16 kHz mono 16-bit PCM",
                )
            frame_count = handle.getnframes()
            if frame_count <= 0:
                raise AnalysisAudioError("WAV_MALFORMED", "analysis audio has no samples")
            expected_bytes = frame_count * handle.getsampwidth()
            if expected_bytes > MAX_ANALYSIS_WAV_BYTES:
                raise AnalysisAudioError(
                    "WAV_TOO_LARGE", "analysis audio exceeds the memory safety limit"
                )
            raw = handle.readframes(frame_count)
    except (OSError, wave.Error) as exc:
        raise AnalysisAudioError(
            "WAV_MALFORMED", "analysis audio is not a readable RIFF/WAVE file"
        ) from exc

    if len(raw) != expected_bytes:
        raise AnalysisAudioError(
            "WAV_TRUNCATED", "analysis audio ended before its declared samples"
        )
    try:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / np.float32(
            32768.0
        )
    except (TypeError, ValueError) as exc:
        raise AnalysisAudioError(
            "WAV_MALFORMED", "analysis audio samples could not be decoded"
        ) from exc
    if samples.size != frame_count:
        raise AnalysisAudioError("WAV_TRUNCATED", "analysis audio sample count is incomplete")
    return np.ascontiguousarray(samples, dtype=np.float32)
