from __future__ import annotations

import json

import httpx
import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.scoring import providers


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / ".clipgauge"))


def profile(kind: str = "custom", **overrides) -> providers.ProviderProfile:
    values = {
        "schema_version": 1,
        "id": f"profile-{kind}",
        "kind": kind,
        "display_name": kind.title(),
        "base_url": "https://provider.example/v1",
        "model": "demo-model",
        "auth_strategy": "bearer",
        "capabilities": providers.CapabilitySet(
            structured_json=True,
            json_schema=True,
            vision=True,
            model_listing=False,
            local=False,
            cloud=True,
        ),
    }
    values.update(overrides)
    return providers.ProviderProfile(**values)


def test_rejects_dangerous_provider_urls():
    with pytest.raises(ValueError):
        profile(base_url="file:///tmp/provider")
    with pytest.raises(ValueError):
        profile(base_url="http://remote.example/v1")
    with pytest.raises(ValueError):
        profile(base_url="https://user:password@provider.example/v1")


def test_cache_identity_is_profile_and_image_specific():
    request = providers.InferenceRequest(prompt="p", schema={"type": "object"}, images=[b"one"])
    assert providers.cache_key(profile(id="alpha"), request) != providers.cache_key(profile(id="beta"), request)
    changed = providers.InferenceRequest(prompt="p", schema={"type": "object"}, images=[b"two"])
    assert providers.cache_key(profile(id="alpha"), request) != providers.cache_key(profile(id="alpha"), changed)


def test_openai_compatible_native_schema_and_secret_never_enters_url(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen.update({"url": url, "headers": headers, "json": json})
        return httpx.Response(
            200,
            json={"id": "req-1", "choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    result = adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
    )
    assert result.data == {"ok": True}
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["headers"] == {"content-type": "application/json", "authorization": "Bearer secret-value"}
    assert "secret-value" not in str(seen["url"])
    body = seen["json"]
    assert body["response_format"]["type"] == "json_schema"


def test_text_only_provider_records_vision_degradation(monkeypatch):
    def fake_post(url, *, headers, json, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(
            id="text-only",
            capabilities=providers.CapabilitySet(
                structured_json=True,
                json_schema=False,
                vision=False,
                model_listing=False,
                local=False,
                cloud=True,
            ),
        ),
        "secret-value",
    )
    result = adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            images=[b"frame"],
        )
    )
    assert result.data == {"ok": True}
    assert result.degraded_signals == ["vision_unavailable"]
    assert result.capabilities_used["vision"] is False


def test_settings_migrates_legacy_modes_without_secrets():
    migrated = config.Settings.from_json({"llm_mode": "ollama", "caption_preset": "classic"})
    saved = migrated.to_json()
    assert migrated.provider_profile_id == "legacy-ollama"
    assert saved["provider_snapshot"]["kind"] == "ollama"
    assert "api_key" not in json.dumps(saved).lower()


def test_local_preset_defaults_to_loopback_without_auth():
    lm = providers.preset_profile("lmstudio")
    assert lm.endpoint_identity == "http://127.0.0.1:1234/v1"
    assert lm.auth_strategy == "none"
    assert lm.locality == "local"


def test_clipgauge_local_preset_is_managed_and_structured():
    local = providers.preset_profile("clipgauge-local")
    assert local.display_name == "ClipGauge Local"
    assert local.endpoint_identity == "http://127.0.0.1:8080/v1"
    assert local.auth_strategy == "none"
    assert local.locality == "local"
    assert local.capabilities.json_schema is True
    assert local.metadata["managed"] is True
    assert local.timeout_seconds == providers.LOCAL_PROVIDER_TIMEOUT_SECONDS == 300.0


