import http.client
import json
import os
import threading
import time
import urllib.parse

import httpx
import pytest

from publikclip_pipeline.edits import visuals
from publikclip_pipeline.insights import instagram
from publikclip_pipeline.scoring import llm


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("GET", "https://example.invalid"), response=httpx.Response(self.status_code))


def test_gemini_uses_header_and_never_query_string(monkeypatch, tmp_path):
    secret = "AIzaTestSecretValue123456"
    monkeypatch.setenv("PUBLIKCLIP_GEMINI_API_KEY", secret)
    monkeypatch.setattr(llm, "_cache_dir", lambda: tmp_path)
    seen = {}

    def fake_post(url, **kwargs):
        seen.update(url=url, kwargs=kwargs)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    result = llm.GeminiClient().generate_json("hello", {"type": "object"})
    assert result == {"ok": True}
    assert secret not in seen["url"]
    assert "params" not in seen["kwargs"]
    assert seen["kwargs"]["headers"] == {"x-goog-api-key": secret}


def test_gemini_error_details_are_redacted(monkeypatch, tmp_path):
    secret = "AIzaSecretInProviderBody123456"
    monkeypatch.setenv("PUBLIKCLIP_GEMINI_API_KEY", secret)
    monkeypatch.setattr(llm, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    response = FakeResponse({"error": {"message": f"quota detail includes {secret}"}}, status_code=429)
    monkeypatch.setattr(llm.httpx, "post", lambda *args, **kwargs: response)
    with pytest.raises(llm.LlmError) as error:
        llm.GeminiClient().generate_json("hello", {"type": "object"})
    assert secret not in str(error.value)


def test_gemini_key_does_not_fall_back_to_plaintext_file(monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLIKCLIP_GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm.config, "home_dir", lambda: tmp_path)
    (tmp_path / "secrets.json").write_text(json.dumps({"gemini_api_key": "file-secret"}))
    assert llm.gemini_api_key() is None


def test_visual_pexels_key_is_environment_scoped(monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLIKCLIP_PEXELS_API_KEY", raising=False)
    monkeypatch.setattr(visuals.config, "home_dir", lambda: tmp_path)
    (tmp_path / "secrets.json").write_text(json.dumps({"pexels_api_key": "file-secret"}))
    assert visuals.pexels_key() is None
    monkeypatch.setenv("PUBLIKCLIP_PEXELS_API_KEY", "env-secret")
    assert visuals.pexels_key() == "env-secret"


def test_instagram_callback_binds_ephemeral_loopback_port_and_accepts_one_callback():
    state = "csrf-state"
    observed = {}

    def callback(port):
        observed["port"] = port

        def send():
            time.sleep(0.05)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            query = urllib.parse.urlencode({"state": state, "code": "oauth-code"})
            connection.request("GET", f"/callback?{query}")
            connection.getresponse().read()
            connection.close()

        threading.Thread(target=send, daemon=True).start()

    result = instagram._wait_for_callback(state, timeout_sec=2, on_ready=callback)
    assert observed["port"] > 0
    assert result.port == observed["port"]
    assert result.code == "oauth-code"
    assert result.error is None


def test_instagram_save_connection_requires_rust_bridge(monkeypatch):
    monkeypatch.delenv("PUBLIKCLIP_CONNECTION_OUTPUT", raising=False)
    with pytest.raises(instagram.IgError, match="desktop vault bridge"):
        instagram.save_connection({"access_token": "secret"})
