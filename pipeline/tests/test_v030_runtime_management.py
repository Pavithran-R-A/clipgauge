from pathlib import Path

import pytest

from clipgauge_pipeline import downloads, hardware


def _asset(destination: str = "bin/model.gguf") -> downloads.ManagedAsset:
    return downloads.ManagedAsset(
        asset_id="model:qwen3-4b",
        display_name="Qwen3 4B Balanced",
        purpose="Local clip scoring",
        destination=destination,
        url="https://models.example.test/model.gguf",
        size_bytes=1024,
        sha256="a" * 64,
        required=False,
        license="Apache-2.0",
        source="https://models.example.test/model.gguf",
    )


def test_hardware_selection_requires_verified_cuda():
    assert hardware.select_asr_accelerator({"cuda_ctranslate2": {"verified": False, "compute_types": ["float16"]}}) == ("cpu", "int8")
    assert hardware.select_asr_accelerator({"cuda_ctranslate2": {"verified": True, "compute_types": ["int8_float16"]}}) == ("cuda", "int8_float16")


def test_download_manager_estimate_and_inventory(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    estimate = manager.estimate([_asset()])
    assert estimate["required_bytes"] == 0
    assert estimate["optional_bytes"] == 1024
    assert estimate["assets"][0]["installed"] is False


def test_download_manager_rejects_escape(tmp_path):
    manager = downloads.DownloadManager(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        manager.inventory([_asset("../outside/model.gguf")])


def test_download_manager_persists_verified_install(monkeypatch, tmp_path):
    events = []
    manager = downloads.DownloadManager(tmp_path, event=events.append)
    asset = _asset()

    def fake_download(url, destination, **kwargs):
        assert url == asset.url
        assert destination == tmp_path / asset.destination
        kwargs["progress"](0.5, "Downloading verified runtime artifact…")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"verified")
        return destination

    monkeypatch.setattr(downloads.runtime, "download_verified", fake_download)
    result = manager.download(asset)
    assert result == tmp_path / asset.destination
    assert manager.state[asset.asset_id]["status"] == "installed"
    assert events[-1]["status"] == "installed"
    assert (tmp_path / "downloads.json").exists()


def test_download_manager_marks_retryable_failure(monkeypatch, tmp_path):
    events = []
    manager = downloads.DownloadManager(tmp_path, event=events.append)
    asset = _asset()

    def failing_download(*args, **kwargs):
        raise downloads.runtime.RuntimeIntegrityError("hash mismatch")

    monkeypatch.setattr(downloads.runtime, "download_verified", failing_download)
    with pytest.raises(downloads.runtime.RuntimeIntegrityError):
        manager.download(asset)
    assert manager.state[asset.asset_id]["status"] == "retryable-failed"
    assert events[-1]["status"] == "retryable-failed"
