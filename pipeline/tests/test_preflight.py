import json

from clipgauge_pipeline import preflight


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
