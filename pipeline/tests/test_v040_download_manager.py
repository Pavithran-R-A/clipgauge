import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from clipgauge_pipeline import downloads, runtime


@pytest.fixture(autouse=True)
def sufficient_test_disk(monkeypatch):
    monkeypatch.setattr(
        downloads.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=8 * 1024**3, total=8 * 1024**3, used=0),
    )


def _asset(destination: str = "assets/model.bin", *, group: str = "core") -> downloads.ManagedAsset:
    return downloads.ManagedAsset(
        asset_id="model:test",
        display_name="Test model",
        purpose="Deterministic manager test",
        destination=destination,
        url="https://example.test/model.bin",
        size_bytes=8,
        sha256="9ac2197d9258257b7b2a5b8cf5f3c0f6d8d3cc4d4f6b7d5f6e8d6a5f9b1a3c7e",
        required=True,
        consent_group=group,
    )


def test_inventory_json_write_cleans_failed_temporary(monkeypatch, tmp_path):
    destination = tmp_path / "inventory-cache.json"
    destination.write_text("previous", encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(downloads.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        downloads._write_json_atomic(destination, {"state": "new"})

    assert destination.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".inventory-cache.json.*.part")) == []


def test_grouped_consent_is_exactly_asset_scoped(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    first = _asset()
    second = _asset("assets/other.bin")
    record = manager.grant_consent("core", [first, second])
    assert record["asset_ids"] == ["model:test", "model:test"]
    assert manager.has_consent("core", [first])
    assert manager.has_consent("core", [second])
    unrelated = _asset("assets/third.bin")
    unrelated = downloads.ManagedAsset(**{**unrelated.to_json(), "asset_id": "model:other"})
    assert not manager.has_consent("core", [unrelated])


def test_download_reuses_verified_asset_and_emits_cache(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    destination = tmp_path / asset.destination
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(destination)})
    events = []
    manager.event = events.append
    monkeypatch.setattr(downloads.runtime, "download_verified", lambda *args, **kwargs: pytest.fail("must reuse"))
    assert manager.download(asset) == destination
    assert events[-1]["cached"] is True
    assert events[-1]["state"] == "REUSED"


def test_download_requires_group_consent(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    with pytest.raises(downloads.ConsentRequiredError):
        manager.download(asset, require_consent=True)
    manager.grant_consent("core", [asset])
    def fake_download(url, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"verified")
        return destination

    monkeypatch.setattr(downloads.runtime, "download_verified", fake_download)
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(tmp_path / asset.destination) if (tmp_path / asset.destination).exists() else "9ac2197d9258257b7b2a5b8cf5f3c0f6d8d3cc4d4f6b7d5f6e8d6a5f9b1a3c7e"})
    # The fake is intentionally allowed to exercise state wiring; real hash enforcement is covered by runtime tests.
    assert manager.download(asset, require_consent=True).is_file()


def test_cancelled_download_preserves_no_verified_state(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    manager.grant_consent("core", [asset])

    def cancelled(*args, **kwargs):
        raise runtime.RuntimeDownloadCancelled("cancelled")

    monkeypatch.setattr(downloads.runtime, "download_verified", cancelled)
    with pytest.raises(runtime.RuntimeDownloadCancelled):
        manager.download(asset, require_consent=True)
    assert manager.state[asset.asset_id]["status"] == "cancelled"
    assert not (tmp_path / asset.destination).exists()


def test_migration_reuses_verified_legacy_asset(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    legacy = tmp_path / "legacy" / "model.bin"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"verified")
    asset = _asset()
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(legacy)})
    assert manager.migrate_legacy_asset(asset, [legacy]) == "reused"
    assert (tmp_path / asset.destination).read_bytes() == b"verified"
    assert manager.state[asset.asset_id]["status"] == "reused"


def test_corrupt_asset_is_needs_repair(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    destination = tmp_path / asset.destination
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"bad")
    row = manager.inventory([asset])[0]
    assert row["status"] == "needs-repair"
    assert row["state"] == "NEEDS_REPAIR"


def test_inventory_cache_reuses_hash_when_file_metadata_is_unchanged(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    destination = tmp_path / "assets/model.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = _asset()
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(destination)})
    original_hash = downloads.runtime.sha256_file
    calls = 0

    def counting_hash(path):
        nonlocal calls
        calls += 1
        return original_hash(path)

    monkeypatch.setattr(downloads.runtime, "sha256_file", counting_hash)
    assert manager.inventory_cached([asset])[0]["verification"] == "fresh-hash"
    assert manager.inventory_cached([asset])[0]["verification"] == "cached-hash"
    assert calls == 1
    cache = json.loads(manager.inventory_cache.path.read_text(encoding="utf-8"))
    assert cache["app_version"]
    assert cache["platform"]
    assert cache["runtime_manifest_digest"]
    assert cache["last_verified_at"]
    assert cache["entries"][manager.inventory_cache.key(asset)]["verified_at"]

    destination.write_bytes(b"changed!!")
    manager.inventory_cached([asset])
    assert calls == 2


