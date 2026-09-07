import json

import pytest
from clipgauge_pipeline import config
from clipgauge_pipeline.camera.stage import camera_mode_for_trajectory
from clipgauge_pipeline.jobs import queue
from clipgauge_pipeline.render.stage import (
    CameraTrajectoryContractError,
    validate_trajectory_contract,
)
from clipgauge_pipeline.scoring.short_quality import assess
from clipgauge_pipeline.scoring.stage import recommendation_outcome


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
