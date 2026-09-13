from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from clipgauge_pipeline.jobs.queue import StageError
from clipgauge_pipeline.scoring import providers, rubric, stage


def test_local_t1_recovers_once_after_transient_provider_failure():
    class Client:
        profile = SimpleNamespace(kind="clipgauge-local")

        def __init__(self):
            self.calls = 0
            self.recoveries = 0

        def generate_json(self, _prompt, _schema):
            self.calls += 1
            if self.calls == 1:
                raise providers.ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "temporary server error",
                    details={"runtime_alive": True, "http_status": 500},
                )
            return {"summary": "safe fixture"}

        def recover_for_scoring(self):
            self.recoveries += 1

        def structured_level(self):
            return "json_mode"

    client = Client()

    result = stage._generate_t1(client, "private transcript", rubric.T1_SCHEMA, set())

    assert result == {"summary": "safe fixture"}
    assert client.calls == 2
    assert client.recoveries == 1


def test_private_scoring_rejects_cloud_provider_before_model_calls(tmp_path, monkeypatch):
    profile = providers.preset_profile("gemini")
    client = SimpleNamespace(model=profile.model, profile=profile)
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 1.0}},
            "diarize": {"segments": []},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": []},
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}, quality_mode="private"),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: client)

    with pytest.raises(StageError, match="private mode requires a local provider"):
        stage.ScoreStage().run(ctx)


def test_empty_candidate_set_is_typed_as_successful_no_recommendations(tmp_path, monkeypatch):
    profile = providers.preset_profile("clipgauge-local", metadata={"managed": False})

    class Client:
        def __init__(self):
            self.model = profile.model
            self.requested_model = profile.model
            self.actual_model = profile.model
            self.profile = profile

        def generate_json(self, *_args, **_kwargs):
            raise AssertionError("empty candidate sets must skip model scoring")

    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 1.0}},
            "diarize": {"segments": []},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": []},
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}, quality_mode="private"),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: Client())

    result = stage.ScoreStage().run(ctx)

    assert result["outcome"] == "SUCCESS_NO_RECOMMENDATIONS"
    assert result["code"] == "NO_RECOMMENDED_CLIPS"
    assert result["counts"] == {
        "candidate_count": 0,
        "eligible_candidate_count": 0,
        "scored_count": 0,
        "score_clip_count": 0,
        "camera_trajectory_count": 0,
        "render_attempt_count": 0,
        "render_output_count": 0,
        "rejection_reason_counts": {},
    }
    assert result["scoring_degraded"] is False


