"""Managed yt-dlp PO-token compatibility for ClipGauge v0.4.

The provider is optional and explicit.  This module owns a pinned portable
Node runtime and tagged bgutil source, binds the HTTP provider to loopback,
and never reads browser cookies or starts a network service implicitly.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .. import config, downloads, runtime

DownloadManager = downloads.DownloadManager

PROVIDER_VERSION = "1.3.2"
NODE_VERSION = "24.19.0"
PROVIDER_GROUP = "core:youtube"
DEFAULT_PORT = 4416
PUBLIC_COMPATIBILITY_FILENAME = "youtube-public-compatibility.json"
WPC_VERSION = "1.1.2"
WPC_SOURCE = "https://github.com/coletdjnz/yt-dlp-getpot-wpc/tree/v1.1.2"
WPC_LICENSE = "MIT"


@dataclass(frozen=True)
class NodeSpec:
    platform_key: str
    archive_name: str
    archive_type: str
    url: str
    sha256: str
    size_bytes: int
    root_name: str
    node_relative: str
    npm_relative: str


NODE_SPECS = {
    "windows-x86_64": NodeSpec(
        "windows-x86_64", "node-v24.19.0-win-x64.zip", "zip",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-x64.zip",
        "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73", 37_304_352,
        "node-v24.19.0-win-x64", "node.exe", "npm.cmd",
    ),
    "macos-x86_64": NodeSpec(
        "macos-x86_64", "node-v24.19.0-darwin-x64.tar.gz", "tar.gz",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-x64.tar.gz",
        "d1b5e999db158c62fe8f7267a4476b035d8bd93b1a605bac24a3f0dd166e3316", 53_439_583,
        "node-v24.19.0-darwin-x64", "bin/node", "bin/npm",
    ),
    "macos-arm64": NodeSpec(
        "macos-arm64", "node-v24.19.0-darwin-arm64.tar.gz", "tar.gz",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz",
        "8294b7aa9b03997481c06babf1e8b270c859358f27da57a11509afe537ac381d", 52_234_372,
        "node-v24.19.0-darwin-arm64", "bin/node", "bin/npm",
    ),
    "linux-x86_64": NodeSpec(
        "linux-x86_64", "node-v24.19.0-linux-x64.tar.xz", "tar.xz",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-x64.tar.xz",
        "14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647", 31_633_904,
        "node-v24.19.0-linux-x64", "bin/node", "bin/npm",
    ),
    "linux-arm64": NodeSpec(
        "linux-arm64", "node-v24.19.0-linux-arm64.tar.xz", "tar.xz",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-arm64.tar.xz",
        "01443c1e1a29e531ccad5a46fefa6df490d2189c49f7955904aecdbb0fe86fdc", 30_553_480,
        "node-v24.19.0-linux-arm64", "bin/node", "bin/npm",
    ),
}


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "windows-x86_64" if machine in {"amd64", "x86_64"} else "windows-arm64"
    if system == "darwin":
        return "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-x86_64"
    return "linux-x86_64" if machine in {"x86_64", "amd64"} else "linux-arm64"


def _root() -> Path:
    return config.runtimes_dir() / "youtube" / "bgutil" / PROVIDER_VERSION


def node_asset() -> downloads.ManagedAsset:
    spec = NODE_SPECS[platform_key()]
    archive = _root() / "node" / spec.archive_name
    return downloads.ManagedAsset(
        asset_id=f"runtime:node:{spec.platform_key}",
        display_name="YouTube support runtime",
        purpose="Portable Node.js runtime for the managed PO-token provider",
        destination=str(archive.relative_to(config.home_dir())),
        url=spec.url,
        size_bytes=spec.size_bytes,
        sha256=spec.sha256,
        required=True,
        one_time=True,
        license="Node.js/OpenJS Foundation; see upstream notices",
        source="https://nodejs.org/en/download/archive/v24.19.0",
        consent_group=PROVIDER_GROUP,
        archive_type=spec.archive_type,
        source_revision=NODE_VERSION,
        platform=spec.platform_key,
    )


def provider_source_asset() -> downloads.ManagedAsset:
    archive = _root() / "bgutil-ytdlp-pot-provider-1.3.2.zip"
    return downloads.ManagedAsset(
        asset_id="youtube:bgutil-provider:1.3.2",
        display_name="YouTube PO-token provider",
        purpose="yt-dlp plugin and loopback PO-token server source",
        destination=str(archive.relative_to(config.home_dir())),
        url="https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/1.3.2.zip",
        size_bytes=125_366,
        sha256="9055f9cbe9f47d242586a542c5b040a17d8e5ddbd1fbc72d3d80841b63dfed8b",
        required=True,
        one_time=True,
        license="GPL-3.0-only",
        source="https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/1.3.2",
        consent_group=PROVIDER_GROUP,
        archive_type="zip",
        source_revision=PROVIDER_VERSION,
        platform=platform_key(),
    )


def assets() -> list[downloads.ManagedAsset]:
    return [node_asset(), provider_source_asset()]


def _node_home() -> Path:
    spec = NODE_SPECS[platform_key()]
    return _root() / "node" / spec.root_name


def node_path() -> Path:
    spec = NODE_SPECS[platform_key()]
    return _node_home() / spec.node_relative


def npm_path() -> Path:
    spec = NODE_SPECS[platform_key()]
    return _node_home() / spec.npm_relative


def source_home() -> Path:
    candidates = sorted((_root() / "source").glob("bgutil-ytdlp-pot-provider-*"))
    return candidates[-1] if candidates else _root() / "source" / "bgutil-ytdlp-pot-provider-1.3.2"


def server_home() -> Path:
    return source_home() / "server"


def plugin_home() -> Path:
    return _root() / "plugin"


def plugin_dir() -> Path:
    return plugin_home()


def _extract_assets(manager: downloads.DownloadManager, archives: list[Path]) -> None:
    node_archive, provider_archive = archives
    node_destination = _root() / "node" / NODE_SPECS[platform_key()].root_name
    if not node_destination.exists():
        runtime.extract_archive_verified(node_archive, _root() / "node", archive_type=NODE_SPECS[platform_key()].archive_type)
    if not source_home().exists():
        runtime.extract_archive_verified(provider_archive, _root() / "source", archive_type="zip")
    plugin_source = source_home() / "plugin" / "yt_dlp_plugins"
    plugin_destination = plugin_home() / "yt_dlp_plugins"
    if plugin_source.is_dir() and not plugin_destination.exists():
        plugin_home().mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin_source, plugin_destination)


def _server_ready() -> bool:
    return (server_home() / "build" / "main.js").is_file() and plugin_dir().is_dir() and node_path().is_file()


def _yt_dlp_ready() -> bool:
    try:
        from . import ytdlp

        _manifest, entry, _name = ytdlp._manifest_record()
        path = ytdlp.binary_path()
        return path.is_file() and runtime.sha256_file(path).lower() == str(entry["sha256"]).lower()
    except (OSError, KeyError, TypeError, ValueError, runtime.RuntimeIntegrityError):
        return False


def _public_compatibility_path() -> Path:
    return config.home_dir() / PUBLIC_COMPATIBILITY_FILENAME


def public_compatibility_status() -> dict[str, Any]:
    """Return only non-sensitive metadata from the latest public compatibility check."""
    try:
        payload = json.loads(_public_compatibility_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verified": False}
    if not isinstance(payload, dict):
        return {"verified": False}
    allowed = {"verified_at", "yt_dlp_version", "provider_version", "method"}
    return {key: payload[key] for key in allowed if key in payload} | {"verified": bool(payload.get("verified"))}


def invalidate_public_compatibility() -> None:
    """Invalidate only the public verification claim after a later transfer failure."""
    path = _public_compatibility_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    payload["verified"] = False
    temporary = path.with_name(f".{path.name}.part")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def record_public_compatibility_success(*, method: str, ytdlp_version: str, provider_version: str = PROVIDER_VERSION) -> None:
    """Cache successful public compatibility metadata, never tokens or session data."""
    config.ensure_home()
    payload = {
        "verified": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "yt_dlp_version": str(ytdlp_version)[:64],
        "provider_version": str(provider_version)[:64],
        "method": str(method)[:64],
    }
    path = _public_compatibility_path()
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _find_browser() -> str | None:
    """Detect an installed browser without launching it or reading its profile."""
    candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]
    return next((shutil.which(candidate) for candidate in candidates if shutil.which(candidate)), None)


def _wpc_plugin_installed() -> bool:
    return (config.runtimes_dir() / "youtube" / "wpc" / "yt_dlp_plugins" / "extractor" / "getpot_wpc.py").is_file()


def wpc_availability() -> dict[str, Any]:
    """Describe optional WPC availability without installing or launching anything."""
    browser_path = _find_browser()
    installed = _wpc_plugin_installed()
    return {
        "available": bool(browser_path and installed),
        "browser_path": browser_path,
        "plugin_installed": installed,
        "version": WPC_VERSION,
        "source": WPC_SOURCE,
        "license": WPC_LICENSE,
        "reason": "Optional browser-assisted compatibility is available." if browser_path and installed else "Install the optional WPC provider and have Chrome or Chromium installed before using browser-assisted compatibility.",
    }


def _launch_wpc_browser(browser_path: str) -> dict[str, Any]:
    """Production hook deliberately requires an explicit integration launcher."""
    return {"state": "NOT_CONFIGURED", "browser_path": browser_path, "provider": "wpc"}


def wpc_launch_decision(*, approved: bool, browser_path: str | None = None, launcher: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Enforce explicit approval before any optional browser-assisted launch."""
    if not approved:
        return {"state": "USER_DECLINED", "provider": "wpc"}
    path = browser_path or _find_browser()
    if not path:
        return {"state": "BROWSER_REQUIRED", "provider": "wpc", "reason": "Chrome or Chromium must be installed; ClipGauge will not install it."}
    return (launcher or _launch_wpc_browser)(path)


