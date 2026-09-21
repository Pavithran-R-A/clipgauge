"""Collection artifact contract and validation."""

from __future__ import annotations

import re
import uuid
from typing import Any

COLLECTIONS_SCHEMA_VERSION = 1
COLLECTION_TITLE_LIMIT = 120
COLLECTION_SUMMARY_LIMIT = 240
MAX_COLLECTIONS = 8
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def collection_path(job_dir):
    return job_dir / "collections.json"


def safe_name(value: str) -> str:
    cleaned = _SAFE_NAME.sub("-", str(value).strip()).strip("-.")
    return cleaned[:80] or "collection"


def collection_id() -> str:
    return "collection-" + uuid.uuid4().hex[:12]


def validate_collection(value: Any, valid_clip_ids: set[str], *, require_two: bool = True) -> dict:
    if not isinstance(value, dict):
        raise ValueError("collection must be an object")
    identifier = str(value.get("id", ""))
    title = " ".join(str(value.get("title", "")).split())
    clip_ids = value.get("clip_ids")
    if not identifier or not title or not isinstance(clip_ids, list):
        raise ValueError("collection requires id, title, and clip_ids")
    normalized = [str(item) for item in clip_ids]
    if require_two and len(normalized) < 2:
        raise ValueError("collection requires at least two clips")
    if len(set(normalized)) != len(normalized):
        raise ValueError("collection clip_ids must be unique")
    if any(item not in valid_clip_ids for item in normalized):
        raise ValueError("collection references an unknown clip")
    return {
        "id": identifier,
        "title": title[:COLLECTION_TITLE_LIMIT],
        "clip_ids": normalized,
        "source": str(value.get("source", "manual")),
        "user_edited": bool(value.get("user_edited", False)),
        "summary": " ".join(str(value.get("summary", "")).split())[:COLLECTION_SUMMARY_LIMIT],
        "render_path": value.get("render_path"),
    }
