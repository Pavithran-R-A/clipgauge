"""ffmpeg binary resolution.

Caption burning needs an ffmpeg built with libass, and (as this very
machine demonstrates) Homebrew's slimmed `ffmpeg` formula ships without it.
Resolution order: PUBLIKCLIP_FFMPEG env → bundled sidecar binary (packaged
app) → Homebrew ffmpeg-full keg → PATH. The first candidate that actually
has the `subtitles` filter wins; if none do, the plain PATH binary is
returned with `has_subtitles=False` so the caller can degrade (render
without burned captions) with an honest message instead of a crash.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import zipfile
from functools import lru_cache
from pathlib import Path

from .. import config, runtime

_KEG_CANDIDATES = [
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
]

# Static macOS builds with libass (ffmpeg.martin-riedl.de). Used only when
# no capable ffmpeg exists on the machine — downloaded once into
# PUBLIKCLIP_HOME/bin so end users never touch Homebrew.
# FFmpeg source is authoritative, but this packaged binary is supplied by
# BtbN. The tag and SHA-256 are recorded in runtime-manifest.json.
_STATIC_WINDOWS = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
    "autobuild-2026-08-18-15-03/ffmpeg-N-126207-g21bbd98e7b-win64-gpl.zip"
)
_STATIC_WINDOWS_SHA256 = "0dfc1c04a5b8c15e56e3e2245d3b0a1fb5f22242591e1b2c4a1cb6fa0cd0230b"

_EXE = ".exe" if platform.system() == "Windows" else ""


def _has_subtitles_filter(binary: str) -> bool:
    try:
        proc = subprocess.run(
            [binary, "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return " subtitles " in proc.stdout


@lru_cache(maxsize=1)
def resolve() -> tuple[str, bool]:
    """(ffmpeg_path, has_subtitles)."""
    candidates: list[str] = []
    env = os.environ.get("PUBLIKCLIP_FFMPEG")
    if env:
        candidates.append(env)
    candidates.append(str(config.bin_dir() / f"ffmpeg{_EXE}"))  # our downloaded static
    bundled = os.environ.get("PUBLIKCLIP_BUNDLED_FFMPEG")  # set by the app shell
    if bundled:
        candidates.append(bundled)
    if platform.system() == "Darwin":
        candidates.extend(_KEG_CANDIDATES)
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        candidates.append(path_ffmpeg)

    fallback: str | None = None
    for cand in candidates:
        if not os.path.exists(cand):
            continue
        fallback = fallback or cand
        if _has_subtitles_filter(cand):
            return cand, True
    return (fallback or "ffmpeg"), False


def ffmpeg() -> str:
    return resolve()[0]


def ffprobe() -> str:
    """ffprobe next to the resolved ffmpeg when present, else PATH."""
    sibling = Path(ffmpeg()).parent / f"ffprobe{_EXE}"
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def supports_captions() -> bool:
    return resolve()[1]


def _download(url: str, dest: Path, expected_sha256: str, progress=None) -> bool:
    try:
        runtime.download_verified(
            url,
            dest,
            expected_sha256=expected_sha256,
            max_bytes=512 * 1024 * 1024,
            timeout=300.0,
            progress=progress,
        )
        return True
    except runtime.RuntimeIntegrityError:
        return False


def _ensure_capable_macos(progress) -> bool:
    if progress:
        progress(-1, "No pinned macOS FFmpeg archive is configured; using a verified system binary if available.")
    return False


def _ensure_capable_windows(progress) -> bool:
    """One zip carries both tools (BtbN GPL build, libass included)."""
    wanted = {
        "ffmpeg.exe": config.bin_dir() / "ffmpeg.exe",
        "ffprobe.exe": config.bin_dir() / "ffprobe.exe",
    }
    if all(dest.exists() for dest in wanted.values()) and _has_subtitles_filter(
        str(wanted["ffmpeg.exe"])
    ):
        return True
    if progress:
        progress(-1, "Downloading ffmpeg (one-time, caption support)…")
    zpath = config.bin_dir() / "ffmpeg-static.zip"
    try:
        if not _download(_STATIC_WINDOWS, zpath, _STATIC_WINDOWS_SHA256, progress=lambda f, m: progress(f, m) if progress else None):
            return False
        runtime.extract_zip_selected_verified(
            zpath,
            config.bin_dir(),
            expected_basenames=set(wanted),
            member_modes={name: 0o755 for name in wanted},
        )
    except (OSError, zipfile.BadZipFile):
        return False
    finally:
        zpath.unlink(missing_ok=True)
    return all(dest.exists() for dest in wanted.values())


def ensure_capable(progress=None) -> bool:
    """If no libass ffmpeg exists anywhere, download a static build once
    into PUBLIKCLIP_HOME/bin (macOS arm64/x86_64, Windows x64), then
    re-resolve. Returns whether caption burning is available afterwards."""
    if supports_captions():
        return True
    system = platform.system()
    config.ensure_home()
    if system == "Darwin":
        ok = _ensure_capable_macos(progress)
    elif system == "Windows":
        ok = _ensure_capable_windows(progress)
    else:
        return False
    if not ok:
        return False
    resolve.cache_clear()
    return supports_captions()
