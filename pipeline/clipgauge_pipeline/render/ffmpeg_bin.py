"""FFmpeg resolution and explicit managed installation.

A valid capable system binary is reused.  When none exists, v0.4 exposes an
explicit Setup Center action that downloads a pinned archive through the common
DownloadManager; render never starts a hidden download.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import config, downloads, runtime

_LEGACY_KEG_CANDIDATES = [
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
]
_EXE = ".exe" if platform.system() == "Windows" else ""


@dataclass(frozen=True)
class FFmpegReadiness:
    ready: bool
    source: str
    executable: str | None
    version: str | None
    capabilities: dict[str, bool]
    managed_download_needed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "source": self.source,
            "executable": self.executable,
            "version": self.version,
            "capabilities": dict(self.capabilities),
            "managed_download_needed": self.managed_download_needed,
            "reason": self.reason,
        }


def _manifest() -> dict[str, Any]:
    path = Path(__file__).parents[2] / "runtime-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _platform_asset() -> dict[str, Any] | None:
    manifest = _manifest().get("runtimes", {}).get("ffmpeg", {})
    assets = manifest.get("assets", {})
    if platform.system() == "Windows" and platform.machine().lower() in {"amd64", "x86_64"}:
        return {"key": "win64-gpl", "version": manifest.get("version", "managed"), **assets.get("win64-gpl", {})}
    return None


def _managed_dir() -> Path | None:
    asset = _platform_asset()
    if not asset:
        return None
    return config.runtimes_dir() / "ffmpeg" / str(asset["version"]) / str(asset.get("key", "platform"))


def _probe(binary: str) -> tuple[str | None, dict[str, bool], str]:
    capabilities = {"starts": False, "subtitles": False}
    try:
        version = subprocess.run(
            [binary, "-hide_banner", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        capabilities["starts"] = version.returncode == 0
        version_text = (version.stdout or version.stderr).splitlines()
        version_line = version_text[0].strip() if version_text else None
        filters = subprocess.run(
            [binary, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        filter_text = f"{filters.stdout}\n{filters.stderr}"
        capabilities["subtitles"] = filters.returncode == 0 and any(
            "subtitles" in line.strip().split() for line in filter_text.splitlines()
        )
        if capabilities["starts"] and capabilities["subtitles"]:
            return version_line, capabilities, "Compatible caption-capable FFmpeg."
        if not capabilities["starts"]:
            return version_line, capabilities, "FFmpeg did not start successfully."
        return version_line, capabilities, "FFmpeg is missing the subtitles filter required for caption rendering."
    except subprocess.TimeoutExpired:
        return None, capabilities, "FFmpeg capability probe timed out."
    except OSError as exc:
        return None, capabilities, f"FFmpeg could not be executed: {exc}"


def _has_subtitles_filter(binary: str) -> bool:
    return _probe(binary)[1]["subtitles"]


def _candidates() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    env = os.environ.get("CLIPGAUGE_FFMPEG")
    if env:
        candidates.append(("configured", env))
    managed = _managed_dir()
    if managed:
        candidates.append(("managed", str(managed / f"ffmpeg{_EXE}")))
    candidates.append(("legacy-managed", str(config.bin_dir() / f"ffmpeg{_EXE}")))
    bundled = os.environ.get("CLIPGAUGE_BUNDLED_FFMPEG")
    if bundled:
        candidates.append(("bundled", bundled))
    if platform.system() == "Darwin":
        candidates.extend(("bundled", path) for path in _LEGACY_KEG_CANDIDATES)
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        candidates.append(("system", path_ffmpeg))
    return candidates


@lru_cache(maxsize=1)
def readiness() -> FFmpegReadiness:
    """Return the single capability decision consumed by setup and preflight."""
    managed_available = _platform_asset() is not None
    first_failure: FFmpegReadiness | None = None
    for source, candidate in _candidates():
        if not Path(candidate).is_file():
            continue
        version, capabilities, reason = _probe(candidate)
        if capabilities["starts"] and capabilities["subtitles"]:
            return FFmpegReadiness(
                ready=True,
                source=source,
                executable=candidate,
                version=version,
                capabilities=capabilities,
                managed_download_needed=False,
                reason=reason,
            )
        if first_failure is None:
            first_failure = FFmpegReadiness(
                ready=False,
                source=source,
                executable=candidate,
                version=version,
                capabilities=capabilities,
                managed_download_needed=managed_available,
                reason=reason,
            )
    if first_failure is not None:
        return first_failure
    return FFmpegReadiness(
        ready=False,
        source="missing",
        executable=None,
        version=None,
        capabilities={"starts": False, "subtitles": False},
        managed_download_needed=managed_available,
        reason="No FFmpeg executable was found in the configured, managed, bundled, or system locations.",
    )


@lru_cache(maxsize=1)
def resolve() -> tuple[str, bool]:
    """Return `(ffmpeg_path, has_subtitles)` without downloading anything."""
    decision = readiness()
    return decision.executable or "ffmpeg", decision.ready


def ffmpeg() -> str:
    return resolve()[0]


def ffprobe() -> str:
    sibling = Path(ffmpeg()).parent / f"ffprobe{_EXE}"
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def supports_captions() -> bool:
    return readiness().ready


def managed_asset() -> downloads.ManagedAsset | None:
    record = _platform_asset()
    managed = _managed_dir()
    if not record or not managed:
        return None
    return downloads.ManagedAsset(
        asset_id=f"runtime:ffmpeg:{record['key']}",
        display_name="FFmpeg — Video engine",
        purpose="Decode, probe, caption, and render video clips",
        destination=str(Path("runtimes") / "ffmpeg" / str(record["version"]) / str(record["key"]) / "ffmpeg.zip"),
        url=str(record["url"]),
        size_bytes=int(record.get("size", 0)),
        sha256=str(record["sha256"]),
        required=True,
        one_time=True,
        license=str(_manifest()["runtimes"]["ffmpeg"].get("license", "See upstream")),
        source=str(_manifest()["runtimes"]["ffmpeg"].get("provenance", "")),
        consent_group="core",
        archive_type="zip",
        source_revision=str(record.get("version", "")),
        platform=str(record.get("platform", "")),
        download_destination=str(Path("runtimes") / "ffmpeg" / str(record["version"]) / str(record["key"]) / "ffmpeg.zip"),
    )


def _atomic_install_windows(archive: Path) -> bool:
    managed = _managed_dir()
    if managed is None:
        return False
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    staging = managed.with_name(f".{managed.name}.{time.time_ns()}.staging")
    try:
        runtime.extract_zip_selected_verified(
            archive,
            staging,
            expected_basenames=wanted,
            member_modes={name: 0o755 for name in wanted},
        )
        ffmpeg_path = staging / "ffmpeg.exe"
        if not _has_subtitles_filter(str(ffmpeg_path)):
            raise runtime.RuntimeIntegrityError("managed FFmpeg lacks the required subtitles/libass filter")
        managed.parent.mkdir(parents=True, exist_ok=True)
        backup = managed.with_name(f".{managed.name}.previous")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if managed.exists():
            os.replace(managed, backup)
        os.replace(staging, managed)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        return True
    except (OSError, runtime.RuntimeIntegrityError, zipfile.BadZipFile):
        shutil.rmtree(staging, ignore_errors=True)
        return False


def install_managed(*, event=None, cancel=None, require_consent: bool = True) -> bool:
    """Install the platform-managed FFmpeg through DownloadManager."""
    asset = managed_asset()
    if asset is None:
        return False
    manager = downloads.DownloadManager(event=event)
    try:
        archive = manager.download(asset, require_consent=require_consent, cancel=cancel)
        if platform.system() != "Windows":
            return False
        ok = _atomic_install_windows(archive)
        if not ok:
            manager.mark_needs_repair(asset.asset_id, "Managed FFmpeg failed archive or capability validation")
            return False
        readiness.cache_clear()
        resolve.cache_clear()
        return supports_captions()
    finally:
        archive_path = _managed_dir() / "ffmpeg.zip" if _managed_dir() else None
        if archive_path:
            archive_path.unlink(missing_ok=True)


def ensure_capable(progress=None) -> bool:
    """Compatibility wrapper for explicit setup callers only.

    Render stages must not call this function automatically.  It is retained
    for the CLI/Tauri Setup Center action and requires the caller's consent.
    """
    event = None
    if progress:
        def event(payload: dict[str, Any]) -> None:
            fraction = payload.get("fraction", -1.0)
            progress(float(fraction if fraction is not None else -1.0), str(payload.get("message", "Installing FFmpeg…")))
    return install_managed(event=event, require_consent=False)
