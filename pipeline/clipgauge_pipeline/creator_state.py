"""Persistent creator-owned state for titles and future review controls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .enrich.stage import stable_clip_id
from .jobs.queue import _atomic_write_json

CREATOR_OVERRIDE_SCHEMA_VERSION = 1
TITLE_LIMIT = 120


def _path(job) -> Any:
    return job.dir / "creator-overrides.json"


def clip_id_for(clip: dict[str, Any], index: int) -> str:
    existing = str(clip.get("clip_id", "")).strip()
    return existing or stable_clip_id(clip, index)


def _stage_clips(job, stage_name: str) -> list[dict[str, Any]]:
    try:
        value = json.loads((job.dir / f"{stage_name}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    data = value.get("data") if isinstance(value, dict) else None
    clips = data.get("clips") if isinstance(data, dict) else None
    return [dict(item) for item in clips if isinstance(item, dict)] if isinstance(clips, list) else []


def _stage_outputs(job) -> list[dict[str, Any]]:
    try:
        value = json.loads((job.dir / "render.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    data = value.get("data") if isinstance(value, dict) else None
    outputs = data.get("outputs") if isinstance(data, dict) else None
    return [dict(item) for item in outputs if isinstance(item, dict)] if isinstance(outputs, list) else []


def _merged_clip_stages(score: list[dict[str, Any]], enrich: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not score:
        return [dict(clip) for clip in enrich]
    if not enrich:
        return [dict(clip) for clip in score]

    enriched_by_id = {
        str(clip.get("clip_id")).strip(): clip
        for clip in enrich
        if str(clip.get("clip_id", "")).strip()
    }
    result: list[dict[str, Any]] = []
    for index, score_clip in enumerate(score):
        score_id = str(score_clip.get("clip_id", "")).strip()
        enriched = enriched_by_id.get(score_id)
        if enriched is None:
            enriched = enrich[index] if index < len(enrich) else None
        item = dict(score_clip)
        if enriched is not None:
            preserved_id = score_id or str(enriched.get("clip_id", "")).strip()
            item.update(enriched)
            if preserved_id:
                item["clip_id"] = preserved_id
        result.append(item)
    return result


def _managed_render_path(job, raw: Any) -> str | None:
    if not raw:
        return None
    root = (job.dir / "clips").resolve()
    raw_path = Path(str(raw))
    candidate = (job.dir / raw_path if not raw_path.is_absolute() else raw_path).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return str(candidate)


def _merge_render_outputs(job, clips: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(clip) for clip in clips]
    ids = [str(clip.get("clip_id", "")).strip() for clip in result]
    id_positions: dict[str, list[int]] = {}
    for index, identifier in enumerate(ids):
        if identifier:
            id_positions.setdefault(identifier, []).append(index)
    output_ids = [str(output.get("clip_id", "")).strip() for output in outputs]
    output_id_counts = {identifier: output_ids.count(identifier) for identifier in set(output_ids) if identifier}
    index_counts: dict[int, int] = {}
    for output in outputs:
        clip_index = output.get("clip")
        if isinstance(clip_index, int) and not isinstance(clip_index, bool):
            index_counts[clip_index] = index_counts.get(clip_index, 0) + 1

    for output in outputs:
        target_index: int | None = None
        output_id = str(output.get("clip_id", "")).strip()
        if output_id and output_id_counts.get(output_id) == 1 and len(id_positions.get(output_id, [])) == 1:
            target_index = id_positions[output_id][0]
        else:
            clip_index = output.get("clip")
            if (
                isinstance(clip_index, int)
                and not isinstance(clip_index, bool)
                and index_counts.get(clip_index) == 1
                and 0 <= clip_index < len(result)
            ):
                target_index = clip_index
        if target_index is None:
            continue
        render_path = _managed_render_path(job, output.get("path") or output.get("render_path"))
        if render_path:
            result[target_index]["render_path"] = render_path
    return result


def creator_clips_for_job(job) -> list[dict[str, Any]]:
    """Load creator clips across legacy and current checkpoints."""
    clips = _merged_clip_stages(_stage_clips(job, "score"), _stage_clips(job, "enrich"))
    normalized = []
    for index, clip in enumerate(clips):
        item = dict(clip)
        item["clip_id"] = clip_id_for(item, index)
        normalized.append(item)
    return _merge_render_outputs(job, normalized, _stage_outputs(job))


def _empty(job) -> dict[str, Any]:
    return {
        "schema_version": CREATOR_OVERRIDE_SCHEMA_VERSION,
        "job_id": job.id,
        "clips": {},
    }


def load_title_overrides(job) -> dict[str, Any]:
    path = _path(job)
    if not path.exists():
        return _empty(job)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("creator title overrides are malformed") from exc
    if not isinstance(value, dict) or value.get("schema_version") != CREATOR_OVERRIDE_SCHEMA_VERSION:
        raise ValueError("unsupported creator title override schema")
    clips = value.get("clips")
    if not isinstance(clips, dict):
        raise ValueError("creator title overrides are malformed")
    normalized: dict[str, dict[str, str]] = {}
    for clip_id, entry in clips.items():
        if not isinstance(entry, dict):
            raise ValueError("creator title override entry is malformed")
        title = " ".join(str(entry.get("title", "")).split())
        if not title or len(title) > TITLE_LIMIT:
            raise ValueError("creator title override title is invalid")
        normalized[str(clip_id)] = {
            "title": title,
            "updated_at": str(entry.get("updated_at", "")),
        }
    return {
        "schema_version": CREATOR_OVERRIDE_SCHEMA_VERSION,
        "job_id": job.id,
        "clips": normalized,
    }


def _valid_clip_ids(clips: list[dict[str, Any]]) -> set[str]:
    return {clip_id_for(clip, index) for index, clip in enumerate(clips)}


def _normalize_title(title: str) -> str:
    normalized = " ".join(str(title).split())
    if not normalized:
        raise ValueError("title cannot be blank")
    if len(normalized) > TITLE_LIMIT:
        raise ValueError(f"title length exceeds {TITLE_LIMIT} characters")
    return normalized


def set_title_override(job, clip_id: str, title: str, clips: list[dict[str, Any]]) -> dict[str, str]:
    identifier = str(clip_id).strip()
    if identifier not in _valid_clip_ids(clips):
        raise ValueError("unknown clip ID")
    normalized = _normalize_title(title)
    value = load_title_overrides(job)
    entry = {
        "title": normalized,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    value["clips"][identifier] = entry
    _atomic_write_json(_path(job), value)
    return dict(entry)


def reset_title_override(job, clip_id: str, clips: list[dict[str, Any]]) -> dict[str, Any]:
    identifier = str(clip_id).strip()
    if identifier not in _valid_clip_ids(clips):
        raise ValueError("unknown clip ID")
    value = load_title_overrides(job)
    value["clips"].pop(identifier, None)
    _atomic_write_json(_path(job), value)
    return value


def apply_title_overrides(clips: list[dict[str, Any]], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    entries = overrides.get("clips", {}) if isinstance(overrides, dict) else {}
    if not isinstance(entries, dict):
        return [dict(clip) for clip in clips]
    result: list[dict[str, Any]] = []
    for index, clip in enumerate(clips):
        item = dict(clip)
        identifier = clip_id_for(item, index)
        entry = entries.get(identifier)
        if isinstance(entry, dict) and entry.get("title"):
            item["clip_id"] = identifier
            item["title"] = str(entry["title"])
            item["title_source"] = "user"
        result.append(item)
    return result
