"""Honest first-run readiness checks for the desktop preflight screen."""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
from pathlib import Path

import httpx

from . import config, hardware, local_runtime, protocol, runtime
from .ingest import ytdlp
from .models import registry, specs  # noqa: F401 - register concrete models
from .render import ffmpeg_bin
from .scoring import providers as providers_mod

MANIFEST = Path(__file__).resolve().parents[1] / "runtime-manifest.json"
MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024
SUPPORTED_SYSTEMS = {"Linux", "Darwin", "Windows"}
SUPPORTED_MACHINES = {"x86_64", "amd64", "aarch64", "arm64", "AMD64"}


def _is_youtube_source(source: str) -> bool:
    from urllib.parse import urlsplit

    host = (urlsplit(source.strip()).hostname or "").lower()
    return host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com")


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
    decision = ffmpeg_bin.readiness()
    details = decision.to_dict()
    if decision.ready:
        _check(checks, "ffmpeg", "ready", f"FFmpeg is ready ({decision.source}).", path=decision.executable, **details)
    elif decision.executable:
        managed = ffmpeg_bin.managed_asset()
        _check(
            checks,
            "ffmpeg",
            "warning",
            "FFmpeg was found but cannot render ClipGauge captions.",
            "Install the compatible managed FFmpeg copy without changing the existing installation.",
            path=decision.executable,
            expected_size=managed.size_bytes if managed and decision.managed_download_needed else None,
            **details,
        )
    else:
        managed = ffmpeg_bin.managed_asset()
        _check(
            checks,
            "ffmpeg",
            "blocked",
            "FFmpeg is not available.",
            "Install FFmpeg or configure a verified bundled binary.",
            expected_size=managed.size_bytes if managed and decision.managed_download_needed else None,
            **details,
        )


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


def _provider(checks: list[dict], profile: providers_mod.ProviderProfile) -> None:
    if not profile.enabled:
        _check(checks, "provider", "blocked", "The selected provider profile is disabled.", "Enable the profile in Settings.", provider=profile.kind)
        return
    if profile.auth_strategy != "none" and not providers_mod.secret_from_environment(profile):
        _check(
            checks,
            "provider-credential",
            "blocked",
            f"No credential is available for {profile.display_name}.",
            "Save the provider credential in Settings or choose a local provider.",
            provider=profile.kind,
        )
        return
    if profile.kind == "clipgauge-local":
        try:
            managed = local_runtime.LocalRuntime()
            binary = managed.binary_path()
            model = managed.model_path(profile.model)
            model_spec = local_runtime.MODEL_CATALOG[profile.model]
        except (KeyError, local_runtime.LocalRuntimeError) as error:
            _check(checks, "clipgauge-local", "blocked", "ClipGauge Local is not available for the selected model or platform.", "Open Setup Center and choose a verified local model.", error=str(error), provider=profile.kind)
            return
        if not binary.is_file():
            _check(checks, "clipgauge-local-runtime", "blocked", "ClipGauge Local runtime is not installed yet.", "Open Setup Center to install the verified llama.cpp runtime.", path=str(binary), expected_size=managed.runtime_asset().get("size"), provider=profile.kind)
            return
        if not model.is_file():
            _check(checks, "clipgauge-local-model", "blocked", f"{model_spec.display_name} is not installed yet.", "Open Setup Center to download the verified local model.", expected_size=model_spec.size_bytes, provider=profile.kind, model=profile.model)
            return
        digest = runtime.sha256_file(model)
        if digest.lower() != model_spec.sha256.lower():
            _check(checks, "clipgauge-local-model", "blocked", "The ClipGauge Local model failed SHA-256 verification.", "Delete the invalid model and retry the verified download.", sha256=digest, expected_size=model_spec.size_bytes, provider=profile.kind, model=profile.model)
            return
        _check(checks, "clipgauge-local", "ready", "ClipGauge Local runtime and model are verified.", provider=profile.kind, model=profile.model, endpoint=profile.endpoint_identity, capabilities=profile.capabilities.to_dict())
        return
    if profile.kind in {"ollama", "lmstudio"}:
        try:
            listing_path = "/api/tags" if profile.kind == "ollama" else "/models"
            response = httpx.get(profile.endpoint_identity.rstrip("/") + listing_path, timeout=3.0)
            if len(response.content) > 1024 * 1024:
                raise ValueError("health response exceeded 1 MiB")
            response.raise_for_status()
            payload = response.json()
            if profile.kind == "ollama":
                models = [item.get("name") for item in payload.get("models", []) if item.get("name")]
            else:
                models = [item.get("id") for item in payload.get("data", []) if item.get("id")]
            if not models:
                _check(checks, "provider", "blocked", f"{profile.display_name} is running but has no local models.", "Start the local server and load a compatible chat model, then retry.", provider=profile.kind, models=[])
            else:
                _check(checks, "provider", "ready", f"{profile.display_name} is running with local models.", provider=profile.kind, models=models)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            _check(checks, "provider", "blocked", f"{profile.display_name} is stopped or unavailable on loopback.", "Start the local server or choose another provider.", provider=profile.kind)
        return
    _check(
        checks,
        "provider",
        "ready" if profile.locality == "local" else "warning",
        f"{profile.display_name} is configured for this operation.",
        "Run Test Connection to verify the selected model and capabilities." if profile.locality != "local" else None,
        provider=profile.kind,
        model=profile.model,
        endpoint=profile.endpoint_identity,
        capabilities=profile.capabilities.to_dict(),
    )


