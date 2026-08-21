"""Managed yt-dlp standalone binary + wrapper.

Ported from JeremySNR/clip-forge src/main/pipeline/ytdlp.ts (MIT — see
VENDORED-LICENSES.md): the standalone binary (not the pip package) is
downloaded to CLIPGAUGE_HOME/bin on first use so the built-in self-updater
keeps working — sites change their players constantly and a stale yt-dlp is
the most common cause of extractor failures. On any yt-dlp failure we run
`-U` once per process and retry once (withSelfUpdateRetry pattern).

Every invocation gets an inactivity watchdog: if yt-dlp prints nothing for
SUBPROCESS_INACTIVITY_TIMEOUT seconds it is killed — a blackholed connection
must never freeze the pipeline (PLAN.md §3).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx

from .. import config, downloads, runtime
from . import youtube_compat

_MANIFEST = Path(__file__).resolve().parents[2] / "runtime-manifest.json"

ProgressFn = Callable[[float, str], None]  # (fraction 0..1 or -1, message)
_provider_supervisor = youtube_compat.ProviderSupervisor()


def _needs_youtube_provider(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com")


SUPPORTED_BROWSER_SESSIONS = {"chrome", "chromium", "edge", "firefox", "brave", "opera", "safari", "vivaldi"}


def _browser_auth_args(browser: str | None) -> list[str]:
    if not browser:
        return []
    normalized = browser.strip().lower()
    if normalized not in SUPPORTED_BROWSER_SESSIONS:
        raise YtDlpError("The selected browser session is not supported. Choose a supported browser or leave authentication off.", code="YTDLP_BROWSER_AUTH_INVALID", retryable=False)
    return ["--cookies-from-browser", normalized]


def _youtube_provider_args(url: str) -> list[str]:
    if not _needs_youtube_provider(url):
        return []
    status = _provider_supervisor.self_test()
    if not status.get("ok"):
        raise YtDlpError(
            "YouTube compatibility is not ready. Open Setup Center, install the PO-token provider, and run its Test action.",
            code="YTDLP_PROVIDER_NOT_READY",
            retryable=True,
        )
    _provider_supervisor.start()
    return [
        "--plugin-dirs", str(youtube_compat.plugin_dir()),
        "--extractor-args", f"youtubepot-bgutilhttp:base_url=http://127.0.0.1:{youtube_compat.DEFAULT_PORT}",
    ]


class YtDlpError(Exception):
    """yt-dlp process failure with a cleaned, user-facing message and stable code."""

    def __init__(self, message: str, code: str = "YTDLP_ERROR", retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _binary_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "yt-dlp.exe"
    if system == "Darwin":
        return "yt-dlp_macos"
    if platform.machine().lower() in {"aarch64", "arm64"}:
        return "yt-dlp_linux_aarch64"
    return "yt-dlp_linux"


def _manifest_record() -> tuple[dict, dict, str]:
    try:
        manifest = runtime.load_manifest(_MANIFEST)
        runtime_manifest = manifest["runtimes"]["yt-dlp"]
        name = _binary_name()
        return manifest, runtime_manifest["assets"][name], name
    except (KeyError, TypeError) as exc:
        raise YtDlpError("The pinned yt-dlp runtime manifest is incomplete.") from exc


def binary_path() -> Path:
    try:
        manifest = runtime.load_manifest(_MANIFEST)
        version = str(manifest["runtimes"]["yt-dlp"]["version"])
        path = config.runtimes_dir() / "yt-dlp" / version / _binary_name()
        if path != config.home_dir() and config.home_dir() not in path.parents:
            raise ValueError("managed yt-dlp path escapes the ClipGauge data root")
        return path
    except (OSError, ValueError, runtime.RuntimeIntegrityError, KeyError, TypeError):
        return config.bin_dir() / _binary_name()


def managed_asset() -> downloads.ManagedAsset:
    manifest, record, name = _manifest_record()
    version = str(manifest["runtimes"]["yt-dlp"]["version"])
    path = binary_path()
    return downloads.ManagedAsset(
        asset_id=f"runtime:yt-dlp:{name}",
        display_name="YouTube downloader",
        purpose="Retrieves public video metadata and media",
        destination=str(path.relative_to(config.home_dir())),
        url=str(record["url"]),
        size_bytes=int(record.get("size", 0) or 0),
        sha256=str(record["sha256"]),
        required=True,
        one_time=True,
        license=str(manifest["runtimes"]["yt-dlp"].get("license", "See upstream")),
        source=str(manifest["runtimes"]["yt-dlp"].get("provenance", "")),
        consent_group="core:youtube",
        source_revision=version,
        platform=str(record.get("platform", "")),
    )


def ensure_ytdlp(progress: ProgressFn) -> Path:
    """Install the pinned yt-dlp asset through the common manager."""
    manifest, record, name = _manifest_record()
    version = str(manifest["runtimes"]["yt-dlp"]["version"])
    path = binary_path()
    asset = managed_asset()
    manager = downloads.DownloadManager(event=lambda payload: progress(float(payload.get("fraction", -1.0) if payload.get("fraction") is not None else -1.0), str(payload.get("message", "Downloading yt-dlp…"))))
    config.ensure_home()
    # Reuse v0.3's verified bin/ copy non-destructively before any network call.
    legacy = config.bin_dir() / name
    if legacy != path and legacy.is_file():
        manager.migrate_legacy_asset(asset, [legacy])
    try:
        result = manager.download(asset, require_consent=True)
    except downloads.ConsentRequiredError as exc:
        raise YtDlpError("YouTube compatibility is not installed. Open Setup Center and approve the YouTube compatibility download group.", code="YTDLP_ASSET_CONSENT_REQUIRED", retryable=True) from exc
    except (runtime.RuntimeIntegrityError, runtime.RuntimeDiskSpaceError) as exc:
        raise YtDlpError(f"Could not install verified yt-dlp: {exc}", code="YTDLP_RUNTIME_INSTALL_FAILED", retryable=True) from exc
    try:
        result.chmod(0o755)
    except OSError:
        pass
    return result


def _clean_error(stderr: str) -> str:
    """Last ERROR: line, with extractor prefixes stripped (clip-forge)."""
    for line in reversed(stderr.splitlines()):
        if line.startswith("ERROR:"):
            return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[^\s:]*:?\s*)?", "", line).strip()
    return ""


def classify_error(message: str) -> str:
    """Map yt-dlp's changing prose to stable, creator-facing states."""
    lowered = message.lower()
    if re.search(r"po.?token|attestation|playback verification|signature extraction|403|forbidden", lowered):
        return "YTDLP_ATTESTATION_REQUIRED"
    if re.search(r"sign ?in|log ?in|cookies|password|authentication required|401|authoriz", lowered):
        return "YTDLP_LOGIN_REQUIRED"
    if re.search(r"private|members only|purchase required|member-only", lowered):
        return "YTDLP_PRIVATE"
    if re.search(r"age.?restricted|confirm your age|mature content", lowered):
        return "YTDLP_AGE_RESTRICTED"
    if re.search(r"not available in your country|geo.?restrict|region|country", lowered):
        return "YTDLP_REGION_RESTRICTED"
    if re.search(r"video unavailable|video has been removed|deleted|does not exist|not found", lowered):
        return "YTDLP_UNAVAILABLE"
    return "YTDLP_ERROR"


