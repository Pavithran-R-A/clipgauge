from __future__ import annotations

import json

import httpx
import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.scoring import providers


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
