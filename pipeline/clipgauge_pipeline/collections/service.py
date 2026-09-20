"""Atomic creator collection operations over job-local JSON."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .. import protocol
from ..creator_state import clip_id_for
from .model import (
    COLLECTIONS_SCHEMA_VERSION,
    COLLECTION_TITLE_LIMIT,
    collection_id,
    collection_path,
    validate_collection,
)
from .smart import SMART_COLLECTION_SCHEMA, build_grouping_prompt

GroupProvider = Callable[[str, dict[str, Any]], dict[str, Any]]


def _atomic_write(path, payload) -> None:
    from ..jobs.queue import _atomic_write_json

    _atomic_write_json(path, payload)


def _empty(job) -> dict[str, Any]:
    return {"schema_version": COLLECTIONS_SCHEMA_VERSION, "job_id": job.id, "collections": []}


def _valid_ids(clips: list[dict] | None) -> list[str]:
    return [clip_id_for(clip, index) for index, clip in enumerate(clips or [])]


def _normalize_title(title: str) -> str:
    normalized = " ".join(str(title).split())
    if not normalized:
        raise ValueError("collection title cannot be blank")
    if len(normalized) > COLLECTION_TITLE_LIMIT:
        raise ValueError(f"collection title length exceeds {COLLECTION_TITLE_LIMIT} characters")
    return normalized


def _validate_requested_clip_ids(clip_ids: list[str], valid_ids: list[str]) -> list[str]:
    normalized = [str(item).strip() for item in clip_ids]
    if len(normalized) < 2:
        raise ValueError("collection requires at least two clips")
    if len(set(normalized)) != len(normalized):
        raise ValueError("collection clip IDs must be unique")
    if any(identifier not in set(valid_ids) for identifier in normalized):
        raise ValueError("collection references an unknown clip")
    return normalized


def _load(job, clips: list[dict] | None = None) -> dict[str, Any]:
    path = collection_path(job.dir)
    if not path.exists():
        return _empty(job)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"collections cannot be read: {protocol.safe_message(str(exc))}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != COLLECTIONS_SCHEMA_VERSION:
        raise ValueError("unsupported collections schema")
    rows = value.get("collections")
    if not isinstance(rows, list):
        raise ValueError("collections are malformed")
    valid = set(_valid_ids(clips))
    return {
        "schema_version": COLLECTIONS_SCHEMA_VERSION,
        "job_id": job.id,
        "collections": [validate_collection(item, valid, require_two=False) for item in rows],
    }


def _save(job, value: dict[str, Any], clips: list[dict] | None = None) -> dict[str, Any]:
    valid = set(_valid_ids(clips))
    rows = value.get("collections", [])
    if not isinstance(rows, list):
        raise ValueError("collections are malformed")
    normalized = {
        "schema_version": COLLECTIONS_SCHEMA_VERSION,
        "job_id": job.id,
        "collections": [validate_collection(item, valid, require_two=False) for item in rows],
    }
    _atomic_write(collection_path(job.dir), normalized)
    return normalized


def list_collections(job, clips: list[dict] | None = None) -> list[dict]:
    return list(_load(job, clips).get("collections", []))


def set_collection_render_path(job, identifier: str, render_path: str, *, clips: list[dict] | None = None) -> dict:
    value = _load(job, clips)
    rows = []
    found = False
    for item in value["collections"]:
        if item["id"] != identifier:
            rows.append(item)
            continue
        found = True
        rows.append({**item, "render_path": str(render_path)})
    if not found:
        raise ValueError("collection not found")
    normalized = _save(job, {**value, "collections": rows}, clips)
    return next(row for row in normalized["collections"] if row["id"] == identifier)


def create_collection(
    job,
    title: str,
    clip_ids: list[str],
    *,
    clips: list[dict] | None = None,
    source: str = "manual",
    summary: str = "",
) -> dict:
    valid_ids = _valid_ids(clips)
    normalized_ids = _validate_requested_clip_ids(clip_ids, valid_ids)
    normalized_title = _normalize_title(title)
    if source not in {"manual", "ai", "deterministic"}:
        raise ValueError("collection source is invalid")
    value = _load(job, clips)
    item = {
        "id": collection_id(),
        "title": normalized_title,
        "summary": " ".join(str(summary).split())[:240],
        "clip_ids": normalized_ids,
        "source": source,
        "user_edited": source == "manual",
    }
    normalized = _save(job, {**value, "collections": [*value["collections"], item]}, clips)
    return dict(normalized["collections"][-1])


def update_collection(
    job,
    identifier: str,
    *,
    title: str | None = None,
    clip_ids: list[str] | None = None,
    clips: list[dict] | None = None,
) -> dict:
    value = _load(job, clips)
    if title is None and clip_ids is None:
        raise ValueError("collection update requires title or clip IDs")
    rows = []
    found = False
    valid_ids = _valid_ids(clips)
    for item in value["collections"]:
        if item["id"] != identifier:
            rows.append(item)
            continue
        found = True
        changed = dict(item)
        if title is not None:
            changed["title"] = _normalize_title(title)
        if clip_ids is not None:
            changed["clip_ids"] = _validate_requested_clip_ids(clip_ids, valid_ids)
        changed["user_edited"] = True
        changed["source"] = "manual"
        rows.append(changed)
    if not found:
        raise ValueError("collection not found")
    normalized = _save(job, {**value, "collections": rows}, clips)
    return next(row for row in normalized["collections"] if row["id"] == identifier)


def reorder_collection(job, identifier: str, clip_ids: list[str], *, clips: list[dict] | None = None) -> dict:
    return update_collection(job, identifier, clip_ids=clip_ids, clips=clips)


def delete_collection(job, identifier: str, *, clips: list[dict] | None = None) -> None:
    value = _load(job, clips)
    rows = [item for item in value["collections"] if item["id"] != identifier]
    if len(rows) == len(value["collections"]):
        raise ValueError("collection not found")
    _save(job, {**value, "collections": rows}, clips)


def _provider_collections(payload: Any, valid_ids: list[str]) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("collections"), list):
        raise ValueError("grouping response is malformed")
    if len(payload["collections"]) > 8:
        raise ValueError("grouping response contains too many collections")
    order = {identifier: index for index, identifier in enumerate(valid_ids)}
    seen: set[str] = set()
    rows: list[dict] = []
    for raw in payload["collections"]:
        if not isinstance(raw, dict):
            raise ValueError("grouping collection is malformed")
        title = _normalize_title(raw.get("title", ""))
        summary = " ".join(str(raw.get("summary", "")).split())[:240]
        clip_ids = raw.get("clip_ids")
        if not isinstance(clip_ids, list):
            raise ValueError("grouping clip IDs are malformed")
        normalized_ids = _validate_requested_clip_ids(clip_ids, valid_ids)
        if seen.intersection(normalized_ids):
            raise ValueError("grouping duplicates a clip")
        seen.update(normalized_ids)
        normalized_ids = sorted(normalized_ids, key=order.__getitem__)
        rows.append({
            "id": collection_id(),
            "title": title,
            "summary": summary,
            "clip_ids": normalized_ids,
            "source": "ai",
            "user_edited": False,
        })
    return rows


def _deterministic_fallback(valid_ids: list[str]) -> list[dict]:
    if len(valid_ids) < 2:
        return []
    return [{
        "id": collection_id(),
        "title": "Highlights",
        "summary": "Selected finalists grouped deterministically.",
        "clip_ids": list(valid_ids),
        "source": "deterministic",
        "user_edited": False,
    }]


def regenerate_smart_collections(
    job,
    clips: list[dict],
    *,
    category: str = "auto",
    group_provider: GroupProvider | None = None,
) -> list[dict]:
    valid_ids = _valid_ids(clips)
    existing = _load(job, clips)["collections"]
    preserved = [dict(item) for item in existing if item.get("user_edited")]
    if len(valid_ids) < 2:
        return preserved
    suggestions: list[dict]
    if group_provider is None:
        suggestions = _deterministic_fallback(valid_ids)
    else:
        try:
            payload = group_provider(build_grouping_prompt(clips, category), SMART_COLLECTION_SCHEMA)
            suggestions = _provider_collections(payload, valid_ids)
        except Exception:
            suggestions = _deterministic_fallback(valid_ids)
    normalized = _save(job, {"collections": [*preserved, *suggestions]}, clips)
    return list(normalized["collections"])


def regenerate_ai_collections(job, clips: list[dict], *, category: str = "auto") -> list[dict]:
    """Compatibility wrapper with truthful deterministic labeling."""

    return regenerate_smart_collections(job, clips, category=category)