def test_openrouter_qa_endpoint_is_opt_in_and_explicit_endpoint_wins(monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_QA_OPENROUTER_ENDPOINT", "http://127.0.0.1:8765/v1")
    qa_profile = providers.preset_profile("openrouter")
    assert qa_profile.endpoint_identity == "http://127.0.0.1:8765/v1"
    explicit_profile = providers.preset_profile("openrouter", endpoint="https://example.test/v1")
    assert explicit_profile.endpoint_identity == "https://example.test/v1"
    monkeypatch.delenv("CLIPGAUGE_QA_OPENROUTER_ENDPOINT")
    default_profile = providers.preset_profile("openrouter")
    assert default_profile.endpoint_identity == "https://openrouter.ai/api/v1"


def test_clipgauge_local_adapter_uses_existing_loopback_server(monkeypatch):
    seen = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen.update(url=url, json=json, follow_redirects=follow_redirects)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    profile_local = providers.preset_profile(
        "clipgauge-local",
        metadata={"managed": False},
    )
    adapter = providers.make_adapter(profile_local)
    result = adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
    )
    assert result.data == {"ok": True}
    assert seen["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert seen["follow_redirects"] is False


def test_clipgauge_local_timeout_is_single_attempt(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("local runtime stalled")

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.make_adapter("clipgauge-local")
    request = providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )
    with pytest.raises(providers.ProviderError) as exc_info:
        adapter._post_json("chat/completions", {"messages": []}, request=request)
    assert exc_info.value.code == "TIMEOUT"
    assert calls == 1


def test_local_qa_trace_is_opt_in_and_bounded(monkeypatch):
    trace_path = config.home_dir() / "diagnostics" / "local-runtime.jsonl"
    providers._local_qa_trace("disabled", payload="secret-free")
    assert not trace_path.exists()

    monkeypatch.setenv("CLIPGAUGE_QA_RUNTIME_TRACE", "1")
    for _ in range(400):
        providers._local_qa_trace("sample", payload="x" * 200)
    assert trace_path.stat().st_size <= providers.LOCAL_QA_TRACE_MAX_BYTES
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert records
    assert records[-1]["event"] == "sample"
    assert "secret-free" not in trace_path.read_text()


def test_clipgauge_local_runtime_command_is_loopback_only(monkeypatch, tmp_path):
    from clipgauge_pipeline import local_runtime

    manager = local_runtime.LocalRuntime(tmp_path)
    binary = tmp_path / "runtimes" / "llama-server" / "b10545" / "llama-server"
    model = tmp_path / "models" / "clipgauge-local" / "Qwen3-4B-Q4_K_M.gguf"
    binary.parent.mkdir(parents=True)
    model.parent.mkdir(parents=True)
    binary.write_text("binary")
    model.write_text("model")
    monkeypatch.setattr(manager, "binary_path", lambda: binary)
    monkeypatch.setattr(manager, "verified_model_path", lambda _model_id: model)
    command = manager.command("clipgauge-local/qwen3-4b-q4_k_m", 43210)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "43210"
    assert "--no-webui" in command


def test_custom_auth_strategy_and_header_are_non_secret_profile_metadata():
    custom = providers.preset_profile(
        "custom",
        model="chat-model",
        endpoint="https://custom.example/v1",
        auth_strategy="custom_secret_header",
        secret_header_name="x-vendor-key",
    )
    assert custom.auth_strategy == "custom_secret_header"
    assert custom.metadata["secret_header_name"] == "x-vendor-key"
    assert "credential-value" not in json.dumps(custom.to_dict()).lower()


def test_provider_snapshot_profile_reconstruction():
    rebuilt = providers.profile_from_snapshot(
        {
            "schema_version": 1,
            "id": "custom-one",
            "kind": "custom",
            "model": "model-one",
            "endpoint_identity": "https://custom.example/v1",
            "auth_strategy": "custom_secret_header",
            "metadata": {"secret_header_name": "x-provider-key"},
            "capabilities": {"structured_json": True, "json_schema": False, "vision": None},
        }
    )
    assert rebuilt.id == "custom-one"
    assert rebuilt.auth_strategy == "custom_secret_header"
    assert rebuilt.metadata["secret_header_name"] == "x-provider-key"


def test_openai_compatible_image_translation_and_text_only_degradation(monkeypatch):
    seen = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen.update(url=url, headers=headers, json=json, follow_redirects=follow_redirects)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(
            id="vision-model",
            capabilities=providers.CapabilitySet(
                structured_json=True,
                json_schema=True,
                vision=True,
                model_listing=False,
                local=False,
                cloud=True,
                max_images=1,
            ),
        ),
        "secret-value",
    )
    result = adapter.infer(providers.InferenceRequest(prompt="describe", schema={"type": "object"}, images=[b"frame"]))
    assert result.data == {"ok": True}
    assert seen["json"]["messages"][0]["content"][1]["type"] == "image_url"
    assert seen["follow_redirects"] is False


def test_provider_errors_normalize_auth_model_quota_and_retry_after(monkeypatch):
    responses = [
        httpx.Response(401, json={"error": {"message": "bad key"}}),
        httpx.Response(404, json={"error": {"message": "missing model"}}),
        httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "quota exceeded"}}),
    ]

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        return responses.pop(0)

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(id="errors"), "secret-value")
    for expected in ["AUTH_INVALID", "MODEL_NOT_FOUND", "QUOTA_EXHAUSTED"]:
        with pytest.raises(providers.ProviderError) as error:
            adapter.infer(providers.InferenceRequest(prompt="p", schema={"type": "object"}))
        assert error.value.code == expected
        if expected == "QUOTA_EXHAUSTED":
            assert error.value.retry_after == 7.0


def test_model_listing_is_manual_entry_safe_when_endpoint_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(503, json={"error": "down"}),
    )
    adapter = providers.OpenAICompatibleAdapter(profile(id="listing"), "secret-value")
    assert adapter.model_listing() == []
    assert providers.preset_profile("custom", model="typed", endpoint="https://custom.example/v1").model == "typed"


def test_redirects_are_never_followed_for_authenticated_requests(monkeypatch):
    seen = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["follow_redirects"] = follow_redirects
        return httpx.Response(302, headers={"location": "https://other.example/v1"})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(id="redirect"), "secret-value")
    with pytest.raises(providers.ProviderError) as error:
        adapter.infer(providers.InferenceRequest(prompt="p", schema={"type": "object"}))
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert seen["follow_redirects"] is False


def test_cache_key_never_contains_secret_material():
    request = providers.InferenceRequest(prompt="p", schema={"type": "object"})
    key = providers.cache_key(profile(id="cache"), request)
    assert "secret-value" not in key
    assert "api_key" not in key.lower()
