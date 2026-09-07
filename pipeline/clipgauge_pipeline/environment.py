"""Persistent identity for the managed pipeline environment."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import os
from pathlib import Path
from typing import Any

from . import __version__, config

ENVIRONMENT_ABI_VERSION = "1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UV_LOCK = PROJECT_ROOT / "uv.lock"


def identity_path(data_root: Path | None = None) -> Path:
    return (data_root or config.home_dir()) / "runtime-environment.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected() -> dict[str, Any]:
    pyproject_hash = _digest(PYPROJECT)
    lock_hash = _digest(UV_LOCK)
    payload = {
        "schema_version": 1,
        "environment_abi": ENVIRONMENT_ABI_VERSION,
        "app_version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "pyproject_sha256": pyproject_hash,
        "uv_lock_sha256": lock_hash,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {**payload, "fingerprint": fingerprint}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_identity(data_root: Path | None = None) -> dict[str, Any]:
    payload = expected()
    _write(identity_path(data_root), payload)
    return payload


def status(data_root: Path | None = None) -> dict[str, Any]:
    current = expected()
    path = identity_path(data_root)
    stored: dict[str, Any] | None = None
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                stored = parsed
        except (OSError, ValueError):
            stored = None
    stored_fingerprint = stored.get("fingerprint") if stored else None
    ready = stored_fingerprint == current["fingerprint"]
    return {
        "state": "READY" if ready else "UPDATE_REQUIRED",
        "reason": None if ready else "ClipGauge runtime update required",
        "identity_path": str(path),
        "expected_fingerprint": current["fingerprint"],
        "stored_fingerprint": stored_fingerprint,
        "expected": current,
    }