def test_scoring_provenance_records_effective_dynamic_provider_capabilities(tmp_path, monkeypatch):
    stale_profile = providers.preset_profile(
        "openrouter",
        model="example/free-model",
        metadata={"managed": False},
    )
    effective_profile = replace(
        stale_profile,
        capabilities=replace(
            stale_profile.capabilities,
            structured_json=True,
            json_schema=True,
        ),
    )

    class Settings:
        provider_profile_id = stale_profile.id
        provider_kind = stale_profile.kind
        provider_model = stale_profile.model
        provider_endpoint_identity = stale_profile.endpoint_identity
        provider_capabilities = stale_profile.capabilities.to_dict()
        provider_auth_strategy = stale_profile.auth_strategy
        provider_locality = stale_profile.locality
        provider_schema_version = stale_profile.schema_version
        quality_mode = "best"
        output_preference = "recommended"

        def __init__(self):
            self.provider_metadata = dict(stale_profile.metadata)

        def provider_snapshot(self):
            return {
                "schema_version": self.provider_schema_version,
                "id": self.provider_profile_id,
                "kind": self.provider_kind,
                "model": self.provider_model,
                "endpoint_identity": self.provider_endpoint_identity,
                "capabilities": dict(self.provider_capabilities),
                "auth_strategy": self.provider_auth_strategy,
                "locality": self.provider_locality,
                "metadata": dict(self.provider_metadata),
            }

        def to_json(self):
            return {
                "provider_snapshot": self.provider_snapshot(),
                "provider_capabilities": dict(self.provider_capabilities),
                "provider_metadata": dict(self.provider_metadata),
            }

    class Client:
        profile = effective_profile
        model = effective_profile.model
        requested_model = effective_profile.model
        actual_model = "example/free-model-resolved"
        last_result = None

        def structured_level(self):
            return "native_schema"

        def generate_json(self, _prompt, _schema, **_kwargs):
            return {
                "hook": 8,
                "hook_type": "bold_claim",
                "funniness": 6,
                "punchline_index": -1,
                "shock": 4,
                "curiosity_gap": 7,
                "value": 8,
                "self_contained": True,
                "bait_phrases": [],
                "summary": "A complete provider provenance fixture.",
                "hook_strength": 8,
                "hook_reason": "clear claim",
                "standalone_comprehension": 8,
                "setup_strength": 8,
                "escalation_strength": 7,
                "payoff_strength": 8,
                "payoff_location": "end",
                "ending_completeness": 8,
                "story_shape": "hook_setup_payoff",
                "information_density": 8,
                "reaction_strength": 6,
                "recommended_start_offset": 0.0,
                "recommended_end_offset": 0.0,
            }

    settings = Settings()
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(
        json.dumps({"arousal": [], "arousal_grid_sec": 0.5}),
        encoding="utf-8",
    )
    words = [
        {"word": f"word{i}", "start": i * 0.4, "end": i * 0.4 + 0.2}
        for i in range(25)
    ]
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 10.0}, "media_path": "fixture.mp4"},
            "diarize": {"segments": [{"start": 0.0, "end": 10.0, "speaker": 0, "words": words}]},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": [{"start": 0.0, "end": 10.0, "curve_score": 0.8, "channel_scores": {}}]},
        },
        settings=settings,
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: stale_profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: Client())

    result = stage.ScoreStage().run(ctx)

    settings_payload = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert result["capabilities"]["json_schema"] is True
    assert result["clips"][0]["ledger"]["provenance"]["capabilities"]["json_schema"] is True
    assert settings_payload["provider_capabilities"]["json_schema"] is True
    assert settings_payload["provider_metadata"]["actual_model"] == "example/free-model-resolved"


def test_cloud_scoring_failure_preserves_provider_error_code(tmp_path, monkeypatch):
    profile = providers.preset_profile("groq", metadata={"managed": False})

    class Client:
        def __init__(self):
            self.model = profile.model
            self.requested_model = profile.model
            self.actual_model = profile.model
            self.profile = profile

        def generate_json(self, *_args, **_kwargs):
            raise providers.ProviderError(
                "AUTH_INVALID",
                "credential rejected",
                details={"http_status": 401},
            )

    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    words = [
        {"word": f"word{i}", "start": i * 0.3, "end": i * 0.3 + 0.2}
        for i in range(30)
    ]
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 9.0}},
            "diarize": {"segments": [{"start": 0.0, "end": 9.0, "speaker": 0, "words": words}]},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": [{"start": 0.0, "end": 9.0, "curve_score": 0.8, "channel_scores": {}}]},
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}, quality_mode="best"),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: Client())

    with pytest.raises(StageError) as exc_info:
        stage.ScoreStage().run(ctx)

    assert exc_info.value.code == "AUTH_INVALID"
    assert "Local" not in str(exc_info.value)
    diagnostic = next((tmp_path / "diagnostics").glob(f"{exc_info.value.diagnostic_id}.json"))
    payload = json.loads(diagnostic.read_text(encoding="utf-8"))
    diagnostic_payload = payload["diagnostic"]
    assert diagnostic_payload["provider"] == "groq"
    assert diagnostic_payload["code"] == "AUTH_INVALID"
    assert diagnostic_payload["failures"][0]["provider_code"] == "AUTH_INVALID"


@pytest.mark.parametrize("failure_code", ["TIMEOUT", "PROVIDER_UNAVAILABLE"])
def test_local_t1_runtime_recovery_is_bounded(failure_code):
    class Client:
        profile = SimpleNamespace(kind="clipgauge-local")

        def __init__(self):
            self.calls = 0
            self.recoveries = 0

        def generate_json(self, _prompt, _schema):
            self.calls += 1
            if self.calls == 1:
                raise providers.ProviderError(
                    failure_code,
                    "temporary local failure",
                    details={"runtime_alive": failure_code != "TIMEOUT"},
                )
            return {"summary": "safe fixture"}

        def recover_for_scoring(self):
            self.recoveries += 1

    client = Client()
    assert stage._generate_t1(client, "safe prompt", rubric.T1_SCHEMA, set()) == {"summary": "safe fixture"}
    assert client.calls == 2
    assert client.recoveries == 1


