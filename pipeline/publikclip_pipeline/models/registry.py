"""Model weight registry + verified downloader.

All weights land in PUBLIKCLIP_HOME/models/<name>. Managed entries require a
concrete SHA-256 pin and are installed through a staged, bounded download.
Whisper weights are fetched internally by faster-whisper and remain outside
this explicit registry boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import config, runtime

ProgressFn = Callable[[float, str], None]


@dataclass(frozen=True)
class ModelSpec:
    name: str            # registry key + subdir name
    filename: str
    url: str
    sha256: str | None = None
    approx_mb: int = 0
    revision: str = "unversioned"
    license: str = "See upstream source"


REGISTRY: dict[str, ModelSpec] = {}


def register(spec: ModelSpec) -> ModelSpec:
    REGISTRY[f"{spec.name}/{spec.filename}"] = spec
    return spec


def model_path(spec: ModelSpec) -> Path:
    return config.models_dir() / spec.name / spec.filename


def is_present(spec: ModelSpec) -> bool:
    return model_path(spec).exists()


def ensure(spec: ModelSpec, progress: ProgressFn) -> Path:
    """Download, verify, and atomically install one pinned model artifact."""
    if not spec.sha256:
        raise RuntimeError(
            f"Model {spec.name} has no release SHA-256 pin; refusing an unverified download."
        )
    dest = model_path(spec)
    if dest.exists():
        try:
            if runtime.sha256_file(dest).lower() == spec.sha256.lower():
                return dest
        except OSError:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    label = f"Downloading {spec.name}" + (f" (~{spec.approx_mb} MB)" if spec.approx_mb else "")
    try:
        return runtime.download_verified(
            spec.url,
            dest,
            expected_sha256=spec.sha256,
            max_bytes=max(2 * 1024 * 1024 * 1024, (spec.approx_mb or 1) * 1024 * 1024 * 3),
            timeout=config.HTTP_TIMEOUT,
            progress=lambda fraction, _: progress(fraction, label),
        )
    except runtime.RuntimeIntegrityError as exc:
        raise RuntimeError(f"Model {spec.name} failed verification: {exc}") from exc
