from __future__ import annotations

import json
import time

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
        profile(base_url="http://remote.example/v1", locality="local")
    with pytest.raises(ValueError):
        profile(base_url="https://user:password@provider.example/v1")


def test_cache_identity_is_profile_and_image_specific():
    request = providers.InferenceRequest(prompt="p", schema={"type": "object"}, images=[b"one"])
    assert providers.cache_key(profile(id="alpha"), request) != providers.cache_key(profile(id="beta"), request)
    changed = providers.InferenceRequest(prompt="p", schema={"type": "object"}, images=[b"two"])
    assert providers.cache_key(profile(id="alpha"), request) != providers.cache_key(profile(id="alpha"), changed)


def test_cache_identity_includes_resolved_model_and_contract_versions():
    request = providers.InferenceRequest(prompt="p", schema={"type": "object"})
    auto = profile(id="auto", model="auto")
    assert providers.cache_key(auto, request, actual_model="model-a") != providers.cache_key(auto, request, actual_model="model-b")
    assert providers.cache_key(auto, request, actual_model="model-a", rubric_version="r1") != providers.cache_key(auto, request, actual_model="model-a", rubric_version="r2")


def test_local_scoring_generation_uses_stable_seed():
    adapter = providers.ProviderAdapter(profile(kind="clipgauge-local"))
    captured: dict[str, providers.InferenceRequest] = {}

    def fake_infer(request, *, use_cache=True):
        captured["request"] = request
        return providers.InferenceResult(
            data={"ok": True},
            provider_profile_id=adapter.profile.id,
            provider_kind=adapter.profile.kind,
            model=adapter.model,
            capabilities_used={},
            degraded_signals=[],
            structured_level="native_schema",
            latency_ms=0,
        )

    adapter.infer = fake_infer
    adapter.generate_json("return ok", {"type": "object"}, purpose="scoring")

    assert captured["request"].seed == 0


def test_local_scoring_generation_is_greedy():
    adapter = providers.ProviderAdapter(profile(kind="clipgauge-local"))
    captured: dict[str, providers.InferenceRequest] = {}

    def fake_infer(request, *, use_cache=True):
        captured["request"] = request
        return providers.InferenceResult(
            data={"ok": True},
            provider_profile_id=adapter.profile.id,
            provider_kind=adapter.profile.kind,
            model=adapter.model,
            capabilities_used={},
            degraded_signals=[],
            structured_level="native_schema",
            latency_ms=0,
        )

    adapter.infer = fake_infer
    adapter.generate_json("return ok", {"type": "object"}, purpose="scoring")

    assert captured["request"].temperature == 0.0


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


def test_local_scoring_sends_stable_seed(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="clipgauge-local"),
        "secret-value",
    )
    adapter.generate_json(
        "return ok",
        {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        purpose="scoring",
    )

    assert seen["json"]["seed"] == 0


def test_groq_qwen_scoring_caps_output_budget_for_provider_limits(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="groq", model="qwen/qwen3.8-27b"),
        "secret-value",
    )

    adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert seen["json"]["max_tokens"] == providers.GROQ_QWEN_SCORING_MAX_OUTPUT_TOKENS


def test_openrouter_scoring_caps_output_budget_for_free_model_latency(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="openrouter", model="nex-agi/nex-n2.5-mini:free"),
        "secret-value",
    )

    adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert seen["json"]["max_tokens"] == providers.OPENROUTER_SCORING_MAX_OUTPUT_TOKENS


def test_openrouter_selected_model_refreshes_capabilities_before_scoring(monkeypatch):
    seen: dict[str, object] = {}

    def fake_get(url, *, headers, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={
                "data": [{
                    "id": "nex-agi/nex-n2.5-mini:free",
                    "architecture": {"input_modalities": ["text"]},
                    "supported_parameters": ["reasoning_effort", "response_format", "structured_outputs"],
                    "reasoning": {"mandatory": False, "supported_efforts": ["high", "medium", "none"]},
                }],
            },
        )

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="openrouter", model="nex-agi/nex-n2.5-mini:free", capabilities=providers.CapabilitySet()),
        "secret-value",
    )

    adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert seen["json"]["response_format"]["type"] == "json_schema"
    assert seen["json"]["max_tokens"] == providers.OPENROUTER_SCORING_MAX_OUTPUT_TOKENS
    assert seen["json"]["reasoning_effort"] == "none"
    assert adapter.profile.capabilities.structured_json is True


