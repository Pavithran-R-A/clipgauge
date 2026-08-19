"""Versioned descriptors for files referenced by stage checkpoints.

Checkpoint data stores relative paths under the job root.  Descriptors retain
cheap freshness metadata for every managed file and a hash according to the
policy below:

* Small or non-media files are fully SHA-256 hashed.
* Large audio/video files use a one-time sampled SHA-256 (size plus the first
  and last MiB), avoiding repeated full-media reads while still detecting the
  usual replacement/corruption cases.

A descriptor is never accepted for a path outside the managed job directory,
a directory, a symlink, or a missing/unreadable file.  All critical JSON
writes are performed by the queue's atomic writer.
"""

from __future__ import annotations

import copy
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

DESCRIPTOR_SCHEMA_VERSION = 1
MANIFEST_NAME = "artifact-manifest.json"
SMALL_HASH_LIMIT = 8 * 1024 * 1024
SAMPLE_BYTES = 1024 * 1024
_PATH_KEYS = {"path", "media_path", "audio_path", "curves_path", "ass"}


class ArtifactError(Exception):
    """A checkpoint cannot be safely reused or persisted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_path_key(key: str) -> bool:
    return key in _PATH_KEYS or key.endswith("_path")


def _root(job_dir: Path) -> Path:
    return job_dir.resolve()


def _managed_file(job_dir: Path, value: str, *, for_write: bool) -> tuple[Path, str]:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else job_dir / raw
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ArtifactError("ARTIFACT_MISSING", f"managed artifact is missing: {value}") from exc
    root = _root(job_dir)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ArtifactError(
            "ARTIFACT_OUTSIDE_MANAGED_ROOT",
            "checkpoint references a file outside the managed job root",
        ) from exc
    if candidate.is_symlink():
        raise ArtifactError("ARTIFACT_SYMLINK_REJECTED", "managed artifacts may not be symlinks")
    if not resolved.is_file():
        raise ArtifactError("ARTIFACT_WRONG_TYPE", "managed artifact is not a regular file")
    if not os.access(resolved, os.R_OK):
        raise ArtifactError("ARTIFACT_UNREADABLE", "managed artifact is not readable")
    return resolved, relative.as_posix()


def _digest(path: Path, size: int, *, sampled: bool) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        if sampled:
            hasher.update(handle.read(SAMPLE_BYTES))
            if size > SAMPLE_BYTES:
                handle.seek(max(0, size - SAMPLE_BYTES))
                hasher.update(handle.read(SAMPLE_BYTES))
        else:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    return hasher.hexdigest()


def _descriptor(job_dir: Path, value: str, role: str, producer_stage: str) -> dict[str, Any]:
    path, relative = _managed_file(job_dir, value, for_write=True)
    stat = path.stat()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    sampled = stat.st_size > SMALL_HASH_LIMIT and media_type.startswith(("audio/", "video/"))
    return {
        "schema_version": DESCRIPTOR_SCHEMA_VERSION,
        "relative_path": relative,
        "producer_stage": producer_stage,
        "producer_version": _producer_version(),
        "size": stat.st_size,
        "updated_at": stat.st_mtime_ns,
        "media_type": media_type,
        "role": role,
        "hash_algorithm": "sha256-sampled" if sampled else "sha256",
        "integrity_hash": _digest(path, stat.st_size, sampled=sampled),
    }


def _producer_version() -> str:
    from .. import __version__

    return __version__


def _iter_paths(value: Any, prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if _is_path_key(key_text) and isinstance(child, str):
                yield ".".join(prefix + (key_text,)), child
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _iter_paths(child, prefix + (key_text,))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            if isinstance(child, (Mapping, list, tuple)):
                yield from _iter_paths(child, prefix + (str(index),))


def prepare(job_dir: Path, data: dict[str, Any], stage: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate referenced files and return relative-path checkpoint data."""
    copied = copy.deepcopy(data)
    descriptors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for role, value in _iter_paths(data):
        descriptor = _descriptor(job_dir, value, role, stage)
        key = (descriptor["relative_path"], role)
        if key in seen:
            continue
        seen.add(key)
        descriptors.append(descriptor)
        _replace_path(copied, role.split("."), descriptor["relative_path"])
    return copied, descriptors


