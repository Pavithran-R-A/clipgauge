import json

import pytest
from clipgauge_pipeline import cli, config
from clipgauge_pipeline.camera.stage import camera_mode_for_trajectory
from clipgauge_pipeline.candidates import stage as candidates_stage
from clipgauge_pipeline.candidates import story_units
from clipgauge_pipeline.jobs import queue
from clipgauge_pipeline.render.stage import (
    CameraTrajectoryContractError,
    validate_trajectory_contract,
)
from clipgauge_pipeline.scoring.short_quality import assess
from clipgauge_pipeline.scoring.stage import ScoreStage, recommendation_outcome


def test_candidate_stage_schema_invalidates_opening_policy_checkpoints():
    assert candidates_stage.CandidatesStage.schema_version == 42


def test_score_stage_schema_invalidates_opening_selection_checkpoints():
    assert ScoreStage.schema_version == 38


def test_zero_recommendations_have_successful_terminal_outcome():
    result = recommendation_outcome(
        candidate_count=5,
        eligible_candidate_count=5,
        scored_count=5,
        clips=[],
    )

    assert result["outcome"] == "SUCCESS_NO_RECOMMENDATIONS"
    assert result["code"] == "NO_RECOMMENDED_CLIPS"
    assert result["counts"]["candidate_count"] == 5


def test_tamil_candidate_uses_aligned_boundary_without_english_punctuation():
    tamil = "\u0b87\u0ba8\u0bcd\u0ba4 \u0b95\u0bcb\u0b9f\u0bcd\u0b9f\u0bc8\u0baf\u0bbf\u0bb2\u0bcd \u0b92\u0bb0\u0bc1 \u0bb0\u0b95\u0b9a\u0bbf\u0baf \u0b85\u0bb1\u0bc8 \u0b89\u0bb3\u0bcd\u0bb3\u0ba4\u0bc1"
    quality = assess(
        tamil,
        [],
        5.0,
        llm={
            "hook_strength": 8,
            "standalone_comprehension": 8,
            "setup_strength": 8,
            "escalation_strength": 7,
            "payoff_strength": 8,
            "ending_completeness": 8,
            "story_shape": "reveal",
            "reaction_strength": 7,
        },
        ending_evidence={
            "punctuated": False,
            "segment_boundary": True,
            "semantic_complete": True,
        },
    )

    assert quality["eligible_to_recommend"] is True
    assert quality["language_signal_mode"] == "neutral_non_english"


def test_missing_trajectory_is_a_typed_contract_failure():
    with pytest.raises(CameraTrajectoryContractError) as caught:
        validate_trajectory_contract(
            [{"start": 0.0, "end": 5.0}],
            {"0": "trajectory_00.json"},
            existing_paths=set(),
        )

    assert caught.value.code == "CAMERA_TRAJECTORY_MISSING"
    assert caught.value.context["missing_indexes"] == [0]


def test_malformed_trajectory_map_is_a_typed_contract_failure():
    with pytest.raises(CameraTrajectoryContractError) as caught:
        validate_trajectory_contract([{"start": 0.0, "end": 5.0}], [])

    assert caught.value.code == "CAMERA_TRAJECTORY_MISSING"
    assert caught.value.context["available_trajectories"] == []


def test_static_center_camera_mode_is_explicit():
    assert camera_mode_for_trajectory({"meta": {"faceless_fallback": True}}) == "static_center"


def test_zero_recommendations_stop_before_camera_and_render(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))

    class ScoreStage(queue.Stage):
        name = "score"
        schema_version = 1

        def run(self, ctx):
            return {
                "outcome": "SUCCESS_NO_RECOMMENDATIONS",
                "code": "NO_RECOMMENDED_CLIPS",
                "counts": {"candidate_count": 2},
                "clips": [],
            }

    class MustNotRun(queue.Stage):
        name = "camera"
        schema_version = 1

        def run(self, ctx):
            raise AssertionError("camera must not run for zero recommendations")

    job = queue.create_job("file", "C:\\Videos\\source.mp4", json.dumps(config.Settings().to_json()))
    results = queue.run_stages(job, [ScoreStage(), MustNotRun()], lambda *_: None)

    assert results["score"]["outcome"] == "SUCCESS_NO_RECOMMENDATIONS"
    assert not (job.dir / "camera.json").exists()
    diagnostics = list((job.dir / "diagnostics").glob("*.json"))
    assert diagnostics
    assert any(
        "candidate_count" in path.read_text(encoding="utf-8")
        for path in diagnostics
    )