def test_openrouter_auto_free_unknown_capabilities_use_safe_json_mode(monkeypatch):
    seen: dict[str, object] = {}

    def fake_get(*_args, **_kwargs):
        raise AssertionError("Auto Free must not require a fixed model lookup")

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={
                "model": "provider/free-model-a",
                "choices": [{"message": {"content": '{"ok": true}'}}],
            },
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="openrouter", model="openrouter/free", capabilities=providers.CapabilitySet()),
        "secret-value",
    )

    result = adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert result.structured_level == "native_schema"
    assert seen["json"]["response_format"]["type"] == "json_schema"
    assert seen["json"]["reasoning"] == {"effort": "none"}
    assert result.model == "provider/free-model-a"


def test_scoring_deadline_caps_provider_request_timeout(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["timeout"] = timeout
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 5.0)

    adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert 0.0 < float(seen["timeout"]) <= 5.0


def test_scoring_request_timeout_has_a_bounded_phase_cap(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["timeout"] = timeout
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 90.0)

    adapter.infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            purpose="scoring",
        )
    )

    assert float(seen["timeout"]) <= providers.SCORING_REQUEST_TIMEOUT_CAP_SECONDS


def test_scoring_request_stops_waiting_at_wall_deadline(monkeypatch):
    def slow_post(*args, **kwargs):
        time.sleep(0.25)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", slow_post)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 0.05)
    started = time.monotonic()

    with pytest.raises(providers.ProviderError) as error:
        adapter.infer(
            providers.InferenceRequest(
                prompt="return ok",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                purpose="scoring",
            )
        )

    assert error.value.code == "TIMEOUT"
    assert error.value.details["structured_output_status"] == "not_returned"
    assert time.monotonic() - started < 0.2


def test_scoring_request_respects_phase_timeout_when_provider_hangs(monkeypatch):
    def hanging_post(*args, **kwargs):
        time.sleep(0.25)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(providers.httpx, "post", hanging_post)
    monkeypatch.setattr(providers, "SCORING_REQUEST_TIMEOUT_CAP_SECONDS", 0.05)
    adapter = providers.OpenAICompatibleAdapter(profile(timeout_seconds=1.0), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 1.0)
    request = providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object"},
        purpose="scoring",
    )
    started = time.monotonic()

    with pytest.raises(httpx.TimeoutException):
        adapter._post_request("https://provider.example/v1/chat/completions", json_body={}, request=request)

    assert time.monotonic() - started < 0.2


def test_scoring_wall_timeout_does_not_retry_a_hanging_request(monkeypatch):
    calls = 0
    original_sleep = time.sleep

    def hanging_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        original_sleep(0.25)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", hanging_post)
    monkeypatch.setattr(providers, "SCORING_REQUEST_TIMEOUT_CAP_SECONDS", 0.05)
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: None)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 5.0)
    started = time.monotonic()

    with pytest.raises(providers.ProviderError) as error:
        adapter.infer(
            providers.InferenceRequest(
                prompt="return ok",
                schema={"type": "object"},
                purpose="scoring",
            )
        )

    assert error.value.code == "TIMEOUT"
    assert calls == 1
    assert time.monotonic() - started < 0.2


def test_scoring_deadline_does_not_spawn_while_previous_request_stops(monkeypatch):
    calls = 0
    original_sleep = time.sleep

    def hanging_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        original_sleep(0.25)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", hanging_post)
    monkeypatch.setattr(providers, "SCORING_REQUEST_TIMEOUT_CAP_SECONDS", 0.05)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    request = providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object"},
        purpose="scoring",
    )
    adapter.set_scoring_deadline(providers.time.monotonic() + 5.0)

    with pytest.raises(providers.ProviderError):
        adapter.infer(request)

    adapter.set_scoring_deadline(providers.time.monotonic() + 5.0)
    with pytest.raises(providers.ProviderError) as error:
        adapter.infer(request)

    assert error.value.code == "TIMEOUT"
    assert calls == 1