def _replace_path(value: Any, parts: list[str], replacement: str) -> None:
    if not parts:
        return
    head, *tail = parts
    if isinstance(value, dict):
        if head not in value:
            return
        if not tail:
            value[head] = replacement
        else:
            _replace_path(value[head], tail, replacement)
    elif isinstance(value, list) and head.isdigit():
        index = int(head)
        if 0 <= index < len(value):
            if not tail:
                value[index] = replacement
            else:
                _replace_path(value[index], tail, replacement)


def restore(job_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Expand managed relative paths for existing stage code after validation."""
    restored = copy.deepcopy(data)
    for role, value in _iter_paths(restored):
        path, _ = _managed_file(job_dir, value, for_write=False)
        _replace_path(restored, role.split("."), str(path))
    return restored


def validate(job_dir: Path, envelope: Mapping[str, Any], stage: str, schema_version: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if envelope.get("stage") != stage:
        raise ArtifactError("CHECKPOINT_STAGE_MISMATCH", "checkpoint stage does not match its filename")
    if envelope.get("schema_version") != schema_version:
        raise ArtifactError("CHECKPOINT_SCHEMA_MISMATCH", "checkpoint schema version is stale")
    if not isinstance(envelope.get("data"), dict):
        raise ArtifactError("CHECKPOINT_MALFORMED", "checkpoint data must be an object")
    descriptors = envelope.get("artifacts")
    if not isinstance(descriptors, list):
        raise ArtifactError("CHECKPOINT_DESCRIPTOR_MISSING", "checkpoint has no versioned artifact descriptors")
    for item in descriptors:
        if not isinstance(item, Mapping):
            raise ArtifactError("CHECKPOINT_MALFORMED", "artifact descriptor is not an object")
        if item.get("schema_version") != DESCRIPTOR_SCHEMA_VERSION:
            raise ArtifactError("ARTIFACT_DESCRIPTOR_STALE", "artifact descriptor schema is stale")
        relative = item.get("relative_path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ArtifactError("ARTIFACT_PATH_INVALID", "artifact descriptor path is not relative to the job root")
        path, actual_relative = _managed_file(job_dir, relative, for_write=False)
        stat = path.stat()
        if actual_relative != relative or stat.st_size != item.get("size") or stat.st_mtime_ns != item.get("updated_at"):
            raise ArtifactError("ARTIFACT_STALE", f"managed artifact is stale: {relative}")
        sampled = item.get("hash_algorithm") == "sha256-sampled"
        if item.get("hash_algorithm") not in {"sha256", "sha256-sampled"}:
            raise ArtifactError("ARTIFACT_HASH_INVALID", "unsupported artifact hash policy")
        if _digest(path, stat.st_size, sampled=sampled) != item.get("integrity_hash"):
            raise ArtifactError("ARTIFACT_HASH_MISMATCH", f"managed artifact failed integrity validation: {relative}")
    manifest = manifest_path(job_dir)
    try:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_entry = manifest_payload["stages"][stage]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ArtifactError("ARTIFACT_MANIFEST_INVALID", "artifact manifest is missing or malformed") from exc
    if manifest_entry.get("schema_version") != schema_version:
        raise ArtifactError("ARTIFACT_MANIFEST_STALE", "artifact manifest schema is stale")
    if manifest_entry.get("artifacts") != descriptors:
        raise ArtifactError("ARTIFACT_MANIFEST_MISMATCH", "artifact manifest does not match the checkpoint")
    _, expected_descriptors = prepare(job_dir, envelope["data"], stage)
    expected = {(d["relative_path"], d["role"]) for d in expected_descriptors}
    actual = {(d.get("relative_path"), d.get("role")) for d in descriptors}
    if expected != actual:
        raise ArtifactError("CHECKPOINT_DESCRIPTOR_MISMATCH", "checkpoint artifact references do not match its descriptor list")
    return restore(job_dir, envelope["data"]), list(descriptors)


def manifest_path(job_dir: Path) -> Path:
    return job_dir / MANIFEST_NAME


def update_manifest(job_dir: Path, stage: str, schema_version: int, descriptors: list[dict[str, Any]], atomic_write) -> None:
    existing: dict[str, Any] = {}
    path = manifest_path(job_dir)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("stages"), dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}
    existing.setdefault("schema_version", DESCRIPTOR_SCHEMA_VERSION)
    existing["updated_at"] = time.time()
    existing.setdefault("job_root", ".")
    stages = existing.setdefault("stages", {})
    stages[stage] = {
        "schema_version": schema_version,
        "producer_stage": stage,
        "producer_version": _producer_version(),
        "artifacts": descriptors,
    }
    atomic_write(path, existing)