def is_auth_error(message: str) -> bool:
    """Backward-compatible helper for callers that only need a login distinction."""
    return classify_error(message) == "YTDLP_LOGIN_REQUIRED"


def _run(
    bin_path: Path,
    args: list[str],
    on_line: Callable[[str], None] | None = None,
    inactivity_timeout: float = config.SUBPROCESS_INACTIVITY_TIMEOUT,
) -> str:
    """Run yt-dlp, streaming stdout lines, killing on output inactivity."""
    proc = subprocess.Popen(
        [str(bin_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    activity = threading.Event()
    done = threading.Event()

    def _pump(stream, sink: list[str], line_cb: Callable[[str], None] | None) -> None:
        for line in stream:
            sink.append(line)
            activity.set()
            if line_cb:
                line_cb(line.rstrip("\n"))

    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, stdout_parts, on_line), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, stderr_parts, None), daemon=True),
    ]
    for t in threads:
        t.start()

    def _watchdog() -> None:
        while not done.is_set():
            activity.clear()
            if done.wait(inactivity_timeout):
                return
            if not activity.is_set():
                proc.kill()
                return

    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()
    code = proc.wait()
    done.set()
    for t in threads:
        t.join(timeout=5)
    if code != 0:
        stderr = "".join(stderr_parts)[-65536:]
        msg = _clean_error(stderr) or f"yt-dlp exited with code {code}"
        if code in (-9, -15) and not _clean_error(stderr):
            msg = "yt-dlp stalled (no output for a while) and was stopped. Check your connection and retry."
        raise YtDlpError(msg, code=classify_error(msg), retryable=True)
    return "".join(stdout_parts)