def test_expired_scoring_deadline_avoids_provider_request(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() - 1.0)

    with pytest.raises(providers.ProviderError) as exc_info:
        adapter.infer(
            providers.InferenceRequest(
                prompt="return ok",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                purpose="scoring",
            )
        )

    assert exc_info.value.code == "TIMEOUT"
    assert calls == 0


def test_scoring_retry_sleep_is_capped_by_deadline(monkeypatch):
    sleeps: list[float] = []

    monkeypatch.setattr(
        providers.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(503, json={"message": "busy"}),
    )
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: sleeps.append(seconds))
    adapter = providers.OpenAICompatibleAdapter(profile(), "secret-value")
    adapter.set_scoring_deadline(providers.time.monotonic() + 0.1)

    with pytest.raises(providers.ProviderError):
        adapter.infer(
            providers.InferenceRequest(
                prompt="return ok",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                purpose="scoring",
            )
        )

    assert sleeps
    assert sleeps[0] <= 0.1


def test_native_schema_adds_strict_object_bounds_without_mutating_schema(monkeypatch):
    seen: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        seen["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true, "nested": {"value": "x"}}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "nested": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        },
        "required": ["ok", "nested"],
    }

    providers.OpenAICompatibleAdapter(profile(), "secret-value").infer(
        providers.InferenceRequest(
            prompt="return ok",
            schema=schema,
        )
    )

    sent_schema = seen["json"]["response_format"]["json_schema"]["schema"]
    assert sent_schema["additionalProperties"] is False
    assert sent_schema["properties"]["nested"]["additionalProperties"] is False
    assert "additionalProperties" not in schema
    assert "additionalProperties" not in schema["properties"]["nested"]


def test_inference_cache_writes_are_atomic(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        ),
    )
    replaced: list[tuple[object, object]] = []
    original_replace = providers.os.replace

    def record_replace(source, destination):
        replaced.append((source, destination))
        return original_replace(source, destination)

    monkeypatch.setattr(providers.os, "replace", record_replace)
    selected = profile(id="atomic-cache")
    request = providers.InferenceRequest(prompt="return ok", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})

    providers.OpenAICompatibleAdapter(selected, "secret-value").infer(request)

    assert replaced
    assert all(str(source).endswith(".tmp") for source, _ in replaced)
    assert not list(providers._cache_dir().glob("*.tmp"))


def test_openrouter_records_actual_routed_model(monkeypatch):
    def fake_post(url, *, headers, json, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={"model": "provider/actual-free-model", "choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="openrouter", model="openrouter/free"),
        "secret-value",
    )
    result = adapter.infer(providers.InferenceRequest(prompt="return ok", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}))
    assert result.model == "provider/actual-free-model"
    assert adapter.actual_model == "provider/actual-free-model"