def test_candidates_stage_returns_typed_no_recommendations(monkeypatch, tmp_path):
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(
        json.dumps({
            "dynamics": [],
            "grid_sec": 1.0,
            "arousal": [],
            "arousal_grid_sec": 1.0,
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(candidates_stage, "detect_scenes", lambda _path: [])
    monkeypatch.setattr(story_units, "build_sentence_units", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        story_units,
        "synthesize",
        lambda *args, **kwargs: {
            "units": [],
            "topic_segment_count": 0,
            "anchors": [],
            "raw_span_variants": 0,
            "cheap_survivors": 0,
            "boundary_calls": 0,
            "candidates": [],
            "candidate_audit": {
                "raw_proposals": 0,
                "deterministic_proposals": 0,
                "llm_proposals": 0,
                "story_unit_proposals": 0,
                "deduped_proposals": 0,
                "shortlisted_proposals": 0,
                "rejection_reasons": [],
            },
        },
    )

    class Settings:
        def provider_snapshot(self):
            return {}

    class Context:
        def __init__(self):
            self.job_dir = tmp_path
            self.prior = {
                "ingest": {"probe": {"duration_sec": 10.0}, "media_path": "source.mp4"},
                "diarize": {"segments": [], "turns": []},
                "events": {"curves_path": str(curves_path), "timeline": []},
            }
            self.settings = Settings()

        @staticmethod
        def emit(*args, **kwargs):
            return None

    result = candidates_stage.CandidatesStage().run(Context())

    assert result["outcome"] == "SUCCESS_NO_RECOMMENDATIONS"
    assert result["code"] == "NO_RECOMMENDED_CLIPS"
    assert result["candidates"] == []
    assert result["count"] == 0
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


def test_candidates_stage_keeps_boundary_discovery_provider_independent(monkeypatch, tmp_path):
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(
        json.dumps({"dynamics": [], "grid_sec": 1.0, "arousal": [], "arousal_grid_sec": 1.0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(candidates_stage, "detect_scenes", lambda _path: [])
    monkeypatch.setattr(story_units, "build_sentence_units", lambda *args, **kwargs: [])
    captured = {}

    def synthesize(*args, **kwargs):
        captured["boundary_proposer"] = kwargs["boundary_proposer"]
        return {
            "units": [],
            "topic_segment_count": 0,
            "anchors": [],
            "raw_span_variants": 0,
            "cheap_survivors": 0,
            "boundary_calls": 0,
            "candidates": [],
            "candidate_audit": {
                "raw_proposals": 0,
                "deterministic_proposals": 0,
                "llm_proposals": 0,
                "story_unit_proposals": 0,
                "deduped_proposals": 0,
                "shortlisted_proposals": 0,
                "rejection_reasons": [],
            },
        }

    monkeypatch.setattr(story_units, "synthesize", synthesize)

    class Settings:
        def provider_snapshot(self):
            return {
                "schema_version": 1,
                "id": "local-test",
                "kind": "ollama",
                "model": "test-model",
                "endpoint_identity": "http://127.0.0.1:11434",
                "capabilities": {"local": True, "cloud": False},
            }

    class Context:
        def __init__(self):
            self.job_dir = tmp_path
            self.prior = {
                "ingest": {"probe": {"duration_sec": 10.0}, "media_path": "source.mp4"},
                "diarize": {"segments": [], "turns": []},
                "events": {"curves_path": str(curves_path), "timeline": []},
            }
            self.settings = Settings()

        @staticmethod
        def emit(*args, **kwargs):
            return None

    result = candidates_stage.CandidatesStage().run(Context())

    assert captured["boundary_proposer"] is None
    assert result["boundary_calls"] == 0


def test_cli_uses_candidate_stage_terminal_outcome():
    stage, result = cli._terminal_result({
        "ingest": {},
        "candidates": {
            "outcome": "SUCCESS_NO_RECOMMENDATIONS",
            "code": "NO_RECOMMENDED_CLIPS",
            "counts": {"candidate_count": 0},
        },
    })

    assert stage == "candidates"
    assert result["code"] == "NO_RECOMMENDED_CLIPS"