def readiness() -> dict[str, Any]:
    """Return dependency readiness separately from verified public-download readiness."""
    checks: list[dict[str, Any]] = []
    public_status = public_compatibility_status()
    wpc_status = wpc_availability()
    ytdlp_ok = _yt_dlp_ready()
    checks.append({"name": "yt-dlp", "ready": ytdlp_ok, "message": "Pinned yt-dlp is verified." if ytdlp_ok else "Pinned yt-dlp is not installed or failed verification."})
    if not ytdlp_ok:
        return {"state": "NOT_INSTALLED", "ready": False, "dependency_state": "NOT_INSTALLED", "public_download_verified": False, "wpc": wpc_status, "reason": "Install the verified YouTube runtime before testing public links.", "actions": ["Install"], "checks": checks}

    rows = DownloadManager().inventory(assets())
    installed = [bool(row.get("installed")) for row in rows]
    checks.extend({"name": str(row.get("asset_id", "youtube-asset")), "ready": bool(row.get("installed")), "message": "Verified asset is installed." if row.get("installed") else "Verified asset is missing or needs repair."} for row in rows)
    if not all(installed):
        state = "NOT_INSTALLED" if not any(installed) else "INSTALL_INCOMPLETE"
        return {"state": state, "ready": False, "dependency_state": state, "public_download_verified": False, "wpc": wpc_status, "reason": "Install the complete YouTube support bundle, then test it.", "actions": ["Install", "Retry"], "checks": checks}

    if not _server_ready():
        checks.append({"name": "provider-build", "ready": False, "message": "The PO-token provider build or plugin is incomplete."})
        return {"state": "BUILD_REQUIRED", "ready": False, "dependency_state": "BUILD_REQUIRED", "public_download_verified": False, "wpc": wpc_status, "reason": "Build the installed PO-token provider before using YouTube.", "actions": ["Repair", "Retry"], "checks": checks}

    result = ProviderSupervisor().self_test()
    plugin_ok = bool(result.get("plugin_discoverable"))
    server_ok = bool(result.get("server_installed"))
    health_ok = bool((result.get("health") or {}).get("healthy"))
    checks.extend([
        {"name": "plugin", "ready": plugin_ok, "message": "The YouTube plugin is discoverable." if plugin_ok else "The YouTube plugin is not discoverable."},
        {"name": "loopback-health", "ready": health_ok, "message": "The local PO-token provider is healthy." if health_ok else "The local PO-token provider is not healthy."},
    ])
    if not server_ok or not plugin_ok:
        return {"state": "REPAIR_REQUIRED", "ready": False, "dependency_state": "REPAIR_REQUIRED", "public_download_verified": False, "wpc": wpc_status, "reason": "Repair the installed YouTube support components, then test again.", "actions": ["Repair", "Retry"], "checks": checks}
    if not health_ok:
        return {"state": "UNHEALTHY", "ready": False, "dependency_state": "UNHEALTHY", "public_download_verified": False, "wpc": wpc_status, "reason": "The local YouTube support check failed. Start a test to retry safely.", "actions": ["Test", "Retry"], "checks": checks}
    public_verified = bool(public_status.get("verified"))
    return {"state": "PUBLIC_DOWNLOAD_VERIFIED" if public_verified else "DEPENDENCIES_READY", "ready": True, "dependency_state": "DEPENDENCIES_READY", "public_download_verified": public_verified, "public_compatibility": public_status, "wpc": wpc_status, "reason": "YouTube download was tested successfully." if public_verified else "YouTube tools are ready. A public download has not been verified on this installation.", "actions": ["Test"], "checks": checks}


