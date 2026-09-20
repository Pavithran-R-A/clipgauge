"""Atomic collection operations over job-local JSON."""

from __future__ import annotations

import json
from typing import Any

from .. import protocol
from ..enrich.stage import stable_clip_id
from .model import COLLECTIONS_SCHEMA_VERSION, collection_id, collection_path, validate_collection


def _atomic_write(path, payload) -> None:
    from ..jobs.queue import _atomic_write_json

    _atomic_write_json(path, payload)


def _load(job, clips: list[dict] | None = None) -> dict:
    path = collection_path(job.dir)
    if not path.exists():
        return {"schema_version": COLLECTIONS_SCHEMA_VERSION, "job_id": job.id, "collections": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"collections cannot be read: {protocol.safe_message(str(exc))}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != COLLECTIONS_SCHEMA_VERSION:
        raise ValueError("unsupported collections schema")
    valid = {stable_clip_id(clip, index) for index, clip in enumerate(clips or [])}
    value["collections"] = [validate_collection(item, valid) for item in value.get("collections", [])]
    return value


def _save(job, value: dict, clips: list[dict] | None = None) -> dict:
    valid = {stable_clip_id(clip, index) for index, clip in enumerate(clips or [])}
    normalized = {
        "schema_version": COLLECTIONS_SCHEMA_VERSION,
        "job_id": job.id,
        "collections": [validate_collection(item, valid) for item in value.get("collections", [])],
    }
    _atomic_write(collection_path(job.dir), normalized)
    return normalized


def list_collections(job, clips: list[dict] | None = None) -> list[dict]:
    return _load(job, clips).get("collections", [])


def create_collection(job, title: str, clip_ids: list[str], *, clips: list[dict] | None = None, source: str = "manual") -> dict:
    value = _load(job, clips)
    item = {"id": collection_id(), "title": title, "clip_ids": clip_ids, "source": source, "user_edited": source == "manual"}
    value["collections"].append(item)
    normalized = _save(job, value, clips)
    return normalized["collections"][-1]


def update_collection(job, identifier: str, *, title: str | None = None, clip_ids: list[str] | None = None, clips: list[dict] | None = None) -> dict:
    value = _load(job, clips)
    for item in value["collections"]:
        if item["id"] == identifier:
            if title is not None:
                item["title"] = title
            if clip_ids is not None:
                item["clip_ids"] = clip_ids
            item["user_edited"] = True
            _save(job, value, clips)
            return next(row for row in _load(job, clips)["collections"] if row["id"] == identifier)
    raise ValueError("collection not found")


def reorder_collection(job, identifier: str, clip_ids: list[str], *, clips: list[dict] | None = None) -> dict:
    return update_collection(job, identifier, clip_ids=clip_ids, clips=clips)


def delete_collection(job, identifier: str, *, clips: list[dict] | None = None) -> None:
    value = _load(job, clips)
    value["collections"] = [item for item in value["collections"] if item["id"] != identifier]
    _save(job, value, clips)


def regenerate_ai_collections(job, clips: list[dict], *, category: str = "auto") -> list[dict]:
    """Create deterministic proposals from existing finalists.

    The proposal is intentionally bounded. It never invents clip IDs and
    never overwrites user-edited collections.
    """
    valid_ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    if not valid_ids:
        return []
    existing = _load(job, clips)["collections"]
    preserved = [item for item in existing if item.get("user_edited")]
    if preserved:
        return preserved
    title = f"{category.title()} highlights" if category != "auto" else "Highlights"
    proposal = {"id": collection_id(), "title": title, "clip_ids": valid_ids, "source": "ai", "user_edited": False}
    result = _save(job, {"collections": [proposal]}, clips)
    return result["collections"]
