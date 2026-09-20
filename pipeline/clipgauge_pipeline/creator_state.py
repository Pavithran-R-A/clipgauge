"""Persistent creator-owned state for titles and future review controls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
