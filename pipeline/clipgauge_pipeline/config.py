"""Managed paths, timeouts, and versioned per-job settings snapshots.

Everything lives under CLIPGAUGE_HOME (default ~/.clipgauge). A job snapshot
contains provider identity and capability metadata but never provider secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def legacy_home_dir() -> Path:
    """Read-only source root for the one-time upstream data migration."""
    return Path(os.environ.get("PUBLIKCLIP_HOME", str(Path.home() / ".publikclip")))


def home_dir() -> Path:
    return Path(os.environ.get("CLIPGAUGE_HOME", str(Path.home() / ".clipgauge")))


def jobs_dir() -> Path:
    return home_dir() / "jobs"


def bin_dir() -> Path:
    """Legacy executable root retained for non-destructive migration."""
    return home_dir() / "bin"


def runtimes_dir() -> Path:
    return home_dir() / "runtimes"


def data_dir() -> Path:
    return home_dir() / "data"


def nltk_data_dir() -> Path:
    return data_dir() / "nltk"


def models_dir() -> Path:
    return home_dir() / "models"


def db_path() -> Path:
    return home_dir() / "db.sqlite3"


def ensure_home() -> Path:
    root = home_dir()
    for d in (root, jobs_dir(), bin_dir(), runtimes_dir(), data_dir(), nltk_data_dir(), models_dir()):
        d.mkdir(parents=True, exist_ok=True)
    return root


HTTP_TIMEOUT = 60.0
SUBPROCESS_INACTIVITY_TIMEOUT = 120.0
PROBE_TIMEOUT = 60.0
MAX_HEIGHT = 1080
AUDIO_SR = 16_000


@dataclass
class CameraSettings:
    """User-facing camera preset knobs."""

    speaker_change: str = "cut"
    pan_duration_s: float = 0.6
    deadzone_frac: float = 0.05
    punch_in: bool = True
    punch_in_sensitivity: float = 1.0
    zoom_lock_per_scene: bool = True


def _legacy_provider_snapshot(llm_mode: str, model: str | None = None) -> dict[str, Any]:
    if llm_mode == "ollama":
        return {
            "schema_version": 1,
            "id": "legacy-ollama",
            "kind": "ollama",
            "model": model or "auto",
            "endpoint_identity": "http://127.0.0.1:11434",
            "capabilities": {
                "text": True,
                "structured_json": True,
                "json_schema": None,
                "vision": None,
                "model_listing": True,
                "local": True,
                "cloud": False,
            },
        }
    return {
        "schema_version": 1,
        "id": "legacy-gemini",
        "kind": "gemini",
        "model": model or "gemini-flash-latest",
        "endpoint_identity": "https://generativelanguage.googleapis.com/v1beta",
        "capabilities": {
            "text": True,
            "structured_json": True,
            "json_schema": True,
            "vision": True,
            "model_listing": True,
            "local": False,
            "cloud": True,
        },
    }


@dataclass
class Settings:
    """Per-job settings snapshot; resume never silently changes provider/model."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    lufs_target: float = -14.0
    true_peak_db: float = -1.0
    llm_mode: str = "gemini"  # legacy compatibility field
    provider_profile_id: str | None = None
    provider_kind: str | None = None
    provider_model: str | None = None
    provider_endpoint_identity: str | None = None
    provider_capabilities: dict[str, Any] = field(default_factory=dict)
    provider_auth_strategy: str = "none"
    provider_locality: str = "cloud"
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    provider_schema_version: int = 0
    cookies_from_browser: str | None = None
    caption_preset: str = "classic"
    laughter_specialist: bool = False

    def provider_snapshot(self) -> dict[str, Any]:
        if self.provider_profile_id and self.provider_kind and self.provider_model:
            return {
                "schema_version": self.provider_schema_version or 1,
                "id": self.provider_profile_id,
                "kind": self.provider_kind,
                "model": self.provider_model,
                "endpoint_identity": self.provider_endpoint_identity or "",
                "capabilities": dict(self.provider_capabilities),
                "auth_strategy": self.provider_auth_strategy,
                "locality": self.provider_locality,
                "metadata": dict(self.provider_metadata),
            }
        return _legacy_provider_snapshot(self.llm_mode, self.provider_model)

    def to_json(self) -> dict[str, Any]:
        snapshot = self.provider_snapshot()
        return {
            "settings_schema_version": 2,
            "camera": self.camera.__dict__.copy(),
            "lufs_target": self.lufs_target,
            "true_peak_db": self.true_peak_db,
            "llm_mode": self.llm_mode,
            "provider_snapshot": snapshot,
            "provider_profile_id": snapshot["id"],
            "provider_kind": snapshot["kind"],
            "provider_model": snapshot["model"],
            "provider_endpoint_identity": snapshot["endpoint_identity"],
            "provider_capabilities": dict(snapshot.get("capabilities", {})),
            "provider_auth_strategy": snapshot.get("auth_strategy", "none"),
            "provider_locality": snapshot.get("locality", "cloud"),
            "provider_metadata": dict(snapshot.get("metadata", {})),
            "provider_schema_version": int(snapshot.get("schema_version", 1)),
            "cookies_from_browser": self.cookies_from_browser,
            "caption_preset": self.caption_preset,
            "laughter_specialist": self.laughter_specialist,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Settings":
        cam = CameraSettings(**data.get("camera", {}))
        legacy_mode = str(data.get("llm_mode", "gemini"))
        snapshot = data.get("provider_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {
                "schema_version": data.get("provider_schema_version", 1),
                "id": data.get("provider_profile_id"),
                "kind": data.get("provider_kind"),
                "model": data.get("provider_model"),
                "endpoint_identity": data.get("provider_endpoint_identity"),
                "capabilities": data.get("provider_capabilities", {}),
            }
        if not snapshot.get("id") or not snapshot.get("kind") or not snapshot.get("model"):
            snapshot = _legacy_provider_snapshot(legacy_mode)
        kind = str(snapshot.get("kind", legacy_mode))
        return cls(
            camera=cam,
            lufs_target=data.get("lufs_target", -14.0),
            true_peak_db=data.get("true_peak_db", -1.0),
            llm_mode=legacy_mode if legacy_mode in {"gemini", "ollama"} else kind,
            provider_profile_id=str(snapshot["id"]),
            provider_kind=kind,
            provider_model=str(snapshot["model"]),
            provider_endpoint_identity=str(snapshot.get("endpoint_identity", "")),
            provider_capabilities=dict(snapshot.get("capabilities", {})),
            provider_auth_strategy=str(snapshot.get("auth_strategy", "none")),
            provider_locality=str(snapshot.get("locality", "cloud")),
            provider_metadata=dict(snapshot.get("metadata", {})),
            provider_schema_version=int(snapshot.get("schema_version", 1)),
            cookies_from_browser=data.get("cookies_from_browser"),
            caption_preset=data.get("caption_preset", "classic"),
            laughter_specialist=data.get("laughter_specialist", False),
        )