def test_all_local_scoring_failures_are_typed_and_redacted(tmp_path, monkeypatch):
    profile = providers.preset_profile("clipgauge-local", metadata={"managed": False})

    class Client:
        def __init__(self):
            self.model = profile.model
            self.profile = profile

        def recover_for_scoring(self):
            pass

        def generate_json(self, prompt, _schema):
            raise providers.ProviderError(
                "TIMEOUT",
                "request timed out",
                details={"runtime_alive": True, "prompt": prompt, "transcript": "hidden"},
            )

    words = [
        {"word": f"word{i}", "start": i * 0.3, "end": i * 0.3 + 0.2}
        for i in range(30)
    ]
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 9.0}},
            "diarize": {"segments": [{"start": 0.0, "end": 9.0, "speaker": 0, "words": words}]},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": [{"start": 0.0, "end": 9.0, "curve_score": 0.8, "channel_scores": {}}]},
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: Client())

    with pytest.raises(StageError) as exc_info:
        stage.ScoreStage().run(ctx)

    error = exc_info.value
    assert error.code == "LOCAL_SCORING_TIMEOUT"
    diagnostic = next((tmp_path / "diagnostics").glob(f"{error.diagnostic_id}.json"))
    payload = diagnostic.read_text(encoding="utf-8")
    assert "LOCAL_SCORING_TIMEOUT" in payload
    assert "hidden" not in payload
    assert "safe prompt" not in payload


def test_local_scoring_keeps_successful_candidates_after_one_failure(monkeypatch, tmp_path):
    profile = providers.preset_profile("clipgauge-local", metadata={"managed": False})

    class Client:
        def __init__(self):
            self.model = profile.model
            self.profile = profile
            self.last_result = None
            self.calls = 0
            self.recoveries = 0

        def recover_for_scoring(self):
            self.recoveries += 1

        def structured_level(self):
            return "json_mode"

        def generate_json(self, _prompt, _schema):
            self.calls += 1
            if self.calls <= 2:
                raise providers.ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "temporary server error",
                    details={"runtime_alive": True, "http_status": 500},
                )
            return {
                "hook": 8,
                "hook_type": "bold_claim",
                "funniness": 5,
                "punchline_index": -1,
                "shock": 2,
                "curiosity_gap": 6,
                "value": 7,
                "self_contained": True,
                "bait_phrases": [],
                "summary": "A complete local scoring fixture.",
                "hook_strength": 8,
                "hook_reason": "claim",
                "standalone_comprehension": 7,
                "setup_strength": 7,
                "escalation_strength": 7,
                "payoff_strength": 7,
                "payoff_location": "middle",
                "ending_completeness": 7,
                "story_shape": "hook_setup_payoff",
                "information_density": 7,
                "reaction_strength": 7,
                "recommended_start_offset": 0.0,
                "recommended_end_offset": 5.0,
            }

    client = Client()
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    words = [
        {"word": f"word{i}", "start": i * 0.4, "end": i * 0.4 + 0.2}
        for i in range(50)
    ]
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 20.0}},
            "diarize": {"segments": [{"start": 0.0, "end": 20.0, "speaker": 0, "words": words}]},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {
                "candidates": [
                    {"start": 0.0, "end": 10.0, "curve_score": 0.8, "channel_scores": {}},
                    {"start": 10.0, "end": 20.0, "curve_score": 0.7, "channel_scores": {}},
                ]
            },
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )
    monkeypatch.setattr(stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(stage.providers_mod, "make_adapter", lambda _profile: client)

    result = stage.ScoreStage().run(ctx)

    assert result["scoring_degraded"] is True
    assert result["scoring_failures"] == {
        "attempted_count": 2,
        "successful_count": 1,
        "failed_count": 1,
        "failure_reason_counts": {"LOCAL_SCORING_UNAVAILABLE": 1},
    }
    assert client.recoveries == 1
