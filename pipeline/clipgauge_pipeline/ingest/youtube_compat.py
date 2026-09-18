"""Managed yt-dlp PO-token compatibility for ClipGauge v0.4.

The provider is optional and explicit.  This module owns a pinned portable
Node runtime and tagged bgutil source, binds the HTTP provider to loopback,
and never reads browser cookies or starts a network service implicitly.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .. import config, downloads, runtime

DownloadManager = downloads.DownloadManager

PROVIDER_VERSION = "2.0.0"
NODE_VERSION = "24.19.0"
PROVIDER_GROUP = "core:youtube"
DEFAULT_PORT = 4416
STARTUP_TIMEOUT_SECONDS = 30.0
PUBLIC_COMPATIBILITY_FILENAME = "youtube-public-compatibility.json"
PROVIDER_SOURCE_URL = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/2.0.0.zip"
PROVIDER_SOURCE_SHA256 = "e95324ee24b1b0f1b4ad43d336343afe7cf1914acdf65d9cc1977f51d7b137c2"
PROVIDER_SOURCE_SIZE_BYTES = 126_968
PROVIDER_SOURCE_ROOT = "bgutil-ytdlp-pot-provider-2.0.0"
PROVIDER_PLUGIN_RELATIVE = "plugin/yt_dlp_plugins/extractor/getpot_bgutil_http.py"
SOURCE_REQUIRED_FILES = (
    "server/package.json",
    "server/package-lock.json",
    "server/tsconfig.json",
    "server/src/main.ts",
    "server/src/generate_once.ts",
    "server/src/session_manager.ts",
    "server/src/utils.ts",
    "server/types/commander.d.ts",
    "plugin/yt_dlp_plugins/extractor/getpot_bgutil.py",
    "plugin/yt_dlp_plugins/extractor/getpot_bgutil_http.py",
    "plugin/yt_dlp_plugins/extractor/getpot_bgutil_script.py",
)
WPC_VERSION = "1.1.2"
WPC_SOURCE = "https://github.com/coletdjnz/yt-dlp-getpot-wpc/tree/v1.1.2"
WPC_LICENSE = "MIT"


def _atomic_write_text(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    archive = _root() / f"bgutil-ytdlp-pot-provider-{PROVIDER_VERSION}.zip"
    return downloads.ManagedAsset(
        asset_id=f"youtube:bgutil-provider:{PROVIDER_VERSION}",
        display_name="YouTube PO-token provider",
        purpose="yt-dlp plugin and loopback PO-token server source",
        destination=str(archive.relative_to(config.home_dir())),
        url=PROVIDER_SOURCE_URL,
        size_bytes=PROVIDER_SOURCE_SIZE_BYTES,
        sha256=PROVIDER_SOURCE_SHA256,
        required=True,
        one_time=True,
        license="GPL-3.0-only",
        source="https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/2.0.0",
        consent_group=PROVIDER_GROUP,
        archive_type="zip",
        source_revision=PROVIDER_VERSION,
        platform=platform_key(),
    )


def assets() -> list[downloads.ManagedAsset]:
    from . import ytdlp

    return [node_asset(), provider_source_asset(), ytdlp.managed_asset()]


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
    return _root() / "source" / PROVIDER_SOURCE_ROOT


def server_home() -> Path:
    return source_home() / "server"


def plugin_home() -> Path:
    return _root() / "plugin"


def plugin_dir() -> Path:
    return plugin_home()


def _provider_plugin_ready() -> bool:
    extractor = plugin_dir() / "yt_dlp_plugins" / "extractor"
    return all(_nonempty_file(extractor / name) for name in (
        "getpot_bgutil.py",
        "getpot_bgutil_http.py",
        "getpot_bgutil_script.py",
    ))


def _node_install_ready() -> bool:
    return _nonempty_file(node_path()) and _nonempty_file(npm_path())


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _node_modules_ready(server: Path | None = None) -> bool:
    provider_server = server or server_home()
    modules = provider_server / "node_modules"
    try:
        if not modules.is_dir():
            return False
        package = json.loads((provider_server / "package.json").read_text(encoding="utf-8"))
        source_lockfile = json.loads((provider_server / "package-lock.json").read_text(encoding="utf-8"))
        lockfile = json.loads((modules / ".package-lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(package, dict) or not isinstance(source_lockfile, dict) or not isinstance(lockfile, dict):
        return False
    dependencies = package.get("dependencies", {})
    dev_dependencies = package.get("devDependencies", {})
    if not isinstance(dependencies, dict) or not isinstance(dev_dependencies, dict):
        return False
    required_packages = set(dependencies) | set(dev_dependencies)
    if "typescript" not in required_packages:
        return False
    if (
        source_lockfile.get("lockfileVersion") != 3
        or not isinstance(source_lockfile.get("packages"), dict)
        or lockfile.get("lockfileVersion") != 3
        or not isinstance(lockfile.get("packages"), dict)
    ):
        return False
    source_packages = source_lockfile["packages"]
    installed_packages = lockfile["packages"]
    for package_path, source_entry in source_packages.items():
        if package_path and package_path not in installed_packages:
            if not isinstance(source_entry, dict) or not source_entry.get("optional"):
                return False
    for package_path, source_entry in source_packages.items():
        if not package_path:
            continue
        installed_entry = installed_packages.get(package_path)
        if installed_entry is None:
            continue
        if not isinstance(source_entry, dict) or not isinstance(installed_entry, dict):
            return False
        source_version = source_entry.get("version")
        if source_version is not None and installed_entry.get("version") != source_version:
            return False
    for package_path in installed_packages:
        if not isinstance(package_path, str) or not package_path.startswith("node_modules/"):
            continue
        if package_path not in source_packages:
            return False
        package_dir = modules / package_path.removeprefix("node_modules/")
        if not _nonempty_file(package_dir / "package.json"):
            return False
    for package_name in required_packages:
        package_json = modules / package_name / "package.json"
        if not _nonempty_file(package_json):
            return False
    compiler = modules / ".bin"
    return _nonempty_file(compiler / "tsc") or _nonempty_file(compiler / "tsc.cmd")


def _source_install_ready() -> bool:
    source = source_home()
    if not source.is_dir() or not all(_nonempty_file(source / relative) for relative in SOURCE_REQUIRED_FILES):
        return False
    try:
        package = json.loads((source / "server" / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((source / "server" / "package-lock.json").read_text(encoding="utf-8"))
        tsconfig = json.loads((source / "server" / "tsconfig.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(package, dict)
        and package.get("name") == "bgutil-ytdlp-pot-provider"
        and package.get("version") == PROVIDER_VERSION
        and isinstance(package.get("dependencies"), dict)
        and isinstance(package.get("scripts"), dict)
        and isinstance(lockfile, dict)
        and lockfile.get("lockfileVersion") == 3
        and isinstance(lockfile.get("packages"), dict)
        and isinstance(tsconfig, dict)
        and isinstance(tsconfig.get("compilerOptions"), dict)
        and isinstance(tsconfig.get("include"), list)
    )


def _remove_managed_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _atomic_replace_managed_tree(staged: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.{time.time_ns()}.backup")
    had_destination = destination.exists() or destination.is_symlink()
    if had_destination:
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except Exception:
        if had_destination and backup.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        _remove_managed_tree(backup)


def _cleanup_interrupted_tree(parent: Path, root_name: str) -> None:
    _cleanup_interrupted_prefix(parent, f".{root_name}.")


def _cleanup_interrupted_prefix(parent: Path, prefix: str) -> None:
    if not parent.is_dir():
        return
    try:
        entries = tuple(parent.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name.startswith(prefix):
            _remove_managed_tree(entry)


def _extract_archive_tree(archive: Path, destination_parent: Path, root_name: str, archive_type: str) -> None:
    destination_parent.mkdir(parents=True, exist_ok=True)
    _cleanup_interrupted_tree(destination_parent, root_name)
    staging = Path(tempfile.mkdtemp(prefix=f".{root_name}.", dir=destination_parent))
    try:
        runtime.extract_archive_verified(archive, staging, archive_type=archive_type)
        extracted_root = staging / root_name
        if not extracted_root.is_dir():
            raise runtime.RuntimeIntegrityError("YOUTUBE_PROVIDER_POSTCONDITION_FAILED: archive layout is incomplete")
        _atomic_replace_managed_tree(extracted_root, destination_parent / root_name)
    finally:
        if staging.exists():
            _remove_managed_tree(staging)


def _install_plugin_tree() -> None:
    plugin_source = source_home() / "plugin" / "yt_dlp_plugins"
    if not all(_nonempty_file(plugin_source / "extractor" / name) for name in (
        "getpot_bgutil.py",
        "getpot_bgutil_http.py",
        "getpot_bgutil_script.py",
    )):
        raise runtime.RuntimeIntegrityError("YOUTUBE_PLUGIN_MISSING: provider archive has no HTTP plugin")
    plugin_parent = plugin_home()
    plugin_parent.mkdir(parents=True, exist_ok=True)
    _cleanup_interrupted_tree(plugin_parent, "yt_dlp_plugins")
    staging = Path(tempfile.mkdtemp(prefix=".yt_dlp_plugins.", dir=plugin_parent))
    try:
        staged = staging / "yt_dlp_plugins"
        shutil.copytree(plugin_source, staged)
        if not all(_nonempty_file(staged / "extractor" / name) for name in (
            "getpot_bgutil.py",
            "getpot_bgutil_http.py",
            "getpot_bgutil_script.py",
        )):
            raise runtime.RuntimeIntegrityError("YOUTUBE_PLUGIN_MISSING: provider plugin copy is incomplete")
        _atomic_replace_managed_tree(staged, plugin_parent / "yt_dlp_plugins")
    finally:
        if staging.exists():
            _remove_managed_tree(staging)


def _extract_assets(manager: downloads.DownloadManager, archives: list[Path]) -> None:
    node_archive, provider_archive = archives
    spec = NODE_SPECS[platform_key()]
    _cleanup_interrupted_tree(_root() / "node", spec.root_name)
    _cleanup_interrupted_tree(_root() / "source", PROVIDER_SOURCE_ROOT)
    if not _node_install_ready():
        _extract_archive_tree(node_archive, _root() / "node", spec.root_name, spec.archive_type)
    if not _source_install_ready():
        _extract_archive_tree(provider_archive, _root() / "source", PROVIDER_SOURCE_ROOT, "zip")
    if not _provider_plugin_ready():
        _install_plugin_tree()


def _server_ready() -> bool:
    server = server_home()
    return (
        _node_install_ready()
        and _source_install_ready()
        and _node_modules_ready(server)
        and _build_ready(server / "build")
        and _provider_plugin_ready()
    )


def _build_ready(build: Path) -> bool:
    main = build / "main.js"
    try:
        return main.is_file() and main.stat().st_size > 0
    except OSError:
        return False


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
    current_provider = payload.get("provider_version") == PROVIDER_VERSION
    return {key: payload[key] for key in allowed if key in payload} | {"verified": bool(payload.get("verified")) and current_provider}


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
    try:
        _atomic_write_text(path, json.dumps(payload, sort_keys=True))
    except OSError:
        pass


def record_public_compatibility_success(*, method: str, ytdlp_version: str, provider_version: str = PROVIDER_VERSION) -> None:
    """Cache successful public compatibility metadata, never tokens or session data."""
    config.ensure_home()
    payload = {
        "verified": True,
        "verified_at": datetime.now(UTC).isoformat(),
        "yt_dlp_version": str(ytdlp_version)[:64],
        "provider_version": str(provider_version)[:64],
        "method": str(method)[:64],
    }
    path = _public_compatibility_path()
    _atomic_write_text(path, json.dumps(payload, sort_keys=True))


def _find_browser() -> str | None:
    """Detect an installed browser without launching it or reading its profile."""
    names = [
        "chrome", "chrome.exe", "msedge", "msedge.exe", "chromium", "chromium.exe",
        "firefox", "firefox.exe", "google-chrome", "google-chrome-stable", "chromium-browser",
    ]
    candidates: list[Path] = []
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    roots = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    relative_paths = [
        Path("Google/Chrome/Application/chrome.exe"),
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Chromium/Application/chrome.exe"),
        Path("Mozilla Firefox/firefox.exe"),
    ]
    candidates.extend(Path(root) / relative for root in roots if root for relative in relative_paths)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return None


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
    dependency_checked_at = datetime.now(UTC).isoformat()
    public_transfer_at = public_status.get("verified_at")
    wpc_status = wpc_availability()
    ytdlp_ok = _yt_dlp_ready()
    checks.append({"name": "yt-dlp", "ready": ytdlp_ok, "message": "Pinned yt-dlp is verified." if ytdlp_ok else "Pinned yt-dlp is not installed or failed verification."})
    if not ytdlp_ok:
        return {"state": "NOT_INSTALLED", "ready": False, "dependency_state": "NOT_INSTALLED", "public_download_verified": False, "public_transfer_verified_at": public_transfer_at, "dependency_checked_at": dependency_checked_at, "provider_self_tested_at": None, "wpc": wpc_status, "reason": "Install the verified YouTube runtime before testing public links.", "actions": ["Install"], "checks": checks}

    rows = DownloadManager().inventory(assets())
    installed = [bool(row.get("installed")) for row in rows]
    checks.extend({"name": str(row.get("asset_id", "youtube-asset")), "ready": bool(row.get("installed")), "message": "Verified asset is installed." if row.get("installed") else "Verified asset is missing or needs repair."} for row in rows)
    if not all(installed):
        state = "NOT_INSTALLED" if not any(installed) else "INSTALL_INCOMPLETE"
        return {"state": state, "ready": False, "dependency_state": state, "public_download_verified": False, "public_transfer_verified_at": public_transfer_at, "dependency_checked_at": dependency_checked_at, "provider_self_tested_at": None, "wpc": wpc_status, "reason": "Install the complete YouTube support bundle, then test it.", "actions": ["Install", "Retry"], "checks": checks}

    if not _server_ready():
        checks.append({"name": "provider-build", "ready": False, "message": "The PO-token provider build or plugin is incomplete."})
        return {"state": "BUILD_REQUIRED", "ready": False, "dependency_state": "BUILD_REQUIRED", "public_download_verified": False, "public_transfer_verified_at": public_transfer_at, "dependency_checked_at": dependency_checked_at, "provider_self_tested_at": None, "wpc": wpc_status, "reason": "Build the installed PO-token provider before using YouTube.", "actions": ["Repair", "Retry"], "checks": checks}

    plugin_ok = _provider_plugin_ready()
    checks.append({"name": "plugin", "ready": plugin_ok, "message": "The YouTube plugin is discoverable." if plugin_ok else "The YouTube plugin is not discoverable."})
    if not plugin_ok:
        return {"state": "REPAIR_REQUIRED", "ready": False, "dependency_state": "REPAIR_REQUIRED", "public_download_verified": False, "public_transfer_verified_at": public_transfer_at, "dependency_checked_at": dependency_checked_at, "provider_self_tested_at": None, "wpc": wpc_status, "reason": "Repair the installed YouTube support components, then test again.", "actions": ["Repair", "Retry"], "checks": checks}
    checks.append({
        "name": "provider-lifecycle",
        "ready": True,
        "message": "The managed provider starts when a YouTube operation begins.",
    })
    public_verified = bool(public_status.get("verified"))
    return {"state": "PUBLIC_DOWNLOAD_VERIFIED" if public_verified else "DEPENDENCIES_READY", "ready": True, "dependency_state": "DEPENDENCIES_READY", "provider_state": "DORMANT", "public_download_verified": public_verified, "public_transfer_verified_at": public_transfer_at, "dependency_checked_at": dependency_checked_at, "provider_self_tested_at": None, "public_compatibility": public_status, "wpc": wpc_status, "reason": "YouTube download was tested successfully." if public_verified else "YouTube tools are ready. A public download has not been verified on this installation.", "actions": ["Test"], "checks": checks}


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


_STARTUP_ERROR_MESSAGES = {
    "BUILD_MISSING": "YouTube compatibility service is not built. Repair it from Setup Center.",
    "HEALTH_TIMEOUT": "YouTube compatibility service did not become healthy before the startup timeout.",
    "NODE_FAILURE": "YouTube compatibility service could not start its managed runtime.",
    "PORT_IN_USE": "Another process is using the required local YouTube compatibility port.",
    "PROCESS_EXITED": "YouTube compatibility service exited before becoming healthy.",
    "VERSION_MISMATCH": "Another process is using the YouTube compatibility port with the wrong provider version.",
}


def startup_error_code(error: BaseException) -> str:
    code = str(error).split(":", 1)[0].strip()
    return code if code in _STARTUP_ERROR_MESSAGES else "UNKNOWN_STARTUP_FAILURE"


def startup_error_message(code: str) -> str:
    return _STARTUP_ERROR_MESSAGES.get(code, "YouTube compatibility service could not start.")


def test() -> dict[str, Any]:
    """Start the loopback provider for one health check, then always stop it."""
    status = readiness()
    if status["state"] not in {"READY", "DEPENDENCIES_READY", "PUBLIC_DOWNLOAD_VERIFIED", "UNHEALTHY"}:
        return status
    supervisor = ProviderSupervisor()
    try:
        supervisor.start()
        result = supervisor.self_test()
        provider_self_tested_at = datetime.now(UTC).isoformat()
        checks = _merge_live_health_checks(status, result)
        if result.get("ok"):
            return {**status, "state": "PUBLIC_DOWNLOAD_VERIFIED" if status.get("public_download_verified") else "DEPENDENCIES_READY", "ready": True, "dependency_state": "DEPENDENCIES_READY", "provider_self_tested_at": provider_self_tested_at, "checks": checks, "reason": "Provider self-test passed. A public download still needs to be verified by a real transfer.", "actions": ["Test"]}
        return {**status, "state": "UNHEALTHY", "ready": False, "provider_self_tested_at": provider_self_tested_at, "checks": checks, "reason": "The local YouTube support check failed. Repair the provider and test again.", "actions": ["Repair", "Test"]}
    except (OSError, RuntimeError, runtime.RuntimeIntegrityError) as error:
        code = startup_error_code(error)
        return {**status, "state": "UNHEALTHY", "ready": False, "startup_error_code": code, "reason": startup_error_message(code), "actions": ["Repair", "Test"], "error": str(error)}
    finally:
        supervisor.stop()


def _sanitize_provider_diagnostics(value: str | None) -> str:
    lines = []
    for line in (value or "").splitlines():
        sanitized = re.sub(r"[A-Za-z]:[^\r\n]*", "<path>", line)
        sanitized = re.sub(r"/(?:[^/\s]+/)+[^/\s]*", "<path>", sanitized)
        lines.append(sanitized[:240])
    return " ".join(lines)[-800:]


def _run_provider_command(args: list[str], *, cwd: Path, failure_code: str, event: downloads.EventFn | None) -> None:
    environment = os.environ.copy()
    managed_node_bin = node_path().parent
    ambient_path = environment.get("PATH", "")
    environment["PATH"] = os.pathsep.join(filter(None, (str(managed_node_bin), ambient_path)))
    environment.update({
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_update_notifier": "false",
    })
    try:
        _completed = subprocess.run(
            args,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        raise runtime.RuntimeIntegrityError(f"{failure_code}: command timed out") from exc
    except subprocess.CalledProcessError as exc:
        diagnostics = _sanitize_provider_diagnostics(exc.stderr or exc.stdout)
        suffix = f": {diagnostics}" if diagnostics else ""
        raise runtime.RuntimeIntegrityError(f"{failure_code}{suffix}") from exc
    if event:
        event({
            "asset_id": f"youtube:bgutil-provider:{PROVIDER_VERSION}",
            "display_name": "PO-token provider",
            "operation": "Provider command completed",
            "bytes_done": 0,
            "bytes_total": None,
            "bytes_per_second": 0.0,
            "fraction": None,
            "eta_seconds": None,
            "elapsed_seconds": 0.0,
            "one_time_download": True,
            "cached": False,
            "state": "INSTALLED",
            "command": args[1] if len(args) > 1 else args[0],
        })


def _build_provider(npm: Path, server: Path, *, event: downloads.EventFn | None) -> None:
    _cleanup_interrupted_tree(server, "build")
    _cleanup_interrupted_prefix(server, ".provider-build-")
    _cleanup_interrupted_prefix(server, ".provider-build.")
    staging = Path(tempfile.mkdtemp(prefix=".provider-build-", dir=server))
    staged_build = staging / "build"
    try:
        _run_provider_command(
            [
                str(npm),
                "exec",
                "tsc",
                "--",
                "--pretty",
                "false",
                "--outDir",
                str(staged_build),
            ],
            cwd=server,
            failure_code="YOUTUBE_PROVIDER_BUILD_FAILED",
            event=event,
        )
        if not _build_ready(staged_build):
            _raise_install_code(
                "YOUTUBE_PROVIDER_POSTCONDITION_FAILED",
                "provider compiler produced no complete server entrypoint",
            )
        _atomic_replace_managed_tree(staged_build, server / "build")
    finally:
        if staging.exists():
            _remove_managed_tree(staging)


def _raise_install_code(code: str, message: str) -> None:
    raise runtime.RuntimeIntegrityError(f"{code}: {message}")


def install(*, event: downloads.EventFn | None = None, cancel: Callable[[], bool] | None = None, require_consent: bool = True) -> dict[str, Any]:
    manager = downloads.DownloadManager(event=event)
    group_assets = assets()
    if require_consent and not manager.has_consent(PROVIDER_GROUP, group_assets):
        raise downloads.ConsentRequiredError("Consent is required before installing YouTube compatibility")
    archives = manager.download_group(group_assets, group_id=PROVIDER_GROUP, cancel=cancel) if require_consent else [manager.download(asset, cancel=cancel) for asset in group_assets]
    _extract_assets(manager, archives[:2])
    node = node_path()
    npm = npm_path()
    server = server_home()
    if not node.is_file() or not npm.is_file():
        _raise_install_code("YOUTUBE_NODE_MISSING", "managed Node.js runtime is missing after verified extraction")
    if not _source_install_ready():
        _raise_install_code("YOUTUBE_PROVIDER_POSTCONDITION_FAILED", "provider source layout is incomplete")
    if not _provider_plugin_ready():
        _raise_install_code("YOUTUBE_PLUGIN_MISSING", "provider plugin is not installed")
    if not _node_modules_ready(server):
        if (server / "node_modules").exists():
            _remove_managed_tree(server / "node_modules")
        event and event({"asset_id": f"youtube:bgutil-server:{PROVIDER_VERSION}", "display_name": "PO-token provider", "operation": "Installing locked provider dependencies", "bytes_done": 0, "bytes_total": None, "bytes_per_second": 0.0, "fraction": None, "eta_seconds": None, "elapsed_seconds": 0.0, "one_time_download": True, "cached": False, "state": "INSTALLING"})
        _run_provider_command([str(npm), "ci", "--no-audit", "--no-fund"], cwd=server, failure_code="YOUTUBE_NPM_INSTALL_FAILED", event=event)
    if not _build_ready(server / "build"):
        event and event({"asset_id": f"youtube:bgutil-server:{PROVIDER_VERSION}", "display_name": "PO-token provider", "operation": "Building the managed provider", "bytes_done": 0, "bytes_total": None, "bytes_per_second": 0.0, "fraction": None, "eta_seconds": None, "elapsed_seconds": 0.0, "one_time_download": True, "cached": False, "state": "BUILDING"})
        _build_provider(npm, server, event=event)
    if not _server_ready():
        _raise_install_code("YOUTUBE_PROVIDER_POSTCONDITION_FAILED", "provider build, node runtime, or plugin is incomplete")
    supervisor = ProviderSupervisor()
    try:
        endpoint = supervisor.start()
        result = supervisor.self_test()
        if not result.get("plugin_discoverable"):
            _raise_install_code("YOUTUBE_PLUGIN_MISSING", "provider plugin discovery failed")
        if not result.get("server_installed"):
            _raise_install_code("YOUTUBE_PROVIDER_POSTCONDITION_FAILED", "provider server postcondition failed")
        if not (result.get("health") or {}).get("healthy"):
            _raise_install_code("YOUTUBE_PROVIDER_HEALTH_FAILED", "provider loopback health check failed")
    except runtime.RuntimeIntegrityError as error:
        if "PORT_IN_USE" in str(error):
            _raise_install_code("YOUTUBE_PORT_IN_USE", "the managed provider port is occupied")
        if str(error).startswith(("BUILD_MISSING", "NODE_FAILURE", "PROCESS_EXITED", "HEALTH_TIMEOUT")):
            _raise_install_code("YOUTUBE_PROVIDER_HEALTH_FAILED", "provider loopback health check failed")
        raise
    finally:
        supervisor.stop()
    return {
        "provider_version": PROVIDER_VERSION,
        "node_version": NODE_VERSION,
        "node_path": str(node),
        "server_home": str(server),
        "plugin_dir": str(plugin_dir()),
        "endpoint": endpoint,
        "installed": True,
    }


@dataclass
class ProviderHandle:
    process: subprocess.Popen[Any]
    endpoint: str


class ProviderSupervisor:
    def __init__(self) -> None:
        self.handle: ProviderHandle | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _endpoint_for_health(result: dict[str, Any]) -> str:
        family = result.get("address_family")
        return f"http://[::1]:{DEFAULT_PORT}" if family == "ipv6" else f"http://127.0.0.1:{DEFAULT_PORT}"

    @staticmethod
    def _port_occupied() -> bool:
        for family, address in ((socket.AF_INET, ("127.0.0.1", DEFAULT_PORT)), (socket.AF_INET6, ("::1", DEFAULT_PORT))):
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(0.25)
            try:
                if sock.connect_ex(address) == 0:
                    return True
            finally:
                sock.close()
        return False

    def health(self) -> dict[str, Any]:
        observed: list[dict[str, Any]] = []
        for family, url in (
            ("ipv4", f"http://127.0.0.1:{DEFAULT_PORT}/ping"),
            ("ipv6", f"http://[::1]:{DEFAULT_PORT}/ping"),
        ):
            try:
                response = httpx.get(url, timeout=1.5, follow_redirects=False)
                if response.status_code != 200:
                    continue
                payload = response.json()
                if not isinstance(payload, dict):
                    payload = {}
                result = {"running": True, "healthy": payload.get("version") == PROVIDER_VERSION, "address_family": family, **payload}
                observed.append(result)
                if result["healthy"]:
                    return result
            except (httpx.HTTPError, ValueError):
                continue
        if observed:
            return observed[0]
        return {"running": False, "healthy": False, "version": None}

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                try:
                    process.terminate()
                except OSError:
                    pass
        else:
            try:
                process.terminate()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    process.kill()
                except OSError:
                    pass
        else:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def start(self) -> str:
        with self._lock:
            if self.handle:
                if self.handle.process.poll() is None:
                    current = self.health()
                    if current.get("healthy"):
                        self.handle.endpoint = self._endpoint_for_health(current)
                        return self.handle.endpoint
                self.stop()

            existing = self.health()
            if existing.get("running"):
                if existing.get("healthy") and existing.get("version") == PROVIDER_VERSION:
                    return self._endpoint_for_health(existing)
                if existing.get("version") is not None:
                    raise runtime.RuntimeIntegrityError(f"VERSION_MISMATCH: provider port returned version {existing.get('version')}")
                raise runtime.RuntimeIntegrityError("PORT_IN_USE: provider port is occupied by an unrelated listener")
            if self._port_occupied():
                raise runtime.RuntimeIntegrityError("PORT_IN_USE: provider port is occupied by an unrelated listener")
            if not _server_ready():
                raise runtime.RuntimeIntegrityError("BUILD_MISSING: YouTube compatibility provider is not installed or built.")

            command = [str(node_path()), "build/main.js", "--port", str(DEFAULT_PORT), "--host", "127.0.0.1,::1"]
            env = os.environ.copy()
            env["PATH"] = str(node_path().parent) + os.pathsep + env.get("PATH", "")
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            kwargs: dict[str, Any] = {
                "cwd": str(server_home()), "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                "creationflags": creationflags,
            }
            if os.name != "nt":
                kwargs["start_new_session"] = True
            try:
                process = subprocess.Popen(command, **kwargs)
            except OSError as error:
                raise runtime.RuntimeIntegrityError(f"NODE_FAILURE: managed provider could not be spawned: {error}") from error

            endpoint = f"http://127.0.0.1:{DEFAULT_PORT}"
            self.handle = ProviderHandle(process=process, endpoint=endpoint)
            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            try:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise runtime.RuntimeIntegrityError("PROCESS_EXITED: managed PO-token provider exited before becoming healthy")
                    health = self.health()
                    if health.get("healthy"):
                        self.handle.endpoint = self._endpoint_for_health(health)
                        return self.handle.endpoint
                    time.sleep(0.25)
                raise runtime.RuntimeIntegrityError("HEALTH_TIMEOUT: managed PO-token provider did not become healthy before the startup timeout")
            except Exception:
                self.stop()
                raise

    def stop(self) -> None:
        with self._lock:
            handle = self.handle
            self.handle = None
            if not handle:
                return
            self._terminate_process(handle.process)

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
        with suppress(Exception):
            self.stop()