def _storage_estimate(checks: list[dict], free_bytes: int | None) -> dict:
    assets = []
    for check in checks:
        details = check.get("details") or {}
        expected = details.get("expected_size")
        if not isinstance(expected, int) or expected <= 0:
            continue
        name = str(check.get("name", "asset"))
        assets.append(
            {
                "asset_id": name,
                "display_name": name.removeprefix("model:").replace("_", " "),
                "size_bytes": expected,
                "required": True,
                "installed": check.get("state") == "ready",
                "status": check.get("state"),
            }
        )
    required_bytes = sum(item["size_bytes"] for item in assets if not item["installed"])
    return {
        "required_bytes": required_bytes,
        "available_bytes": free_bytes,
        "consent_required": required_bytes >= 100 * 1024 * 1024,
        "assets": assets,
    }


def run(selected_llm: providers_mod.ProviderProfile | str = "gemini", source: str | None = None) -> dict:
    checks: list[dict] = []
    system = platform.system()
    machine = platform.machine()
    _check(checks, "platform", "ready" if system in SUPPORTED_SYSTEMS and machine in SUPPORTED_MACHINES else "warning", f"Detected {system}/{machine}.", "Use a supported desktop build if runtime behavior is unexpected.", system=system, architecture=machine)
    free_bytes: int | None = None
    try:
        usage = shutil.disk_usage(config.home_dir().parent)
        free_bytes = usage.free
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
    youtube_status = None
    if source and _is_youtube_source(source):
        from .ingest import youtube_compat

        youtube_status = youtube_compat.readiness()
        dependency_ready = youtube_status.get("dependency_state") == "DEPENDENCIES_READY" or youtube_status.get("state") == "PUBLIC_DOWNLOAD_VERIFIED"
        public_verified = bool(youtube_status.get("public_download_verified"))
        if not youtube_status.get("ready"):
            youtube_check_state = "blocked"
            remediation = "Open Setup Center, repair YouTube support, and retry."
        elif public_verified:
            youtube_check_state = "ready"
            remediation = None
        else:
            youtube_check_state = "warning"
            remediation = "Retry the public link later, or import the downloaded video file directly."
        _check(
            checks,
            "youtube-support",
            youtube_check_state,
            str(youtube_status.get("reason") or ("YouTube tools are ready; public download availability depends on YouTube." if dependency_ready else "YouTube support needs attention.")),
            remediation,
            youtube_state=youtube_status.get("state"),
            public_download_verified=public_verified,
        )
    profile = providers_mod.legacy_profile(selected_llm) if isinstance(selected_llm, str) else selected_llm
    _provider(checks, profile)
    states = {item["state"] for item in checks}
    overall = "blocked" if "blocked" in states else "warning" if "warning" in states else "ready"
    capabilities = hardware.snapshot(config.home_dir())
    return {
        "state": overall,
        "checks": checks,
        "hardware": capabilities,
        "storage": _storage_estimate(checks, free_bytes),
        "selected_llm": profile.kind,
        "youtube": youtube_status,
        "provider": {
            "id": profile.id,
            "kind": profile.kind,
            "model": profile.model,
            "endpoint_identity": profile.endpoint_identity,
            "capabilities": profile.capabilities.to_dict(),
            "locality": profile.locality,
        },
    }