_self_updated_this_run = False


def _with_self_update_retry(bin_path: Path, progress: ProgressFn, fn: Callable[[], str]) -> str:
    """Run the pinned binary once; in-process self-updates are forbidden."""
    return fn()


@dataclass
class UrlMeta:
    id: str
    title: str
    duration_sec: float
    webpage_url: str
    # YouTube "most replayed" heatmap: [{start_time, end_time, value}] with
    # value normalized 0..1. Real human engagement data — the free ground
    # truth for the interest curve (PLAN.md stage 5). None if unavailable.
    heatmap: list[dict] | None = None
    raw: dict = field(default_factory=dict, repr=False)


def _pick_playlist_entry(data: dict) -> dict:
    """Some sites resolve to a playlist (archive.org items). Pick the longest
    entry — almost always the main video (clip-forge pattern)."""
    entries = [e for e in data.get("entries") or [] if (e.get("duration") or 0) > 0]
    if not entries:
        raise YtDlpError("This URL does not contain a downloadable video.")
    main = max(entries, key=lambda e: e.get("duration") or 0)
    merged = dict(main)
    merged.setdefault("title", data.get("title"))
    if main.get("url"):
        merged["webpage_url"] = main["url"]
    return merged


def fetch_meta(url: str, progress: ProgressFn, cookies_from_browser: str | None = None) -> UrlMeta:
    bin_path = ensure_ytdlp(progress)

    def _go() -> str:
        args = [*_youtube_provider_args(url), *_browser_auth_args(cookies_from_browser)]
        return _run(bin_path, [*args, "-J", "--no-playlist", "--no-warnings", url])

    out = _with_self_update_retry(bin_path, progress, _go)
    data = json.loads(out)
    if data.get("_type") == "playlist":
        data = _pick_playlist_entry(data)
    if not data.get("duration") or data["duration"] <= 0:
        raise YtDlpError("This URL does not point to a downloadable video.")
    heatmap = data.get("heatmap")
    if isinstance(heatmap, list) and heatmap:
        heatmap = [
            {
                "start_time": float(seg.get("start_time", 0.0)),
                "end_time": float(seg.get("end_time", 0.0)),
                "value": float(seg.get("value", 0.0)),
            }
            for seg in heatmap
            if isinstance(seg, dict)
        ]
    else:
        heatmap = None
    return UrlMeta(
        id=str(data.get("id", "video")),
        title=str(data.get("title", "Imported video")),
        duration_sec=float(data["duration"]),
        webpage_url=str(data.get("webpage_url") or data.get("url") or url),
        heatmap=heatmap,
        raw=data,
    )


DOWNLOAD_FORMAT = (
    f"bv*[height<={config.MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]"
    f"/b[height<={config.MAX_HEIGHT}][ext=mp4]/b"
)

_PCT_RE = re.compile(r"\[download\]\s+([\d.]+)%")


def download(url: str, out_path: Path, progress: ProgressFn, cookies_from_browser: str | None = None) -> None:
    bin_path = ensure_ytdlp(progress)
    ffmpeg = shutil.which("ffmpeg")
    args = [
        *_youtube_provider_args(url),
        *_browser_auth_args(cookies_from_browser),
        "-f", DOWNLOAD_FORMAT,
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-warnings",
        "--newline",
        "--socket-timeout", "30",
    ]
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    args += ["-o", str(out_path), url]

    def _on_line(line: str) -> None:
        m = _PCT_RE.search(line)
        if m:
            # Map download to 0.15..0.95 of ingest (after binary setup).
            progress(0.15 + (float(m.group(1)) / 100) * 0.8, "Downloading video…")
        elif "[Merger]" in line:
            progress(0.96, "Merging streams…")

    def _go() -> str:
        return _run(bin_path, args, on_line=_on_line)

    _with_self_update_retry(bin_path, progress, _go)
    if not out_path.exists():
        # yt-dlp may add an extension when the template lacks one
        candidates = list(out_path.parent.glob(out_path.name + ".*"))
        if candidates:
            candidates[0].replace(out_path)
        else:
            raise YtDlpError("Download finished but no output file was produced.")
