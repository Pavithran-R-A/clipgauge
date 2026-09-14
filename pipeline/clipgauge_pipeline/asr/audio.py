"""ClipGauge-owned loading for normalized analysis audio."""

from __future__ import annotations

import wave
import struct
from pathlib import Path

import numpy as np

from .. import config

# Float32 conversion doubles the PCM footprint.
# Keep the resulting working array bounded on 8 GB systems.
MAX_ANALYSIS_WAV_BYTES = 256 * 1024 * 1024


class AnalysisAudioError(ValueError):
    """A normalized analysis WAV failed validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _pcm_data_chunk(path: Path, file_size: int) -> tuple[int, int]:
    """Locate the PCM payload without reading the payload itself."""
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
            if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
                raise AnalysisAudioError("WAV_MALFORMED", "analysis audio is not a RIFF/WAVE file")
            offset = 12
            while offset + 8 <= file_size:
                handle.seek(offset)
                chunk_header = handle.read(8)
                if len(chunk_header) != 8:
                    break
                chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
                data_offset = offset + 8
                data_end = data_offset + chunk_size
                if data_end > file_size:
                    raise AnalysisAudioError("WAV_TRUNCATED", "analysis audio chunk is incomplete")
                if chunk_id == b"data":
                    return data_offset, chunk_size
                offset = data_end + (chunk_size & 1)
    except AnalysisAudioError:
        raise
    except (OSError, struct.error) as exc:
        raise AnalysisAudioError("WAV_MALFORMED", "analysis audio is not a readable RIFF/WAVE file") from exc
    raise AnalysisAudioError("WAV_MALFORMED", "analysis audio has no PCM data chunk")


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
    except (OSError, wave.Error) as exc:
        raise AnalysisAudioError(
            "WAV_MALFORMED", "analysis audio is not a readable RIFF/WAVE file"
        ) from exc

    data_offset, data_size = _pcm_data_chunk(path, file_size)
    if data_size < expected_bytes:
        raise AnalysisAudioError(
            "WAV_TRUNCATED", "analysis audio ended before its declared samples"
        )
    mapped = None
    try:
        mapped = np.memmap(path, dtype="<i2", mode="r", offset=data_offset, shape=(frame_count,))
        samples = mapped.astype(np.float32, copy=True)
        samples /= np.float32(32768.0)
    except (OSError, TypeError, ValueError) as exc:
        raise AnalysisAudioError(
            "WAV_MALFORMED", "analysis audio samples could not be decoded"
        ) from exc
    finally:
        if mapped is not None:
            del mapped
    if samples.size != frame_count:
        raise AnalysisAudioError("WAV_TRUNCATED", "analysis audio sample count is incomplete")
    return np.ascontiguousarray(samples, dtype=np.float32)
