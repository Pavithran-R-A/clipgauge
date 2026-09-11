import http.client
import hashlib
import json
import os
import threading
import time
import urllib.parse

import httpx
import pytest

from clipgauge_pipeline.edits import visuals
from clipgauge_pipeline.insights import instagram
from clipgauge_pipeline.scoring import llm


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
    monkeypatch.setenv("CLIPGAUGE_GEMINI_API_KEY", secret)
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
    monkeypatch.setenv("CLIPGAUGE_GEMINI_API_KEY", secret)
    monkeypatch.setattr(llm, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    response = FakeResponse({"error": {"message": f"quota detail includes {secret}"}}, status_code=429)
    monkeypatch.setattr(llm.httpx, "post", lambda *args, **kwargs: response)
    with pytest.raises(llm.LlmError) as error:
        llm.GeminiClient().generate_json("hello", {"type": "object"})
    assert secret not in str(error.value)


def test_gemini_key_does_not_fall_back_to_plaintext_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIPGAUGE_GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm.config, "home_dir", lambda: tmp_path)
    (tmp_path / "secrets.json").write_text(json.dumps({"gemini_api_key": "file-secret"}))
    assert llm.gemini_api_key() is None


def test_visual_pexels_key_is_environment_scoped(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIPGAUGE_PEXELS_API_KEY", raising=False)
    monkeypatch.setattr(visuals.config, "home_dir", lambda: tmp_path)
    (tmp_path / "secrets.json").write_text(json.dumps({"pexels_api_key": "file-secret"}))
    assert visuals.pexels_key() is None
    monkeypatch.setenv("CLIPGAUGE_PEXELS_API_KEY", "env-secret")
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
    monkeypatch.delenv("CLIPGAUGE_CONNECTION_OUTPUT", raising=False)
    with pytest.raises(instagram.IgError, match="desktop vault bridge"):
        instagram.save_connection({"access_token": "secret"})


@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "{}",
        '{"user_id":"42"}',
        '{"access_token":"token"}',
        '{"user_id":"","access_token":"token"}',
        '{"user_id":"42","access_token":""}',
    ],
)
def test_instagram_load_connection_rejects_incomplete_vault_payload(monkeypatch, payload):
    monkeypatch.setenv("CLIPGAUGE_INSTAGRAM_CONNECTION_JSON", payload)

    assert instagram.load_connection() is None


def test_instagram_api_errors_redact_access_tokens(monkeypatch):
    token = "instagram-secret-token"
    monkeypatch.setattr(
        instagram.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({"access_token": token}, status_code=500),
    )

    with pytest.raises(instagram.IgError) as error:
        instagram.media_node({"user_id": "42", "access_token": token}, "M1")

    assert token not in str(error.value)


def test_instagram_save_connection_preserves_existing_file_on_replace_failure(monkeypatch, tmp_path):
    output = tmp_path / "connection.json"
    output.write_text('{"access_token":"old"}', encoding="utf-8")
    monkeypatch.setenv("CLIPGAUGE_CONNECTION_OUTPUT", str(output))
    monkeypatch.setattr(instagram.config, "ensure_home", lambda: None)

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(instagram.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        instagram.save_connection({"access_token": "new"})

    assert output.read_text(encoding="utf-8") == '{"access_token":"old"}'
    assert list(tmp_path.glob(".connection.json.*.tmp")) == []


def test_overlay_cache_preserves_existing_file_on_replace_failure(monkeypatch, tmp_path):
    overlay_dir = tmp_path / "overlays"
    overlay_dir.mkdir()
    destination = overlay_dir / f"px_{hashlib.sha256(b'city').hexdigest()[:12]}.jpg"
    monkeypatch.setattr(visuals, "_overlay_dir", lambda _job_dir: overlay_dir)
    monkeypatch.setenv("CLIPGAUGE_PEXELS_API_KEY", "pexels-test-key")
    api_response = FakeResponse({"photos": [{"src": {"large": "https://img.example/city.jpg"}}]})
    image_response = FakeResponse({})
    image_response.content = b"new-image"
    monkeypatch.setattr(visuals.httpx, "get", lambda url, **_kwargs: api_response if "api.pexels" in url else image_response)

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(visuals.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        visuals.fetch_pexels("city", tmp_path)

    assert not destination.exists()
    assert list(overlay_dir.glob(".px_*.tmp")) == []


def test_overlay_fetchers_treat_invalid_provider_json_as_unavailable(monkeypatch, tmp_path):
    overlay_dir = tmp_path / "overlays"
    overlay_dir.mkdir()
    monkeypatch.setattr(visuals, "_overlay_dir", lambda _job_dir: overlay_dir)
    monkeypatch.setenv("CLIPGAUGE_PEXELS_API_KEY", "pexels-test-key")
    invalid = httpx.Response(200, request=httpx.Request("GET", "https://example.invalid"), content=b"not-json")
    monkeypatch.setattr(visuals.httpx, "get", lambda *_args, **_kwargs: invalid)

    assert visuals.fetch_pexels("city", tmp_path) is None

    monkeypatch.delenv("CLIPGAUGE_PEXELS_API_KEY")
    monkeypatch.setattr(visuals.providers_mod, "secret_from_environment", lambda _profile: "gemini-test-key")
    monkeypatch.setattr(visuals.httpx, "post", lambda *_args, **_kwargs: invalid)

    assert visuals.fetch_gemini("city", tmp_path) is None


def test_instagram_thumbnail_cache_never_follows_redirects(monkeypatch, tmp_path):
    thumbnails = tmp_path / "ig_thumbs"
    thumbnails.mkdir()
    monkeypatch.setattr(instagram, "thumbs_dir", lambda: thumbnails)
    responses = [FakeResponse({}, status_code=302), FakeResponse({})]
    responses[1].content = b"thumbnail"
    seen = []

    def fake_get(url, **kwargs):
        seen.append((url, kwargs["follow_redirects"]))
        return responses.pop(0)

    monkeypatch.setattr(instagram.httpx, "get", fake_get)
    monkeypatch.setattr(instagram, "media_node", lambda *_args: {"thumbnail_url": "https://cdn.example/fresh.jpg"})

    result = instagram.cache_thumbnail({}, {"id": "M1", "thumbnail_url": "https://img.example/stale.jpg"})

    assert result == str(thumbnails / "M1.jpg")
    assert [follow for _, follow in seen] == [False, False]


def test_instagram_thumbnail_cache_writes_atomically(monkeypatch, tmp_path):
    thumbnails = tmp_path / "ig_thumbs"
    thumbnails.mkdir()
    monkeypatch.setattr(instagram, "thumbs_dir", lambda: thumbnails)
    response = FakeResponse({})
    response.content = b"thumbnail"
    monkeypatch.setattr(instagram.httpx, "get", lambda *_args, **_kwargs: response)

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(instagram.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        instagram.cache_thumbnail({}, {"id": "M1", "thumbnail_url": "https://img.example/m1.jpg"})

    assert not (thumbnails / "M1.jpg").exists()
    assert list(thumbnails.glob(".M1.jpg.*.tmp")) == []
