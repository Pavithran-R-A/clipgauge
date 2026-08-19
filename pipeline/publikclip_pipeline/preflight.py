"""Honest first-run readiness checks for the desktop preflight screen."""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
from pathlib import Path

import httpx

from . import config, protocol, runtime
from .ingest import ytdlp
from .models import registry, specs  # noqa: F401 - register concrete models
from .render import ffmpeg_bin

MANIFEST = Path(__file__).resolve().parents[1] / "runtime-manifest.json"
MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024
SUPPORTED_SYSTEMS = {"Linux", "Darwin", "Windows"}
SUPPORTED_MACHINES = {"x86_64", "amd64", "aarch64", "arm64", "AMD64"}


def _check(checks: list[dict], name: str, state: str, message: str, remediation: str | None = None, **details) -> None:
    row = {"name": name, "state": state, "message": protocol.safe_message(message)}
    if remediation:
        row["remediation"] = protocol.safe_message(remediation)
    if details:
        row["details"] = details
    checks.append(row)


def _writable_root(checks: list[dict]) -> None:
    try:
        root = config.ensure_home()
        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=root, delete=True):
            pass
        _check(checks, "managed-data", "ready", "The managed data directory is writable.", path=str(root))
    except OSError as error:
        _check(checks, "managed-data", "blocked", "The managed data directory is not writable.", "Choose a writable app-data location and retry.", error=str(error))


def _runtime_manifest() -> dict:
    return runtime.load_manifest(MANIFEST)


def _yt_dlp(checks: list[dict], manifest: dict) -> None:
    name = ytdlp._binary_name()
    entry = manifest.get("runtimes", {}).get("yt-dlp", {}).get("assets", {}).get(name)
    path = ytdlp.binary_path()
    if not entry:
        _check(checks, "yt-dlp", "blocked", f"No pinned yt-dlp asset is registered for {name}.", "Update the signed runtime manifest.")
    elif not path.exists():
        _check(checks, "yt-dlp", "warning", f"yt-dlp {manifest['runtimes']['yt-dlp']['version']} is not installed yet.", "Start the run to download the pinned asset.", version=manifest["runtimes"]["yt-dlp"]["version"], expected_size=entry.get("size"))
    else:
        try:
            digest = runtime.sha256_file(path)
            state = "ready" if digest.lower() == entry["sha256"].lower() else "blocked"
            message = "The installed yt-dlp matches the pinned SHA-256." if state == "ready" else "The installed yt-dlp does not match the pinned SHA-256."
            remediation = None if state == "ready" else "Remove the untrusted binary or start a verified reinstall."
            _check(checks, "yt-dlp", state, message, remediation, version=manifest["runtimes"]["yt-dlp"]["version"], sha256=digest)
        except OSError as error:
            _check(checks, "yt-dlp", "blocked", "The installed yt-dlp could not be read.", "Check file permissions and retry.", error=str(error))


def _models(checks: list[dict], manifest: dict) -> None:
    for key, spec in registry.REGISTRY.items():
        path = registry.model_path(spec)
        entry = manifest.get("models", {}).get(key, {})
        if not path.exists():
            _check(checks, f"model:{key}", "warning", f"Model {key} is not installed yet.", "Start the run to download the pinned model.", expected_size=entry.get("size"), revision=spec.revision)
            continue
        try:
            digest = runtime.sha256_file(path)
            state = "ready" if digest.lower() == spec.sha256.lower() else "blocked"
            _check(checks, f"model:{key}", state, "Model hash matches the pinned registry." if state == "ready" else "Model hash does not match the pinned registry.", None if state == "ready" else "Delete the invalid model and retry the verified download.", sha256=digest, expected_size=entry.get("size"))
        except OSError as error:
            _check(checks, f"model:{key}", "blocked", "Model file could not be read.", "Check file permissions and retry.", error=str(error))


def _ffmpeg(checks: list[dict]) -> None:
    binary, captions = ffmpeg_bin.resolve()
    if binary == "ffmpeg" and not shutil.which("ffmpeg"):
        _check(checks, "ffmpeg", "blocked", "FFmpeg is not available.", "Install FFmpeg or configure a verified bundled binary.")
    elif captions:
        _check(checks, "ffmpeg", "ready", "FFmpeg is available with the subtitles filter.", path=binary)
    else:
        _check(checks, "ffmpeg", "warning", "FFmpeg is available but caption burning is unavailable.", "Install a build with libass/subtitles support; renders can continue without burned captions.", path=binary)


def _ollama(checks: list[dict], selected: str) -> None:
    if selected != "ollama":
        return
    try:
        response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if len(response.content) > 1024 * 1024:
            raise ValueError("health response exceeded 1 MiB")
        response.raise_for_status()
        models = [item.get("name") for item in response.json().get("models", []) if item.get("name")]
        if not models:
            _check(checks, "ollama", "blocked", "Ollama is running but has no local models.", "Start Ollama and pull a supported model, then retry.", models=[])
        else:
            _check(checks, "ollama", "ready", "Ollama is running with local models.", models=models)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        _check(checks, "ollama", "blocked", "Ollama is stopped or unavailable on loopback.", "Start Ollama locally or switch the run to Gemini mode.")


def run(selected_llm: str = "gemini") -> dict:
    checks: list[dict] = []
    system = platform.system()
    machine = platform.machine()
    _check(checks, "platform", "ready" if system in SUPPORTED_SYSTEMS and machine in SUPPORTED_MACHINES else "warning", f"Detected {system}/{machine}.", "Use a supported desktop build if runtime behavior is unexpected.", system=system, architecture=machine)
    try:
        usage = shutil.disk_usage(config.home_dir().parent)
        if usage.free < MIN_FREE_BYTES:
            _check(checks, "disk", "blocked", "Less than 1 GiB is free on the managed data volume.", "Free disk space before downloading models or rendering.", free_bytes=usage.free)
        else:
            _check(checks, "disk", "ready", "Sufficient free disk space is available for setup.", free_bytes=usage.free)
    except OSError as error:
        _check(checks, "disk", "warning", "Free disk space could not be measured.", "Check the volume manually before starting a large render.", error=str(error))
    _writable_root(checks)
    try:
        manifest = _runtime_manifest()
        _check(checks, "runtime-manifest", "ready", "The pinned runtime manifest is valid.", version=manifest["manifest_version"])
        _yt_dlp(checks, manifest)
        _models(checks, manifest)
    except runtime.RuntimeIntegrityError as error:
        _check(checks, "runtime-manifest", "blocked", str(error), "Repair or reinstall the signed application bundle.")
    _ffmpeg(checks)
    if selected_llm == "gemini":
        _check(checks, "gemini", "ready" if os.environ.get("PUBLIKCLIP_GEMINI_API_KEY") else "blocked", "Gemini credential is available for this operation." if os.environ.get("PUBLIKCLIP_GEMINI_API_KEY") else "No Gemini credential is available to this operation.", "Save a Gemini key in Settings or choose Ollama mode.")
    _ollama(checks, selected_llm)
    states = {item["state"] for item in checks}
    overall = "blocked" if "blocked" in states else "warning" if "warning" in states else "ready"
    return {"state": overall, "checks": checks, "selected_llm": selected_llm}
