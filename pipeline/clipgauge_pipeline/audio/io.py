"""Deterministic audio I/O without librosa's optional decoder chain."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def load_mono(path: str | Path, sample_rate: int) -> tuple[np.ndarray, int]:
    """Load local audio as contiguous float32 mono samples."""
    samples, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = np.mean(samples, axis=1, dtype=np.float32)
    if source_rate != sample_rate:
        mono = resample(mono, source_rate, sample_rate)
    return np.ascontiguousarray(mono, dtype=np.float32), sample_rate


def sample_count(path: str | Path) -> int:
    """Return source frame count without loading audio samples."""
    return int(sf.info(str(path)).frames)


def iter_mono(
    path: str | Path,
    sample_rate: int,
    *,
    chunk_samples: int = 160_000,
):
    """Yield bounded float32 mono chunks from an already-resampled file."""
    if chunk_samples < 1:
        raise ValueError("chunk_samples must be positive")
    with sf.SoundFile(str(path), mode="r") as handle:
        if handle.samplerate != sample_rate:
            raise ValueError(
                f"streaming audio requires {sample_rate} Hz, got {handle.samplerate} Hz"
            )
        while True:
            samples = handle.read(chunk_samples, dtype="float32", always_2d=True)
            if len(samples) == 0:
                return
            yield np.asarray(np.mean(samples, axis=1, dtype=np.float32), dtype=np.float32)


def read_mono_window(
    path: str | Path,
    sample_rate: int,
    start_sample: int,
    end_sample: int,
) -> np.ndarray:
    """Read one bounded mono window from an exact-rate audio file."""
    if start_sample < 0 or end_sample < start_sample:
        raise ValueError("invalid audio window")
    with sf.SoundFile(str(path), mode="r") as handle:
        if handle.samplerate != sample_rate:
            raise ValueError(
                f"windowed audio requires {sample_rate} Hz, got {handle.samplerate} Hz"
            )
        handle.seek(start_sample)
        samples = handle.read(end_sample - start_sample, dtype="float32", always_2d=True)
    return np.asarray(np.mean(samples, axis=1, dtype=np.float32), dtype=np.float32)


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample samples with the bounded SciPy polyphase implementation."""
    if source_rate == target_rate:
        return np.ascontiguousarray(samples, dtype=np.float32)
    common = np.gcd(source_rate, target_rate)
    output = resample_poly(
        np.asarray(samples, dtype=np.float32),
        target_rate // common,
        source_rate // common,
    )
    return np.ascontiguousarray(output, dtype=np.float32)
