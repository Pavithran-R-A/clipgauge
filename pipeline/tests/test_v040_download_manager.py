from pathlib import Path

import pytest

from clipgauge_pipeline import downloads, runtime


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


def test_disk_space_check_blocks_before_download(monkeypatch, tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    asset = _asset()
    monkeypatch.setattr(downloads.shutil, "disk_usage", lambda path: type("U", (), {"free": 1, "total": 1, "used": 0})())
    with pytest.raises(runtime.RuntimeDiskSpaceError):
        manager.check_disk_space([asset])
