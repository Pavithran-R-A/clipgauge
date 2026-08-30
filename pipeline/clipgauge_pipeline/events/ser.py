"""Speech-emotion arousal fallback policy.

Remote SpeechBrain custom interfaces are deliberately disabled. The DSP
proxy remains deterministic until a verified local SER bundle is shipped.
"""

from __future__ import annotations

import numpy as np

WINDOW_SEC = 5.0
HOP_SEC = 2.5
GRID_SEC = 0.5

# Kept for compatibility with existing scoring imports.
AROUSAL_WEIGHTS = {"ang": 1.0, "hap": 0.85, "neu": 0.4, "sad": 0.15}


def _windows(segments: list[dict], duration: float) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    for seg in segments:
        start, end = float(seg["start"]), min(float(seg["end"]), duration)
        t = start
        while t < end:
            w_end = min(t + WINDOW_SEC, end)
            if w_end - t >= 1.0:
                spans.append((t, w_end))
            if w_end >= end:
                break
            t += HOP_SEC
    return spans


def arousal_curve_ser(
    y16k: np.ndarray,
    segments: list[dict],
    cache_dir: str,
    progress=None,
) -> np.ndarray | None:
    """Return None until a verified local SER bundle exists."""
    del y16k, segments, cache_dir, progress
    return None


def arousal_curve_dsp(dynamics: list[float], dynamics_grid_sec: float) -> np.ndarray:
    """Fallback proxy: energy dynamics resampled onto the arousal grid."""
    arr = np.asarray(dynamics, dtype=float)
    if len(arr) == 0:
        return np.zeros(0)
    factor = max(1, int(round(GRID_SEC / dynamics_grid_sec)))
    trimmed = arr[: (len(arr) // factor) * factor]
    coarse = trimmed.reshape(-1, factor).mean(axis=1) if len(trimmed) else arr
    top = np.percentile(coarse, 95) or 1.0
    return np.clip(coarse / top, 0.0, 1.0)
