"""Conservative working-space estimates for one analysis job."""

from __future__ import annotations

import math

MIN_SAFE_BYTES = 1 * 1024**3
AUDIO_BYTES_PER_SECOND = 32_000
CHECKPOINT_BYTES = 256 * 1024**2
MIN_RENDER_BYTES = 256 * 1024**2
SAFETY_FRACTION = 0.20
MIN_SAFETY_BYTES = 512 * 1024**2
CACHED_SCORE_MIN_SAFE_BYTES = 256 * 1024**2


def for_source(
    source_bytes: int,
    *,
    duration_seconds: float | None = None,
    source_copy_bytes: int | None = None,
) -> dict[str, int | float | None]:
    """Estimate source copy, analysis, checkpoints, render, and margin."""
    size = max(0, int(source_bytes))
    copy_bytes = size if source_copy_bytes is None else max(0, int(source_copy_bytes))
    duration = duration_seconds if duration_seconds is not None and math.isfinite(duration_seconds) else None
    audio_bytes = max(0, math.ceil(duration * AUDIO_BYTES_PER_SECOND)) if duration is not None and duration >= 0 else 0
    render_bytes = max(MIN_RENDER_BYTES, math.ceil(size * 0.5))
    working_bytes = copy_bytes + audio_bytes + CHECKPOINT_BYTES + render_bytes
    safety_bytes = max(MIN_SAFETY_BYTES, math.ceil(working_bytes * SAFETY_FRACTION))
    return {
        "source_bytes": size,
        "source_copy_bytes": copy_bytes,
        "duration_seconds": duration,
        "temporary_audio_bytes": audio_bytes,
        "checkpoint_bytes": CHECKPOINT_BYTES,
        "render_bytes": render_bytes,
        "safety_margin_bytes": safety_bytes,
        "required_bytes": working_bytes + safety_bytes,
    }


def for_cached_score() -> dict[str, int | float | None]:
    """Estimate transient space for a cached score-only replay."""
    working_bytes = CACHED_SCORE_MIN_SAFE_BYTES // 2
    safety_bytes = CACHED_SCORE_MIN_SAFE_BYTES - working_bytes
    return {
        "source_bytes": 0,
        "source_copy_bytes": 0,
        "duration_seconds": None,
        "temporary_audio_bytes": 0,
        "checkpoint_bytes": working_bytes,
        "render_bytes": 0,
        "safety_margin_bytes": safety_bytes,
        "required_bytes": working_bytes + safety_bytes,
    }
