import json

from clipgauge_pipeline import preflight, storage_estimate


def test_source_storage_estimate_accounts_for_working_space_components():
    estimate = storage_estimate.for_source(2 * 1024**3, duration_seconds=600)

    assert estimate["source_copy_bytes"] == 2 * 1024**3
    assert estimate["temporary_audio_bytes"] == 600 * 32_000
    assert estimate["checkpoint_bytes"] == 256 * 1024**2
    assert estimate["render_bytes"] == 1 * 1024**3
    assert estimate["safety_margin_bytes"] > 0
    assert estimate["required_bytes"] == sum(
        estimate[key]
        for key in (
            "source_copy_bytes",
            "temporary_audio_bytes",
            "checkpoint_bytes",
            "render_bytes",
            "safety_margin_bytes",
        )
    )


def test_preflight_aggregates_blocked_state(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight.config, "home_dir", lambda: tmp_path)
    monkeypatch.setattr(preflight.config, "ensure_home", lambda: tmp_path)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 5 * 1024 * 1024 * 1024})())
    monkeypatch.setattr(preflight, "_writable_root", lambda checks: checks.append({"name": "managed-data", "state": "ready", "message": "ok"}))
    monkeypatch.setattr(preflight, "_runtime_manifest", lambda: {"manifest_version": 1, "runtimes": {}, "models": {}})
    monkeypatch.setattr(preflight, "_yt_dlp", lambda checks, manifest: checks.append({"name": "yt-dlp", "state": "blocked", "message": "bad hash"}))
    monkeypatch.setattr(preflight, "_models", lambda checks, manifest: None)
    monkeypatch.setattr(preflight, "_ffmpeg", lambda checks: checks.append({"name": "ffmpeg", "state": "ready", "message": "ok"}))
    monkeypatch.setattr(preflight, "_ollama", lambda checks, selected: None)
    monkeypatch.setenv("CLIPGAUGE_GEMINI_API_KEY", "test-key")
    result = preflight.run("gemini")
    assert result["state"] == "blocked"


def test_preflight_warning_is_not_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight.config, "home_dir", lambda: tmp_path)
    monkeypatch.setattr(preflight.config, "ensure_home", lambda: tmp_path)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 5 * 1024 * 1024 * 1024})())
    monkeypatch.setattr(preflight, "_writable_root", lambda checks: checks.append({"name": "managed-data", "state": "ready", "message": "ok"}))
    monkeypatch.setattr(preflight, "_runtime_manifest", lambda: {"manifest_version": 1, "runtimes": {}, "models": {}})
    monkeypatch.setattr(preflight, "_yt_dlp", lambda checks, manifest: checks.append({"name": "yt-dlp", "state": "warning", "message": "not installed"}))
    monkeypatch.setattr(preflight, "_models", lambda checks, manifest: None)
    monkeypatch.setattr(preflight, "_ffmpeg", lambda checks: checks.append({"name": "ffmpeg", "state": "ready", "message": "ok"}))
    monkeypatch.setattr(preflight, "_ollama", lambda checks, selected: None)
    monkeypatch.setenv("CLIPGAUGE_GEMINI_API_KEY", "test-key")
    result = preflight.run("gemini")
    assert result["state"] == "warning"


def test_preflight_blocks_source_storage_shortfall(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"0" * (2 * 1024 * 1024))
    monkeypatch.setattr(preflight.normalize, "probe", lambda _path: type("Probe", (), {"duration_sec": 600.0})())
    checks = []
    preflight._source_storage_check(checks, str(source), 400 * 1024 * 1024)
    assert checks[0]["name"] == "source-storage"
    assert checks[0]["state"] == "blocked"
    assert checks[0]["details"]["source_bytes"] == 2 * 1024 * 1024
    assert checks[0]["details"]["duration_seconds"] == 600.0
    assert checks[0]["details"]["temporary_audio_bytes"] == 600 * 32_000


def test_ollama_probe_is_loopback_and_reports_missing_models(monkeypatch):
    seen = {}

    class Response:
        content = b'{"models": []}'

        def raise_for_status(self):
            return None

        def json(self):
            return json.loads(self.content)

    def fake_get(url, **kwargs):
        seen["url"] = url
        return Response()

    monkeypatch.setattr(preflight.httpx, "get", fake_get)
    checks = []
    preflight._ollama(checks, "ollama")
    assert seen["url"] == "http://127.0.0.1:11434/api/tags"
    assert checks[0]["state"] == "blocked"
