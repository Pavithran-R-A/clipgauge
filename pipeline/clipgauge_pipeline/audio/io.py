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
