import json
from pathlib import Path

from clipgauge_pipeline.edits.render_clip import _camera_filter_chain, _job_path, context_for_clip, context_for_clip_result


def _checkpoint(path: Path, data: dict) -> None:
    path.write_text(json.dumps({"data": data}))


def test_job_path_rebases_relative_artifacts_but_preserves_absolute_paths(tmp_path):
    job = tmp_path / "job"
    absolute = tmp_path / "outside" / "absolute.json"
    assert _job_path(job, "curves.json") == job / "curves.json"
    assert _job_path(job, absolute) == absolute


def test_context_resolves_relative_curve_and_trajectory_paths(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    _checkpoint(
        job / "ingest.json",
        {"media_path": "media.mp4", "probe": {"duration_sec": 10, "width": 1280, "height": 720}},
    )
    _checkpoint(job / "diarize.json", {"segments": []})
    _checkpoint(job / "events.json", {"timeline": [], "curves_path": "curves.json"})
    _checkpoint(job / "score.json", {"clips": [{"start": 1.0, "end": 4.0}]})
    (job / "curves.json").write_text(
        json.dumps({"grid_sec": 0.1, "rms": [0.2] * 100, "flux": [0.0] * 100})
    )
    _checkpoint(job / "camera.json", {"trajectories": {"0": "trajectory.json"}})
    (job / "trajectory.json").write_text(json.dumps({"fps": 25, "frames": [[0, 0, 100, 100]]}))

    (tmp_path / "different-cwd").mkdir()
    monkeypatch.chdir(tmp_path / "different-cwd")
    context = context_for_clip(job, 0)

    assert len(context["rms"]) == 100
    assert context["rms_grid"] == 0.1
    assert context["trajectory"] == {"fps": 25, "frames": [[0, 0, 100, 100]]}


def test_editor_camera_graph_keeps_encoder_frame_shape_fixed(tmp_path):
    command_text, chain = _camera_filter_chain(
        [(404, 720, 438, 0), (360, 642, 438, 38)],
        25.0,
        1280,
        720,
    )

    assert "scale@z" in command_text
    assert "crop@o" in command_text
    assert "crop@c w" not in command_text
    assert "scale@z=w=" in chain
    assert "crop@o=w=1080:h=1920" in chain


def test_context_result_degrades_when_optional_artifacts_are_missing(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    _checkpoint(
        job / "ingest.json",
        {"media_path": "media.mp4", "probe": {"duration_sec": 10, "width": 1280, "height": 720}},
    )
    _checkpoint(job / "score.json", {"clips": [{"start": 1.0, "end": 4.0, "score": 75}]})

    result = context_for_clip_result(job, 0)

    assert result["ok"] is True
    assert result["words"] == []
    assert result["rms"] == []
    assert result["events"] == []
    assert result["auto_cuts"] == []
    assert result["trajectory"] is None
    assert set(result["degraded_features"]) == {
        "speaker_transcript",
        "audio_waveform",
        "event_markers",
        "camera_trajectory",
    }


def test_context_result_reports_typed_required_artifact_failure(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    result = context_for_clip_result(job, 0)

    assert result["ok"] is False
    assert result["code"] == "EDIT_CONTEXT_ARTIFACTS_MISSING"
    assert "ingest" in result["missing_or_invalid_artifacts"]
    assert result["diagnostic_id"].startswith("edit-context-")


def test_context_result_reports_invalid_clip_index(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    _checkpoint(
        job / "ingest.json",
        {"media_path": "media.mp4", "probe": {"duration_sec": 10, "width": 1280, "height": 720}},
    )
    _checkpoint(job / "score.json", {"clips": []})

    result = context_for_clip_result(job, 0)

    assert result["ok"] is False
    assert result["code"] == "EDIT_CLIP_INDEX_INVALID"
    assert result["missing_or_invalid_artifacts"] == ["score.clips[0]"]