def test_openrouter_writes_routed_model_cache_identity(monkeypatch):
    def fake_post(url, *, headers, json, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={"model": "provider/actual-free-model", "choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    selected = profile(kind="openrouter", model="provider/specific-free-model")
    adapter = providers.OpenAICompatibleAdapter(selected, "secret-value")
    request = providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    adapter.infer(request)

    requested_path = providers._cache_dir() / f"{providers.cache_key(selected, request, actual_model='provider/specific-free-model')}.json"
    routed_path = providers._cache_dir() / f"{providers.cache_key(selected, request, actual_model='provider/actual-free-model')}.json"
    assert requested_path.exists()
    assert routed_path.exists()
    assert requested_path != routed_path

    cached = providers.OpenAICompatibleAdapter(selected, "secret-value").infer(request)
    assert cached.cache_hit is True
    assert cached.model == "provider/actual-free-model"


def test_openrouter_auto_free_does_not_reuse_cross_run_inference_cache(monkeypatch):
    routed_models = iter(["provider/free-model-a", "provider/free-model-b"])
    post_calls = 0

    def fake_post(url, *, headers, json, timeout, follow_redirects):
        nonlocal post_calls
        post_calls += 1
        return httpx.Response(
            200,
            json={
                "model": next(routed_models),
                "choices": [{"message": {"content": '{"ok": true}'}}],
            },
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    selected = profile(kind="openrouter", model="openrouter/free")
    request = providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    first = providers.OpenAICompatibleAdapter(selected, "secret-value").infer(request)
    second = providers.OpenAICompatibleAdapter(selected, "secret-value").infer(request)

    assert first.model == "provider/free-model-a"
    assert second.model == "provider/free-model-b"
    assert second.cache_hit is False
    assert post_calls == 2


def test_connection_test_bypasses_inference_cache(monkeypatch):
    post_calls = 0

    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json={"data": [{"id": "demo-model"}]}),
    )

    def fake_post(*args, **kwargs):
        nonlocal post_calls
        post_calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.OpenAICompatibleAdapter(profile(id="connection-cache"), "secret-value")

    assert adapter.test_connection()["state"] == "PASS"
    assert adapter.test_connection()["state"] == "PASS"
    assert post_calls == 2


def test_ollama_auto_records_selected_model(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"message": {"content": '{"ok": true}'}},
        ),
    )
    selected = profile(kind="ollama", model="auto")
    adapter = providers.OllamaAdapter(selected)
    adapter.model_listing = lambda: ["qwen3:8b", "llama3:8b"]

    result = adapter.infer(providers.InferenceRequest(
        prompt="return ok",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    ))

    assert result.model == "llama3:8b"
    assert adapter.actual_model == "llama3:8b"


def test_gemini_model_listing_filters_models_without_generation_support(monkeypatch):
    def fake_get(url, *, headers, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    adapter = providers.GeminiAdapter(providers.preset_profile("gemini"), "secret-value")
    assert adapter.model_listing() == ["gemini-2.5-flash"]


def test_gemini_transport_failures_use_retry_backoff(monkeypatch):
    calls = 0
    sleeps: list[float] = []

    def fail_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("temporary network failure")

    monkeypatch.setattr(providers.httpx, "post", fail_post)
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: sleeps.append(seconds))
    adapter = providers.GeminiAdapter(providers.preset_profile("gemini"), "secret-value")

    with pytest.raises(providers.ProviderError) as error:
        adapter.infer(
            providers.InferenceRequest(
                prompt="return ok",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            )
        )

    assert error.value.code == "NETWORK_FAILED"
    assert calls == 3
    assert sleeps == [1, 2]


def test_model_listings_reject_non_object_payloads(monkeypatch):
    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(200, json=[], request=httpx.Request("GET", "https://provider.example")),
    )

    adapters = [
        providers.OpenAICompatibleAdapter(profile(id="openai-listing"), "secret-value"),
        providers.GeminiAdapter(providers.preset_profile("gemini"), "secret-value"),
        providers.OllamaAdapter(profile(
            id="ollama-listing",
            kind="ollama",
            base_url="http://127.0.0.1:11434",
            auth_strategy="none",
            locality="local",
        )),
    ]

    assert [adapter.model_listing() for adapter in adapters] == [[], [], []]


