from pathlib import Path

from clipgauge_pipeline.render import ffmpeg_bin


def _clear_cache() -> None:
    ffmpeg_bin.readiness.cache_clear()
    ffmpeg_bin.resolve.cache_clear()


def test_capable_system_ffmpeg_is_ready_without_managed_download(monkeypatch, tmp_path):
    binary = tmp_path / "ffmpeg"
    binary.write_text("placeholder")
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: {"key": "win64-gpl", "size": 123})
    monkeypatch.setattr(ffmpeg_bin, "_candidates", lambda: [("system", str(binary))])
    monkeypatch.setattr(ffmpeg_bin, "_probe", lambda _path: ("ffmpeg version test", {"starts": True, "subtitles": True}, "ok"))
    _clear_cache()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is True
        assert result.source == "system"
        assert result.executable == str(binary)
        assert result.managed_download_needed is False
        assert result.capabilities == {"starts": True, "subtitles": True}
        assert ffmpeg_bin.resolve() == (str(binary), True)
    finally:
        _clear_cache()


def test_incompatible_system_ffmpeg_offers_managed_fallback(monkeypatch, tmp_path):
    binary = tmp_path / "ffmpeg"
    binary.write_text("placeholder")
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: {"key": "win64-gpl", "size": 456})
    monkeypatch.setattr(ffmpeg_bin, "_candidates", lambda: [("system", str(binary))])
    monkeypatch.setattr(ffmpeg_bin, "_probe", lambda _path: ("ffmpeg version old", {"starts": True, "subtitles": False}, "missing subtitles"))
    _clear_cache()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is False
        assert result.source == "system"
        assert result.managed_download_needed is True
        assert result.reason == "missing subtitles"
    finally:
        _clear_cache()