def test_inventory_cache_rehashes_same_size_replacement_with_preserved_mtime(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    destination = tmp_path / "assets/model.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = _asset()
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(destination)})

    assert manager.inventory_cached([asset])[0]["verification"] == "fresh-hash"
    original_stat = destination.stat()
    replacement = destination.with_name("replacement.bin")
    replacement.write_bytes(b"tampered")
    os.replace(replacement, destination)
    os.utime(destination, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    row = manager.inventory_cached([asset])[0]
    assert row["verification"] == "fresh-hash"
    assert row["installed"] is False


def test_sidecar_inventory_cache_does_not_collide_with_native_inventory_cache(tmp_path):
    native_cache = tmp_path / "inventory-cache.json"
    native_cache.write_text(
        json.dumps({
            "schema_version": 1,
            "app_version": "0.5.16",
            "platform": "windows",
            "entries": {"native": {"files": []}},
        }),
        encoding="utf-8",
    )

    manager = downloads.DownloadManager(tmp_path)

    assert manager.inventory_cache.path == tmp_path / "pipeline-inventory-cache.json"
    assert manager.inventory_cache.payload["entries"] == {}
    assert native_cache.read_text(encoding="utf-8").find('"files"') >= 0


def test_inventory_cache_survives_different_callers_and_invalidates_only_changed_asset(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    first_path = tmp_path / "assets/first.bin"
    second_path = tmp_path / "assets/second.bin"
    first_path.parent.mkdir(parents=True)
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    first = downloads.ManagedAsset(**{**_asset("assets/first.bin").to_json(), "sha256": runtime.sha256_file(first_path), "size_bytes": 5})
    second = downloads.ManagedAsset(**{**_asset("assets/second.bin").to_json(), "sha256": runtime.sha256_file(second_path), "size_bytes": 6})

    assert manager.inventory_cached([first])[0]["verification"] == "fresh-hash"
    rows = manager.inventory_cached([second, first])
    assert rows[0]["verification"] == "fresh-hash"
    assert rows[1]["verification"] == "cached-hash"


def test_cached_inventory_consent_does_not_rehash_verified_asset(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    destination = tmp_path / "assets/model.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = downloads.ManagedAsset(**{**_asset().to_json(), "sha256": runtime.sha256_file(destination), "size_bytes": 8})
    manager.grant_consent("core", [asset])
    manager.inventory_cached([asset])
    monkeypatch.setattr(manager, "_asset_ready", lambda *args: pytest.fail("cached consent must not rehash"))
    assert manager.inventory_cached([asset])[0]["consent_granted"] is True


def test_inventory_cache_invalidates_when_app_version_changes(tmp_path):
    destination = tmp_path / "assets/model.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = _asset()
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(destination)})
    path = tmp_path / "inventory-cache.json"

    first = downloads.VersionedInventoryCache(path, app_version="0.5.16")
    first.set_context("manifest-a")
    first.record(asset, destination, asset.sha256)
    first.save()
    second = downloads.VersionedInventoryCache(path, app_version="0.5.17")
    second.set_context("manifest-a")

    assert second.lookup(asset, destination) is None


def test_inventory_cache_reuses_unaffected_asset_when_runtime_manifest_changes(tmp_path):
    destination = tmp_path / "assets/model.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"verified")
    asset = _asset()
    asset = downloads.ManagedAsset(**{**asset.to_json(), "sha256": runtime.sha256_file(destination)})
    path = tmp_path / "inventory-cache.json"

    cache = downloads.VersionedInventoryCache(path, app_version="0.5.16")
    cache.set_context("manifest-a")
    cache.record(asset, destination, asset.sha256)
    cache.save()
    changed = downloads.VersionedInventoryCache(path, app_version="0.5.16")
    changed.set_context("manifest-b")

    assert changed.payload["runtime_manifest_digest"] == "manifest-b"
    assert changed.lookup(asset, destination) is not None


def test_estimate_uses_metadata_aware_inventory(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    monkeypatch.setattr(manager, "inventory", lambda *args, **kwargs: pytest.fail("full inventory must not run"))
    monkeypatch.setattr(manager, "inventory_cached", lambda assets, **kwargs: [{
        "required": True,
        "installed": True,
        "size_bytes": 8,
        "installed_size_bytes": 8,
    }])

    estimate = manager.estimate([_asset()])

    assert estimate["installed_bytes"] == 8


def test_disk_space_check_blocks_before_download(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    monkeypatch.setattr(downloads.shutil, "disk_usage", lambda path: type("U", (), {"free": 1, "total": 1, "used": 0})())
    with pytest.raises(runtime.RuntimeDiskSpaceError):
        manager.check_disk_space([asset])
