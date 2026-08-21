"""Managed asset inventory and resumable download state.

The manager deliberately delegates bytes, Range resume, size limits, SHA-256,
and atomic replacement to :mod:`runtime`. It adds user-facing metadata and a
small persisted state file; it never executes downloaded files.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from . import config, runtime


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

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


EventFn = Callable[[dict[str, Any]], None]


class DownloadManager:
    def __init__(self, root: Path | None = None, event: EventFn | None = None) -> None:
        self.root = (root or config.home_dir()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "downloads.json"
        self.event = event
        self.state = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.state_path)

    def _destination(self, asset: ManagedAsset) -> Path:
        destination = (self.root / asset.destination).resolve()
        if destination != self.root and self.root not in destination.parents:
            raise ValueError("managed asset destination escapes the ClipGauge data root")
        return destination

    def inventory(self, assets: Iterable[ManagedAsset]) -> list[dict[str, Any]]:
        rows = []
        for asset in assets:
            destination = self._destination(asset)
            installed = False
            digest = None
            if destination.is_file():
                try:
                    digest = runtime.sha256_file(destination)
                    installed = digest.lower() == asset.sha256.lower()
                except OSError:
                    installed = False
            state = self.state.get(asset.asset_id, {})
            rows.append(
                {
                    **asset.to_json(),
                    "installed": installed,
                    "installed_sha256": digest,
                    "status": "installed" if installed else state.get("status", "not-installed"),
                    "managed_path": str(destination),
                }
            )
        return rows

    def estimate(self, assets: Iterable[ManagedAsset]) -> dict[str, Any]:
        rows = self.inventory(assets)
        required = sum(int(row["size_bytes"]) for row in rows if row["required"] and not row["installed"])
        optional = sum(int(row["size_bytes"]) for row in rows if not row["required"] and not row["installed"])
        try:
            available = shutil.disk_usage(self.root).free
        except OSError:
            available = None
        return {
            "required_bytes": required,
            "optional_bytes": optional,
            "available_bytes": available,
            "assets": rows,
        }

    def _emit(self, payload: dict[str, Any]) -> None:
        if self.event:
            self.event(payload)

    def download(self, asset: ManagedAsset) -> Path:
        destination = self._destination(asset)
        started = time.monotonic()
        self.state[asset.asset_id] = {
            "status": "downloading",
            "destination": str(destination),
            "updated_at": time.time(),
        }
        self._save()

        def progress(fraction: float, message: str) -> None:
            part = destination.with_name(f".{destination.name}.part")
            done = part.stat().st_size if part.exists() else 0
            elapsed = max(0.0, time.monotonic() - started)
            speed = done / elapsed if elapsed > 0 else 0.0
            eta = (asset.size_bytes - done) / speed if speed > 0 else None
            self._emit(
                {
                    "asset_id": asset.asset_id,
                    "display_name": asset.display_name,
                    "bytes_done": done,
                    "bytes_total": asset.size_bytes,
                    "fraction": fraction,
                    "bytes_per_second": speed,
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta,
                    "one_time_download": asset.one_time,
                    "status": "downloading",
                    "message": message,
                }
            )

        try:
            result = runtime.download_verified(
                asset.url,
                destination,
                expected_sha256=asset.sha256,
                max_bytes=max(asset.size_bytes, 1) + 1024 * 1024,
                timeout=config.HTTP_TIMEOUT,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001 - state must survive every failure
            self.state[asset.asset_id] = {
                "status": "retryable-failed",
                "destination": str(destination),
                "error": str(exc),
                "updated_at": time.time(),
            }
            self._save()
            self._emit({"asset_id": asset.asset_id, "status": "retryable-failed", "message": str(exc)})
            raise
        self.state[asset.asset_id] = {
            "status": "installed",
            "destination": str(result),
            "updated_at": time.time(),
        }
        self._save()
        self._emit(
            {
                "asset_id": asset.asset_id,
                "display_name": asset.display_name,
                "bytes_done": asset.size_bytes,
                "bytes_total": asset.size_bytes,
                "fraction": 1.0,
                "one_time_download": asset.one_time,
                "status": "installed",
                "message": "Installed and verified.",
            }
        )
        return result