def test_gemini_model_descriptors_preserve_context_metadata(monkeypatch):
    def fake_get(url, *, headers, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={
                "models": [{
                    "name": "models/gemini-2.5-flash",
                    "inputTokenLimit": 1_048_576,
                    "supportedGenerationMethods": ["generateContent"],
                }],
            },
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    adapter = providers.GeminiAdapter(providers.preset_profile("gemini"), "secret-value")

    descriptors = adapter.model_descriptors()

    assert descriptors[0]["id"] == "gemini-2.5-flash"
    assert descriptors[0]["capabilities"]["context_window"] == 1_048_576


def test_openai_compatible_model_descriptors_use_provider_metadata(monkeypatch):
    def fake_get(url, *, headers, timeout, follow_redirects):
        return httpx.Response(
            200,
            json={
                "data": [{
                    "id": "provider/text-model",
                    "context_length": 8192,
                    "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                    "supported_parameters": ["temperature"],
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                }],
            },
        )

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    adapter = providers.OpenAICompatibleAdapter(
        profile(kind="openrouter", model="openrouter/free"),
        "secret-value",
    )

    models = adapter.model_descriptors()

    assert models[0]["compatibility"] == "NO STRUCTURED OUTPUT"
    assert models[0]["capabilities"]["vision"] is False
    assert models[0]["capabilities"]["context_window"] == 8192
    assert models[0]["price"] == {"prompt": "0.000001", "completion": "0.000002"}


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


def test_clipgauge_local_managed_endpoint_requires_its_model(monkeypatch):
    calls = []
    started = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        if url.endswith("/health"):
            return httpx.Response(200)
        return httpx.Response(200, json={"data": [{"id": "unrelated-model"}]})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    adapter = providers.make_adapter("clipgauge-local")
    monkeypatch.setattr(
        adapter._runtime,
        "start",
        lambda model: started.append(model) or "http://127.0.0.1:19001/v1",
    )

    adapter._ensure_runtime()

    assert calls == [
        "http://127.0.0.1:8080/health",
        "http://127.0.0.1:8080/v1/models",
    ]
    assert started == [adapter.model]


def test_clipgauge_local_managed_endpoint_accepts_matching_model(monkeypatch):
    def fake_get(url, **_kwargs):
        if url.endswith("/health"):
            return httpx.Response(200)
        return httpx.Response(200, json={"data": [{"id": "clipgauge-local/qwen3-4b-q4_k_m"}]})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    adapter = providers.make_adapter("clipgauge-local")
    started = []
    monkeypatch.setattr(adapter._runtime, "start", lambda model: started.append(model))

    adapter._ensure_runtime()

    assert started == []


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


def test_provider_http_failure_has_safe_request_details(monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(500, json={"error": {"message": "private runtime detail"}})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    adapter = providers.make_adapter("clipgauge-local")
    request = providers.InferenceRequest(
        prompt="do not include this prompt",
        schema={"type": "object"},
    )

    with pytest.raises(providers.ProviderError) as exc_info:
        adapter._post_json("chat/completions", {"messages": []}, request=request)

    error = exc_info.value
    assert error.code == "PROVIDER_UNAVAILABLE"
    assert error.details["http_status"] == 500
    assert error.details["request_number"] == 1
    assert "private runtime detail" not in json.dumps(error.details)
    assert "do not include this prompt" not in json.dumps(error.details)


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
    monkeypatch.setattr(manager, "_platform_key", lambda: "windows-x86_64")
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


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (httpx.Response(401, json={"error": {"message": "bad key"}}), "AUTH_INVALID"),
        (httpx.Response(503, json={"error": {"message": "down"}}), "PROVIDER_UNAVAILABLE"),
        (httpx.Response(200, text="not-json"), "PROVIDER_RESPONSE_INVALID"),
    ],
)
def test_model_descriptors_report_typed_listing_failures(monkeypatch, response, expected_code):
    monkeypatch.setattr(providers.httpx, "get", lambda *args, **kwargs: response)
    adapter = providers.OpenAICompatibleAdapter(profile(id="listing"), "secret-value")

    with pytest.raises(providers.ProviderError) as error:
        adapter.model_descriptors()

    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("adapter_factory", "expected_code"),
    [
        (lambda: providers.GeminiAdapter(providers.preset_profile("gemini"), "secret-value"), "AUTH_INVALID"),
        (lambda: providers.OllamaAdapter(profile(
            id="ollama-listing-error",
            kind="ollama",
            base_url="http://127.0.0.1:11434",
            auth_strategy="none",
            locality="local",
        )), "PROVIDER_UNAVAILABLE"),
    ],
)
def test_legacy_provider_descriptors_report_typed_listing_failures(monkeypatch, adapter_factory, expected_code):
    status = 401 if expected_code == "AUTH_INVALID" else 503
    monkeypatch.setattr(providers.httpx, "get", lambda *args, **kwargs: httpx.Response(status, json={"error": {"message": "failure"}}))

    with pytest.raises(providers.ProviderError) as error:
        adapter_factory().model_descriptors()

    assert error.value.code == expected_code


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
