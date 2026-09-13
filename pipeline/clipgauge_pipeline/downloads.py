"""Unified managed asset downloads for ClipGauge v0.4.

Every runtime/model download enters through this module.  The manager persists
asset state and grouped consent, delegates verified bytes and safe extraction to
``runtime``, and never executes downloaded content before an adapter's own
capability check has passed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from . import __version__, config, runtime


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
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
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class ManagedAsset:
    asset_id: str
    display_name: str
    purpose: str
    destination: str
    url: str
    size_bytes: int
    sha256: str
    required: bool = True
    one_time: bool = True
    license: str = "See upstream source"
    source: str = ""
    consent_group: str = "core"
    installed_size_bytes: int | None = None
    archive_type: str | None = None
    source_revision: str = ""
    platform: str = ""
    dependencies: tuple[str, ...] = ()
    expected_paths: tuple[str, ...] = ()
    download_destination: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


EventFn = Callable[[dict[str, Any]], None]
CancelFn = Callable[[], bool]


class ConsentRequiredError(RuntimeError):
    """The requested asset group has not been explicitly approved."""


class VersionedInventoryCache:
    """Metadata-backed integrity cache for managed asset inventory."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path, *, app_version: str = "unknown", platform: str | None = None) -> None:
        self.path = path
        self.app_version = app_version
        self.platform = platform or sys.platform
        self.payload = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                isinstance(value, dict)
                and value.get("schema_version") == self.SCHEMA_VERSION
                and value.get("app_version") == self.app_version
            ):
                return value
        except (OSError, ValueError):
            pass
        return {
            "schema_version": self.SCHEMA_VERSION,
            "app_version": self.app_version,
            "platform": self.platform,
            "runtime_manifest_digest": "",
            "last_verified_at": None,
            "entries": {},
        }

    def set_context(self, manifest_digest: str) -> None:
        self.payload["platform"] = self.platform
        self.payload["runtime_manifest_digest"] = manifest_digest

    @staticmethod
    def key(asset: ManagedAsset) -> str:
        return f"{asset.asset_id}|{asset.destination}"

    @staticmethod
    def asset_manifest_digest(asset: ManagedAsset) -> str:
        manifest_record = {
            "asset_id": asset.asset_id,
            "destination": asset.destination,
            "sha256": asset.sha256,
            "size_bytes": asset.size_bytes,
            "platform": asset.platform,
            "source_revision": asset.source_revision,
        }
        return hashlib.sha256(json.dumps(manifest_record, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def file_identity(stat: os.stat_result) -> list[int] | None:
        device = getattr(stat, "st_dev", None)
        inode = getattr(stat, "st_ino", None)
        if not isinstance(device, int) or not isinstance(inode, int) or device <= 0 or inode <= 0:
            return None
        return [device, inode]

    def lookup(self, asset: ManagedAsset, destination: Path) -> dict[str, Any] | None:
        try:
            stat = destination.stat()
        except OSError:
            return None
        identity = self.file_identity(stat)
        if identity is None:
            return None
        entry = self.payload.get("entries", {}).get(self.key(asset))
        if not isinstance(entry, dict):
            return None
        if (
            entry.get("canonical_path") == str(destination.resolve())
            and entry.get("expected_hash", "").lower() == asset.sha256.lower()
            and entry.get("size") == stat.st_size
            and entry.get("mtime_ns") == stat.st_mtime_ns
            and entry.get("file_identity") == identity
            and entry.get("verified_hash", "").lower() == asset.sha256.lower()
            and entry.get("asset_manifest_digest") == self.asset_manifest_digest(asset)
            and entry.get("platform") == self.platform
        ):
            return entry
        return None

    def record(self, asset: ManagedAsset, destination: Path, verified_hash: str) -> None:
        try:
            stat = destination.stat()
        except OSError:
            return
        entries = self.payload.setdefault("entries", {})
        entries[self.key(asset)] = {
            "canonical_path": str(destination.resolve()),
            "expected_hash": asset.sha256,
            "verified_hash": verified_hash,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "file_identity": self.file_identity(stat),
            "verified_at": time.time(),
            "runtime_manifest_digest": self.payload.get("runtime_manifest_digest", ""),
            "asset_manifest_digest": self.asset_manifest_digest(asset),
            "platform": self.platform,
        }

    def save(self) -> None:
        self.payload["app_version"] = self.app_version
        self.payload["platform"] = self.platform
        verified_times = [
            entry.get("verified_at", 0)
            for entry in self.payload.get("entries", {}).values()
            if isinstance(entry, dict)
        ]
        if verified_times:
            self.payload["last_verified_at"] = max(verified_times)
        self.payload["updated_at"] = time.time()
        _write_json_atomic(self.path, self.payload)


class DownloadManager:
    # Tauri owns inventory-cache.json with a different multi-file schema.
    # Keep sidecar verification state separate to prevent cache thrashing.
    SIDECAR_INVENTORY_CACHE_FILENAME = "pipeline-inventory-cache.json"

    def __init__(self, root: Path | None = None, event: EventFn | None = None) -> None:
        self.root = (root or config.home_dir()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "downloads.json"
        self.consent_path = self.root / "download-consent.json"
        self.inventory_cache = VersionedInventoryCache(
            self.root / self.SIDECAR_INVENTORY_CACHE_FILENAME,
            app_version=__version__,
        )
        self.event = event
        self.state = self._load_json(self.state_path)
        self.consents = self._load_json(self.consent_path)
        self._cancelled: set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        _write_json_atomic(path, payload)

    def _save(self) -> None:
        with self._lock:
            self._atomic_json(self.state_path, self.state)

    def _save_consents(self) -> None:
        with self._lock:
            self._atomic_json(self.consent_path, self.consents)

    def _destination(self, asset: ManagedAsset) -> Path:
        destination = (self.root / asset.destination).resolve()
        if destination != self.root and self.root not in destination.parents:
            raise ValueError("managed asset destination escapes the ClipGauge data root")
        return destination

    def _download_destination(self, asset: ManagedAsset) -> Path:
        if not asset.download_destination:
            return self._destination(asset)
        destination = (self.root / asset.download_destination).resolve()
        if destination != self.root and self.root not in destination.parents:
            raise ValueError("managed asset download destination escapes the ClipGauge data root")
        return destination

    def _emit(self, payload: dict[str, Any]) -> None:
        if self.event:
            self.event(payload)

    def cancel(self, asset_id: str) -> None:
        self._cancelled.add(asset_id)

    def clear_cancel(self, asset_id: str) -> None:
        self._cancelled.discard(asset_id)

    def _is_cancelled(self, asset_id: str, cancel: CancelFn | None) -> bool:
        return asset_id in self._cancelled or bool(cancel and cancel())

    def _asset_ready(self, asset: ManagedAsset, destination: Path) -> tuple[bool, str | None]:
        if not destination.is_file():
            return False, None
        try:
            size_ok = asset.size_bytes <= 0 or destination.stat().st_size == asset.size_bytes
            digest = runtime.sha256_file(destination)
        except OSError:
            return False, None
        if size_ok and digest.lower() == asset.sha256.lower():
            return True, digest
        return False, digest

    def inventory(self, assets: Iterable[ManagedAsset], *, verify: bool = True) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for asset in assets:
            destination = self._destination(asset)
            state = self.state.get(asset.asset_id, {})
            if verify:
                installed, digest = self._asset_ready(asset, destination)
                verification = "fresh-hash"
            else:
                persisted_status = str(state.get("status", "")).lower()
                installed = destination.is_file() and persisted_status in {"installed", "reused", "ready"}
                digest = asset.sha256 if installed and asset.sha256 else None
                verification = "persisted-state" if installed else "not-verified"
            status = "ready" if installed else state.get("status", "not-installed")
            if destination.is_file() and not installed and digest:
                status = "needs-repair"
            cached = installed or status in {"ready", "reused", "installed"}
            rows.append(
                {
                    **asset.to_json(),
                    "installed": installed,
                    "cached": cached,
                    "installed_sha256": digest,
                    "verification": verification,
                    "status": status,
                    "state": status.upper().replace("-", "_"),
                    "managed_path": str(destination),
                    "consent_granted": self.has_consent(asset.consent_group, [asset]),
                }
            )
        return rows

    def inventory_cached(self, assets: Iterable[ManagedAsset], *, verify: bool = True) -> list[dict[str, Any]]:
        """Inventory assets while reusing unchanged verified file metadata."""
        asset_list = list(assets)
        manifest_path = Path(__file__).resolve().parents[1] / "runtime-manifest.json"
        try:
            manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        except OSError:
            manifest_digest = hashlib.sha256(
                json.dumps([self.inventory_cache.asset_manifest_digest(asset) for asset in asset_list], sort_keys=True).encode("utf-8")
            ).hexdigest()
        self.inventory_cache.set_context(manifest_digest)
        rows: list[dict[str, Any]] = []
        for asset in asset_list:
            destination = self._destination(asset)
            state = self.state.get(asset.asset_id, {})
            cached_entry = self.inventory_cache.lookup(asset, destination) if verify else None
            if cached_entry is not None:
                installed = True
                digest = str(cached_entry["verified_hash"])
                verification = "cached-hash"
            elif verify:
                installed, digest = self._asset_ready(asset, destination)
                verification = "fresh-hash"
                if installed and digest:
                    self.inventory_cache.record(asset, destination, digest)
            else:
                persisted_status = str(state.get("status", "")).lower()
                installed = destination.is_file() and persisted_status in {"installed", "reused", "ready"}
                digest = asset.sha256 if installed and asset.sha256 else None
                verification = "persisted-state" if installed else "not-verified"
            status = "ready" if installed else state.get("status", "not-installed")
            if destination.is_file() and not installed and digest:
                status = "needs-repair"
            rows.append({
                **asset.to_json(),
                "installed": installed,
                "cached": installed or status in {"ready", "reused", "installed"},
                "installed_sha256": digest,
                "verification": verification,
                "status": status,
                "state": status.upper().replace("-", "_"),
                "managed_path": str(destination),
                "consent_granted": self.has_consent(asset.consent_group, [asset], verified_asset_ids={asset.asset_id} if installed else set()),
            })
        if verify:
            self.inventory_cache.save()
        return rows

    def estimate(self, assets: Iterable[ManagedAsset], *, verify: bool = True) -> dict[str, Any]:
        rows = self.inventory_cached(assets, verify=verify)
        required = sum(int(row["size_bytes"]) for row in rows if row["required"] and not row["installed"])
        optional = sum(int(row["size_bytes"]) for row in rows if not row["required"] and not row["installed"])
        installed = sum(
            int(row.get("installed_size_bytes") or row.get("size_bytes") or 0)
            for row in rows
            if row["installed"]
        )
        try:
            usage = shutil.disk_usage(self.root)
            available = usage.free
        except OSError:
            available = None
        return {
            "required_bytes": required,
            "optional_bytes": optional,
            "download_bytes": required + optional,
            "installed_bytes": installed,
            "available_bytes": available,
            "assets": rows,
            "location": str(self.root),
        }

    def check_disk_space(self, assets: Iterable[ManagedAsset], *, extra_bytes: int = 0) -> None:
        estimate = self.estimate(assets)
        available = estimate["available_bytes"]
        needed = int(estimate["download_bytes"]) + int(estimate["installed_bytes"]) + max(0, extra_bytes)
        if available is not None and available < needed:
            raise runtime.RuntimeDiskSpaceError(
                f"ClipGauge needs {needed} bytes of staging space but only {available} bytes are available"
            )

    def grant_consent(self, group_id: str, assets: Iterable[ManagedAsset], *, budget_bytes: int | None = None) -> dict[str, Any]:
        asset_list = list(assets)
        ids = sorted(asset.asset_id for asset in asset_list)
        total = sum(asset.size_bytes for asset in asset_list if not self._asset_ready(asset, self._destination(asset))[0])
        if budget_bytes is not None and total > budget_bytes:
            raise ConsentRequiredError("the requested asset group exceeds the approved download budget")
        record = {
            "asset_ids": ids,
            "download_bytes": total,
            "budget_bytes": budget_bytes if budget_bytes is not None else total,
            "location": str(self.root),
            "granted_at": time.time(),
        }
        self.consents[group_id] = record
        self._save_consents()
        return record

    def revoke_consent(self, group_id: str) -> None:
        self.consents.pop(group_id, None)
        self._save_consents()

    def has_consent(
        self,
        group_id: str,
        assets: Iterable[ManagedAsset],
        *,
        verified_asset_ids: set[str] | None = None,
    ) -> bool:
        record = self.consents.get(group_id)
        if not isinstance(record, dict):
            return False
        requested = list(assets)
        expected = {asset.asset_id for asset in requested}
        granted = {str(item) for item in record.get("asset_ids", [])}
        if not expected.issubset(granted):
            return False
        requested_bytes = sum(
            asset.size_bytes
            for asset in requested
            if asset.asset_id not in (verified_asset_ids or set()) and not self._asset_ready(asset, self._destination(asset))[0]
        )
        return requested_bytes <= int(record.get("budget_bytes", -1))

    def migrate_legacy_asset(self, asset: ManagedAsset, candidates: Iterable[Path]) -> str:
        destination = self._destination(asset)
        if self._asset_ready(asset, destination)[0]:
            return "ready"
        for candidate in candidates:
            candidate = candidate.expanduser().resolve()
            if not candidate.is_file():
                continue
            try:
                if asset.size_bytes > 0 and candidate.stat().st_size != asset.size_bytes:
                    continue
                if runtime.sha256_file(candidate).lower() != asset.sha256.lower():
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                staged: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=destination.parent,
                        prefix=f".{destination.name}.",
                        suffix=".migration",
                        delete=False,
                    ) as handle:
                        staged = Path(handle.name)
                    shutil.copy2(candidate, staged)
                    if runtime.sha256_file(staged).lower() != asset.sha256.lower():
                        continue
                    os.replace(staged, destination)
                    staged = None
                finally:
                    if staged is not None:
                        staged.unlink(missing_ok=True)
                self.state[asset.asset_id] = {
                    "status": "reused",
                    "destination": str(destination),
                    "source": str(candidate),
                    "updated_at": time.time(),
                }
                self._save()
                return "reused"
            except OSError:
                continue
        return "not-found"

    def mark_needs_repair(self, asset_id: str, message: str = "Integrity or capability validation failed") -> None:
        self.state[asset_id] = {"status": "needs-repair", "error": message, "updated_at": time.time()}
        self._save()

    def download(
        self,
        asset: ManagedAsset,
        *,
        require_consent: bool = False,
        cancel: CancelFn | None = None,
    ) -> Path:
        destination = self._destination(asset)
        download_destination = self._download_destination(asset)
        ready, _ = self._asset_ready(asset, destination)
        if ready:
            self.state[asset.asset_id] = {
                "status": "reused",
                "destination": str(destination),
                "updated_at": time.time(),
            }
            self._save()
            self._emit({
                "asset_id": asset.asset_id,
                "display_name": asset.display_name,
                "operation": "Reusing verified asset",
                "bytes_done": asset.size_bytes,
                "bytes_total": asset.size_bytes,
                "bytes_per_second": 0.0,
                "fraction": 1.0,
                "eta_seconds": 0.0,
                "elapsed_seconds": 0.0,
                "one_time_download": asset.one_time,
                "cached": True,
                "state": "REUSED",
                "status": "reused",
                "message": "Verified asset reused.",
            })
            return destination
        if require_consent and not self.has_consent(asset.consent_group, [asset]):
            raise ConsentRequiredError(f"Consent is required before downloading asset group {asset.consent_group}")
        self.check_disk_space([asset])
        self.clear_cancel(asset.asset_id)
        started = time.monotonic()
        self.state[asset.asset_id] = {
            "status": "downloading",
            "destination": str(destination),
            "download_destination": str(download_destination),
            "updated_at": time.time(),
        }
        self._save()

        def progress(fraction: float, message: str) -> None:
            part = download_destination.with_name(f".{download_destination.name}.part")
            done = part.stat().st_size if part.exists() else 0
            elapsed = max(0.0, time.monotonic() - started)
            speed = done / elapsed if elapsed > 0 else 0.0
            remaining = max(0, asset.size_bytes - done)
            eta = remaining / speed if speed > 0 else None
            self._emit({
                "asset_id": asset.asset_id,
                "display_name": asset.display_name,
                "operation": message,
                "bytes_done": done,
                "bytes_total": asset.size_bytes,
                "bytes_per_second": speed,
                "fraction": fraction,
                "eta_seconds": eta,
                "elapsed_seconds": elapsed,
                "one_time_download": asset.one_time,
                "cached": False,
                "state": "DOWNLOADING",
                "status": "downloading",
                "message": message,
            })

        try:
            result = runtime.download_verified(
                asset.url,
                download_destination,
                expected_sha256=asset.sha256,
                expected_size=asset.size_bytes if asset.size_bytes > 0 else None,
                max_bytes=(asset.size_bytes + 1024 * 1024) if asset.size_bytes > 0 else 128 * 1024 * 1024,
                timeout=config.HTTP_TIMEOUT,
                progress=progress,
                cancelled=lambda: self._is_cancelled(asset.asset_id, cancel),
            )
        except runtime.RuntimeDownloadCancelled:
            self.state[asset.asset_id] = {
                "status": "cancelled",
                "destination": str(destination),
                "updated_at": time.time(),
            }
            self._save()
            self._emit({"asset_id": asset.asset_id, "state": "CANCELLED", "status": "cancelled", "message": "Download cancelled."})
            raise
        except Exception as exc:  # noqa: BLE001 - state must survive every failure
            self.state[asset.asset_id] = {
                "status": "retryable-failed",
                "destination": str(destination),
                "error": str(exc),
                "updated_at": time.time(),
            }
            self._save()
            self._emit({"asset_id": asset.asset_id, "state": "FAILED", "status": "retryable-failed", "message": str(exc)})
            raise
        self.state[asset.asset_id] = {
            "status": "installed",
            "state": "READY",
            "destination": str(destination),
            "download_destination": str(result),
            "sha256": asset.sha256,
            "updated_at": time.time(),
        }
        self._save()
        self._emit({
            "asset_id": asset.asset_id,
            "display_name": asset.display_name,
            "operation": "Installed and verified",
            "bytes_done": asset.size_bytes,
            "bytes_total": asset.size_bytes,
            "bytes_per_second": asset.size_bytes / max(0.001, time.monotonic() - started),
            "fraction": 1.0,
            "eta_seconds": 0.0,
            "elapsed_seconds": time.monotonic() - started,
            "one_time_download": asset.one_time,
            "cached": False,
            "state": "READY",
            "status": "installed",
            "message": "Installed and verified.",
        })
        return result

    def download_group(self, assets: Iterable[ManagedAsset], *, group_id: str, cancel: CancelFn | None = None) -> list[Path]:
        asset_list = list(assets)
        if not asset_list:
            return []
        if not self.has_consent(group_id, asset_list):
            raise ConsentRequiredError(f"Consent is required before downloading asset group {group_id}")
        self.check_disk_space(asset_list)
        return [self.download(asset, require_consent=True, cancel=cancel) for asset in asset_list]
