from __future__ import annotations

import json
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
