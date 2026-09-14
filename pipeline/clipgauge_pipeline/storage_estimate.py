"""Conservative working-space estimates for one analysis job."""

from __future__ import annotations

import math
from collections.abc import Mapping

MIN_SAFE_BYTES = 1 * 1024**3
AUDIO_BYTES_PER_SECOND = 32_000
CHECKPOINT_BYTES = 256 * 1024**2
MIN_RENDER_BYTES = 256 * 1024**2
SAFETY_FRACTION = 0.20
MIN_SAFETY_BYTES = 512 * 1024**2
CACHED_SCORE_MIN_SAFE_BYTES = 256 * 1024**2
# Missing URL sizes must assume a high-bitrate source. This avoids allowing
# long or high-resolution downloads through a falsely small duration guess.
URL_FALLBACK_BYTES_PER_SECOND = 4 * 1024**2
URL_FALLBACK_MIN_SOURCE_BYTES = 512 * 1024**2


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


def _positive_number(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _metadata_size(metadata: Mapping[str, object]) -> tuple[int | None, str]:
    exact = _positive_number(metadata.get("filesize"))
    approximate = _positive_number(metadata.get("filesize_approx"))
    formats = metadata.get("requested_formats") or metadata.get("formats")
    if isinstance(formats, list):
        format_sizes = [
            _positive_number(item.get("filesize"))
            for item in formats
            if isinstance(item, Mapping)
        ]
        format_sizes = [size for size in format_sizes if size is not None]
        if format_sizes:
            exact = exact or sum(format_sizes)
    if exact:
        return exact, "exact"
    if approximate:
        return approximate, "approximate"
    return None, "duration-fallback"


def for_url_metadata(metadata: Mapping[str, object] | None) -> dict[str, int | float | str | None]:
    """Estimate URL working space without treating missing size as zero."""
    metadata = metadata if isinstance(metadata, Mapping) else {}
    try:
        duration = float(metadata.get("duration"))
    except (TypeError, ValueError, OverflowError):
        duration = None
    if duration is not None and (not math.isfinite(duration) or duration < 0):
        duration = None
    source_size, confidence = _metadata_size(metadata)
    if source_size is None:
        duration_bytes = math.ceil((duration or 0.0) * URL_FALLBACK_BYTES_PER_SECOND)
        source_size = max(URL_FALLBACK_MIN_SOURCE_BYTES, duration_bytes)
    estimate = for_source(source_size, duration_seconds=duration)
    return {**estimate, "source_size_confidence": confidence}
