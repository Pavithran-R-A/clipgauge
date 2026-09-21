"""Versioned job input manifests.

The manifest separates source selection from provider settings. Accepted
artifacts live inside the managed job directory, so resume does not depend on
external files remaining at their original paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .. import protocol
from .platforms import classify_source

MANIFEST_SCHEMA_VERSION = 1


def default_manifest(source_type: str, source: str) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "media": {
            "source_type": source_type,
            "source": source,
            "platform": "local" if source_type == "file" else classify_source(source).value,
        },
        "subtitle": {
            "mode": "asr",
            "requested_path": None,
            "artifact_path": None,
            "format": None,
            "language": None,
            "source": "asr",
            "extractor": None,
            "sha256": None,
            "automatic": False,
        },
    }


def validate_manifest(value: Any, *, source_type: str, source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("input manifest must be an object")
    if int(value.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported input manifest schema")
    media = value.get("media")
    subtitle = value.get("subtitle")
    if not isinstance(media, dict) or not isinstance(subtitle, dict):
        raise ValueError("input manifest requires media and subtitle objects")
    if media.get("source_type") != source_type or media.get("source") != source:
        raise ValueError("input manifest media does not match the job")
    mode = str(subtitle.get("mode", "asr"))
    if mode not in {"auto", "external", "platform", "asr"}:
        raise ValueError("unsupported subtitle mode")
    normalized = default_manifest(source_type, source)
    normalized["media"] = {
        **normalized["media"],
        "platform": str(media.get("platform") or normalized["media"]["platform"]),
    }
    normalized["subtitle"] = {
        **normalized["subtitle"],
        **{key: subtitle.get(key) for key in normalized["subtitle"]},
    }
    if normalized["subtitle"]["requested_path"] is not None:
        normalized["subtitle"]["requested_path"] = str(normalized["subtitle"]["requested_path"])
    if normalized["subtitle"]["artifact_path"] is not None:
        normalized["subtitle"]["artifact_path"] = str(normalized["subtitle"]["artifact_path"])
    return normalized


def manifest_path(job_dir: Path) -> Path:
    return job_dir / "input.json"


def load(job_dir: Path, *, source_type: str, source: str) -> dict[str, Any]:
    path = manifest_path(job_dir)
    if not path.exists():
        return default_manifest(source_type, source)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"input manifest cannot be read: {protocol.safe_message(str(exc))}") from exc
    return validate_manifest(value, source_type=source_type, source=source)


def persist(job, value: dict[str, Any]) -> None:
    from ..jobs import queue

    normalized = validate_manifest(value, source_type=job.source_type, source=job.source)
    queue._atomic_write_json(manifest_path(job.dir), normalized)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    with queue._connect() as conn:
        conn.execute("UPDATE jobs SET input_json = ? WHERE id = ?", (encoded, job.id))
    job.input_json = encoded


def load_from_job(job) -> dict[str, Any]:
    value = load(job.dir, source_type=job.source_type, source=job.source)
    if value.get("subtitle", {}).get("mode") == "asr":
        try:
            if job.input_json:
                value = validate_manifest(json.loads(job.input_json), source_type=job.source_type, source=job.source)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
