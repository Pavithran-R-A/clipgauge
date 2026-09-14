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


def for_stage(stage: str, estimate: Mapping[str, object] | None) -> dict[str, int | float | str | None]:
    """Estimate only the storage remaining for an active stage."""
    normalized = stage.strip().lower()
    if normalized == "ingest":
        return dict(estimate or for_url_metadata(None))

    source = estimate or {}
    if normalized == "asr":
        working_bytes = CHECKPOINT_BYTES
        safety_bytes = max(MIN_SAFETY_BYTES, math.ceil(working_bytes * SAFETY_FRACTION))
        return {
            "source_bytes": _positive_number(source.get("source_bytes")),
            "source_copy_bytes": 0,
            "duration_seconds": source.get("duration_seconds"),
            "temporary_audio_bytes": 0,
            "checkpoint_bytes": CHECKPOINT_BYTES,
            "render_bytes": 0,
            "safety_margin_bytes": safety_bytes,
            "required_bytes": working_bytes + safety_bytes,
            "source_size_confidence": source.get("source_size_confidence"),
        }

    if normalized == "render":
        render_bytes = max(MIN_RENDER_BYTES, _positive_number(source.get("render_bytes")) or MIN_RENDER_BYTES)
        working_bytes = CHECKPOINT_BYTES + render_bytes
        safety_bytes = max(MIN_SAFETY_BYTES, math.ceil(working_bytes * SAFETY_FRACTION))
        return {
            "source_bytes": _positive_number(source.get("source_bytes")),
            "source_copy_bytes": 0,
            "duration_seconds": source.get("duration_seconds"),
            "temporary_audio_bytes": 0,
            "checkpoint_bytes": CHECKPOINT_BYTES,
            "render_bytes": render_bytes,
            "safety_margin_bytes": safety_bytes,
            "required_bytes": working_bytes + safety_bytes,
            "source_size_confidence": source.get("source_size_confidence"),
        }

    return dict(source)


def _positive_number(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _selected_format_records(metadata: Mapping[str, object]) -> list[Mapping[str, object]]:
    selected = metadata.get("requested_formats")
    if not isinstance(selected, list):
        return []
    records: list[Mapping[str, object]] = []
    seen: set[tuple[str, object]] = set()
    for item in selected:
        if not isinstance(item, Mapping):
            continue
        format_id = item.get("format_id")
        url = item.get("url")
        identity = ("format_id", format_id) if format_id else ("url", url)
        if identity[1] is not None and identity in seen:
            continue
        if identity[1] is not None:
            seen.add(identity)
        records.append(item)
    return records


def _selected_component_size(records: list[Mapping[str, object]]) -> tuple[int | None, str]:
    if not records:
        return None, "unknown"
    sizes: list[int] = []
    approximate = False
    for record in records:
        exact = _positive_number(record.get("filesize"))
        approx = _positive_number(record.get("filesize_approx"))
        value = exact or approx
        if value is None:
            return None, "unknown"
        sizes.append(value)
        approximate = approximate or exact is None
    return sum(sizes), "approximate" if approximate else "exact"


def _selected_bitrate_bytes(metadata: Mapping[str, object], records: list[Mapping[str, object]]) -> int | None:
    candidates = records or [metadata]
    bitrates: list[int] = []
    for record in candidates:
        total_kbps = _positive_number(record.get("tbr"))
        if total_kbps is None:
            video_kbps = _positive_number(record.get("vbr")) or 0
            audio_kbps = _positive_number(record.get("abr")) or 0
            total_kbps = video_kbps + audio_kbps
        if total_kbps > 0:
            bitrates.append(total_kbps)
    duration = _positive_number(metadata.get("duration"))
    if not bitrates or duration is None:
        return None
    return math.ceil(duration * sum(bitrates) * 1000 / 8)


def _metadata_size(metadata: Mapping[str, object]) -> tuple[int | None, str]:
    exact = _positive_number(metadata.get("filesize"))
    if exact:
        return exact, "exact"
    selected = _selected_format_records(metadata)
    selected_size, selected_confidence = _selected_component_size(selected)
    if selected_size is not None and selected_confidence == "exact":
        return selected_size, "exact"
    approximate = _positive_number(metadata.get("filesize_approx"))
    if approximate:
        return approximate, "approximate"
    if selected_size is not None:
        return selected_size, selected_confidence
    bitrate_size = _selected_bitrate_bytes(metadata, selected)
    if bitrate_size is not None:
        return bitrate_size, "bitrate-estimate"
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
