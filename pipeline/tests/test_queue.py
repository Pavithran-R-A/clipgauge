"""Job queue + checkpoint/resume contract tests.

The resume guarantee is the whole point of M0: kill anywhere, re-run, and
only missing/stale work repeats. These tests exercise that contract without
any media."""

import json

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.jobs import queue


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    yield


def _settings_json() -> str:
    return json.dumps(config.Settings().to_json())


class CountingStage(queue.Stage):
    name = "counting"
    schema_version = 1

    def __init__(self):
        self.runs = 0

    def run(self, ctx):
        self.runs += 1
        return {"runs": self.runs}


class FailingStage(queue.Stage):
    name = "failing"
    schema_version = 1

    def run(self, ctx):
        raise queue.StageError("boom, but politely")


class ArtifactStage(queue.Stage):
    name = "artifact"
    schema_version = 1

    def __init__(self):
        self.runs = 0

    def run(self, ctx):
        self.runs += 1
        out = ctx.job_dir / "artifact.bin"
        out.write_bytes(b"data")
        return {"path": str(out)}

    def artifacts_ok(self, ctx, data):
        from pathlib import Path

        return Path(data["path"]).exists()


def _noop_progress(stage, fraction, message):
    pass


def test_create_and_get_job():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    fetched = queue.get_job(job.id)
    assert fetched is not None
    assert fetched.source == "/tmp/x.mp4"
    assert job.dir.exists()
    assert (job.dir / "settings.json").exists()


def test_stage_runs_once_then_caches():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = CountingStage()
    queue.run_stages(job, [stage], _noop_progress)
    queue.run_stages(job, [stage], _noop_progress)
    assert stage.runs == 1  # second run served from checkpoint


def test_stage_timing_diagnostic_records_active_and_cached_runs():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = CountingStage()
    queue.run_stages(job, [stage], _noop_progress)
    queue.run_stages(job, [stage], _noop_progress)

    timing = json.loads(queue.stage_timing_path(job).read_text())
    records = timing["stages"]
    assert records[0]["name"] == "counting"
    assert records[0]["active_seconds"] >= 0
    assert records[0]["cached"] is False
    assert records[1]["cached"] is True
    assert set(records[0]) >= {"name", "active_seconds", "cached", "backend", "workload", "workload_count"}
    assert "source" not in records[0]


def test_schema_version_bump_invalidates():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = CountingStage()
    queue.run_stages(job, [stage], _noop_progress)
    stage.schema_version = 2
    queue.run_stages(job, [stage], _noop_progress)
    assert stage.runs == 2


def test_missing_artifact_invalidates_checkpoint():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = ArtifactStage()
    queue.run_stages(job, [stage], _noop_progress)
    (job.dir / "artifact.bin").unlink()
    queue.run_stages(job, [stage], _noop_progress)
    assert stage.runs == 2


def test_corrupt_checkpoint_reruns():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = CountingStage()
    queue.run_stages(job, [stage], _noop_progress)
    queue.checkpoint_path(job, stage.name).write_text("{not json")
    queue.run_stages(job, [stage], _noop_progress)
    assert stage.runs == 2


def test_stage_error_marks_job_failed():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    with pytest.raises(queue.StageError):
        queue.run_stages(job, [FailingStage()], _noop_progress)
    fetched = queue.get_job(job.id)
    assert fetched.status == "failed"
    assert "politely" in (fetched.error or "")


def test_checkpoint_contains_relative_descriptors_and_manifest():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = ArtifactStage()
    queue.run_stages(job, [stage], _noop_progress)
    envelope = json.loads(queue.checkpoint_path(job, stage.name).read_text())
    assert envelope["artifacts"][0]["relative_path"] == "artifact.bin"
    assert not envelope["artifacts"][0]["relative_path"].startswith("/")
    manifest = json.loads((job.dir / "artifact-manifest.json").read_text())
    assert manifest["stages"]["artifact"]["artifacts"][0]["role"] == "path"


def test_changed_artifact_content_invalidates_even_when_size_is_unchanged():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = ArtifactStage()
    queue.run_stages(job, [stage], _noop_progress)
    (job.dir / "artifact.bin").write_bytes(b"else")
    queue.run_stages(job, [stage], _noop_progress)
    assert stage.runs == 2


def test_malformed_checkpoint_emits_structured_recovery_message():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    stage = CountingStage()
    queue.run_stages(job, [stage], _noop_progress)
    queue.checkpoint_path(job, stage.name).write_text(
        json.dumps({"stage": stage.name, "schema_version": stage.schema_version, "data": {"runs": 1}})
    )
    messages = []
    queue.run_stages(job, [stage], lambda s, f, m: messages.append((s, m)))
    assert stage.runs == 2
    assert any("CHECKPOINT_DESCRIPTOR_MISSING" in message for _, message in messages)


def test_outside_root_artifact_fails_closed_with_typed_error(tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"not managed")

    class OutsideStage(queue.Stage):
        name = "outside"
        schema_version = 1

        def run(self, ctx):
            return {"path": str(outside)}

    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    with pytest.raises(queue.StageError) as exc:
        queue.run_stages(job, [OutsideStage()], _noop_progress)
    assert exc.value.code == "ARTIFACT_OUTSIDE_MANAGED_ROOT"


def test_failure_then_resume_skips_completed_stages():
    job = queue.create_job("file", "/tmp/x.mp4", _settings_json())
    counting = CountingStage()
    with pytest.raises(queue.StageError):
        queue.run_stages(job, [counting, FailingStage()], _noop_progress)
    assert counting.runs == 1

    class FixedStage(queue.Stage):
        name = "failing"  # same name — simulates the bug being fixed
        schema_version = 1

        def run(self, ctx):
            return {"ok": True}

    results = queue.run_stages(job, [counting, FixedStage()], _noop_progress)
    assert counting.runs == 1  # not re-run
    assert results["failing"] == {"ok": True}
    assert queue.get_job(job.id).status == "done"