def _merge_live_health_checks(status: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [dict(check) for check in status.get("checks", []) if isinstance(check, dict)]
    live = {
        "plugin": (bool(result.get("plugin_discoverable")), "The YouTube plugin is discoverable.", "The YouTube plugin is not discoverable."),
        "loopback-health": (bool((result.get("health") or {}).get("healthy")), "The local PO-token provider is healthy.", "The local PO-token provider is not healthy."),
    }
    seen: set[str] = set()
    for check in checks:
        name = str(check.get("name", ""))
        if name in live:
            ready, success_message, failure_message = live[name]
            check.update({"ready": ready, "message": success_message if ready else failure_message})
            seen.add(name)
    for name, (ready, success_message, failure_message) in live.items():
        if name not in seen:
            checks.append({"name": name, "ready": ready, "message": success_message if ready else failure_message})
    return checks


def test() -> dict[str, Any]:
    """Start the loopback provider for one health check, then always stop it."""
    status = readiness()
    if status["state"] not in {"READY", "DEPENDENCIES_READY", "PUBLIC_DOWNLOAD_VERIFIED", "UNHEALTHY"}:
        return status
    supervisor = ProviderSupervisor()
    try:
        supervisor.start()
        result = supervisor.self_test()
        checks = _merge_live_health_checks(status, result)
        if result.get("ok"):
            return {**status, "state": "PUBLIC_DOWNLOAD_VERIFIED" if status.get("public_download_verified") else "DEPENDENCIES_READY", "ready": True, "dependency_state": "DEPENDENCIES_READY", "checks": checks, "reason": "YouTube tools are ready. A public download still needs to be verified by a real transfer.", "actions": ["Test"]}
        return {**status, "state": "UNHEALTHY", "ready": False, "checks": checks, "reason": "The local YouTube support check failed. Repair the provider and test again.", "actions": ["Repair", "Test"]}
    except (OSError, RuntimeError, runtime.RuntimeIntegrityError) as error:
        return {**status, "state": "UNHEALTHY", "ready": False, "reason": "The local YouTube support provider could not start for its health check.", "actions": ["Repair", "Test"], "error": str(error)}
    finally:
        supervisor.stop()


def install(*, event: downloads.EventFn | None = None, cancel: Callable[[], bool] | None = None, require_consent: bool = True) -> dict[str, Any]:
    manager = downloads.DownloadManager(event=event)
    group_assets = assets()
    if require_consent and not manager.has_consent(PROVIDER_GROUP, group_assets):
        raise downloads.ConsentRequiredError("Consent is required before installing YouTube compatibility")
    archives = manager.download_group(group_assets, group_id=PROVIDER_GROUP, cancel=cancel) if require_consent else [manager.download(asset, cancel=cancel) for asset in group_assets]
    _extract_assets(manager, archives)
    node = node_path()
    npm = npm_path()
    server = server_home()
    if not node.is_file() or not npm.is_file():
        raise runtime.RuntimeIntegrityError("managed Node.js runtime is missing after verified extraction")
    if not (server / "node_modules").is_dir() or not (server / "build" / "main.js").is_file():
        event and event({"asset_id": "youtube:bgutil-server:1.3.2", "display_name": "PO-token provider", "operation": "Installing locked provider dependencies", "bytes_done": 0, "bytes_total": None, "bytes_per_second": 0.0, "fraction": None, "eta_seconds": None, "elapsed_seconds": 0.0, "one_time_download": True, "cached": False, "state": "INSTALLING"})
        env = os.environ.copy()
        env.update({"npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false"})
        subprocess.run([str(npm), "ci", "--no-audit", "--no-fund"], cwd=server, env=env, check=True, timeout=900)
        subprocess.run([str(npm), "exec", "tsc", "--", "--pretty", "false"], cwd=server, env=env, check=True, timeout=900)
    return {
        "provider_version": PROVIDER_VERSION,
        "node_version": NODE_VERSION,
        "node_path": str(node),
        "server_home": str(server),
        "plugin_dir": str(plugin_dir()),
        "endpoint": f"http://127.0.0.1:{DEFAULT_PORT}",
        "installed": _server_ready(),
    }


@dataclass
class ProviderHandle:
    process: subprocess.Popen[Any]
    endpoint: str


class ProviderSupervisor:
    def __init__(self) -> None:
        self.handle: ProviderHandle | None = None

    def health(self) -> dict[str, Any]:
        try:
            response = httpx.get(f"http://127.0.0.1:{DEFAULT_PORT}/ping", timeout=1.5, follow_redirects=False)
            if response.status_code == 200:
                payload = response.json()
                return {"running": True, "healthy": payload.get("version") == PROVIDER_VERSION, **payload}
        except (httpx.HTTPError, ValueError):
            pass
        return {"running": False, "healthy": False, "version": None}

    def start(self) -> str:
        if self.handle and self.handle.process.poll() is None and self.health().get("healthy"):
            return self.handle.endpoint
        if not _server_ready():
            raise runtime.RuntimeIntegrityError("YouTube compatibility is not installed. Open Setup Center to install it.")
        command = [str(node_path()), "build/main.js", "--port", str(DEFAULT_PORT)]
        env = os.environ.copy()
        env["PATH"] = str(node_path().parent) + os.pathsep + env.get("PATH", "")
        log_path = _root() / "provider.log"
        log = log_path.open("ab")
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        kwargs: dict[str, Any] = {
            "cwd": str(server_home()), "stdin": subprocess.DEVNULL,
            "stdout": log, "stderr": log, "creationflags": creationflags,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        endpoint = f"http://127.0.0.1:{DEFAULT_PORT}"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise runtime.RuntimeIntegrityError("The managed PO-token provider exited before becoming healthy.")
            if self.health().get("healthy"):
                self.handle = ProviderHandle(process=process, endpoint=endpoint)
                return endpoint
            time.sleep(0.25)
        self.stop()
        raise runtime.RuntimeIntegrityError("The managed PO-token provider did not become healthy within 30 seconds.")

    def stop(self) -> None:
        if not self.handle:
            return
        process = self.handle.process
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self.handle = None

    def self_test(self) -> dict[str, Any]:
        health = self.health()
        plugin_ok = (plugin_dir() / "yt_dlp_plugins" / "extractor" / "getpot_bgutil_http.py").is_file()
        server_ok = _server_ready()
        return {
            "provider_version": PROVIDER_VERSION,
            "plugin_discoverable": plugin_ok,
            "server_installed": server_ok,
            "health": health,
            "loopback_only": True,
            "ok": plugin_ok and server_ok and bool(health.get("healthy")),
        }

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
