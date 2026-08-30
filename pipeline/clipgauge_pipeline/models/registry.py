"""Model weight registry + verified downloader.

All weights land in CLIPGAUGE_HOME/models/<name>. Managed entries require a
concrete SHA-256 pin and are installed through a staged, bounded download.
Whisper weights are fetched internally by faster-whisper and remain outside
this explicit registry boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import config, downloads, runtime

ProgressFn = Callable[[float, str], None]


@dataclass(frozen=True)
class ModelSpec:
    name: str            # registry key + subdir name
    filename: str
    url: str
    sha256: str | None = None
    approx_mb: int = 0
    size_bytes: int = 0
    revision: str = "unversioned"
    license: str = "See upstream source"


REGISTRY: dict[str, ModelSpec] = {}


def register(spec: ModelSpec) -> ModelSpec:
    REGISTRY[f"{spec.name}/{spec.filename}"] = spec
    return spec


def model_path(spec: ModelSpec) -> Path:
    return config.models_dir() / spec.name / spec.filename


def require_verified_model(spec: ModelSpec, candidate: str | Path) -> Path:
    """Return a model path only when identity and bytes match the registry."""
    expected = model_path(spec).resolve()
    path = Path(candidate).expanduser().resolve()
    if path != expected:
        raise runtime.RuntimeIntegrityError(
            f"model path is outside the approved registry path for {spec.name}"
        )
    if not path.is_file():
        raise runtime.RuntimeIntegrityError(f"managed model is missing: {spec.name}")
    if spec.size_bytes > 0 and path.stat().st_size != spec.size_bytes:
        raise runtime.RuntimeIntegrityError(f"managed model size mismatch: {spec.name}")
    if not spec.sha256 or runtime.sha256_file(path).lower() != spec.sha256.lower():
        raise runtime.RuntimeIntegrityError(f"managed model hash mismatch: {spec.name}")
    return path


def is_present(spec: ModelSpec) -> bool:
    return model_path(spec).exists()


def managed_asset(spec: ModelSpec) -> downloads.ManagedAsset:
    if not spec.sha256:
        raise RuntimeError(f"Model {spec.name} has no release SHA-256 pin; refusing an unverified download.")
    return downloads.ManagedAsset(
        asset_id=f"model:{spec.name}:{spec.filename}",
        display_name=spec.name.replace("-", " ").title(),
        purpose="ClipGauge analysis and creator workflow",
        destination=str(model_path(spec).relative_to(config.home_dir())),
        url=spec.url,
        size_bytes=spec.size_bytes,
        sha256=spec.sha256,
        required=True,
        one_time=True,
        license=spec.license,
        source=spec.url,
        consent_group="core:analysis",
        source_revision=spec.revision,
    )


def ensure(spec: ModelSpec, progress: ProgressFn) -> Path:
    """Install one pinned analysis model only after Setup Center consent."""
    asset = managed_asset(spec)
    manager = downloads.DownloadManager(event=lambda payload: progress(float(payload.get("fraction", -1.0) if payload.get("fraction") is not None else -1.0), str(payload.get("message", f"Downloading {spec.name}"))))
    try:
        return manager.download(asset, require_consent=True)
    except downloads.ConsentRequiredError as exc:
        raise RuntimeError(
            f"Analysis asset {spec.name} is not installed. Open Setup Center and approve the Analysis components group."
        ) from exc
    except (runtime.RuntimeIntegrityError, runtime.RuntimeDiskSpaceError) as exc:
        raise RuntimeError(f"Model {spec.name} failed verification: {exc}") from exc
