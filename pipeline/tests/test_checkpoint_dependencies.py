import os
from types import SimpleNamespace

from clipgauge_pipeline import config
from clipgauge_pipeline.jobs import queue
from clipgauge_pipeline.scoring import constants
from clipgauge_pipeline.scoring import providers
from clipgauge_pipeline.scoring.stage import ScoreStage


class _AsrLikeStage(queue.Stage):
    name = "asr"
    schema_version = 99


class _IngestLikeStage(queue.Stage):
    name = "ingest"
    schema_version = 1


def test_cpu_recovery_changes_asr_dependency_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))
    settings = config.Settings()
    job = SimpleNamespace(id="job", source_type="file", source="C:\\Videos\\source.mp4", dir=config.jobs_dir() / "job")
    ctx = queue.StageContext(job=job, settings=settings, progress=lambda *_: None)
    stage = _AsrLikeStage()

    before = queue._dependency_fingerprint(stage, ctx, {})
    settings.allow_cpu_asr_fallback = True
    after = queue._dependency_fingerprint(stage, ctx, {})

    assert before != after


def test_source_identity_changes_ingest_dependency_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-v1")
    settings = config.Settings()
    job = SimpleNamespace(id="job", source_type="file", source=str(source), dir=config.jobs_dir() / "job")
    ctx = queue.StageContext(job=job, settings=settings, progress=lambda *_: None)
    stage = _AsrLikeStage()

    before = queue._dependency_fingerprint(stage, ctx, {})
    source.write_bytes(b"source-v2-replaced")
    after = queue._dependency_fingerprint(stage, ctx, {})

    assert before != after


def test_same_size_preserved_mtime_source_change_invalidates_ingest(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-v1")
    settings = config.Settings()
    job = SimpleNamespace(id="job", source_type="file", source=str(source), dir=config.jobs_dir() / "job")
    ctx = queue.StageContext(job=job, settings=settings, progress=lambda *_: None)
    stage = _IngestLikeStage()
    before_stat = source.stat()
    before = queue._dependency_fingerprint(stage, ctx, {})
    source.write_bytes(b"source-v2")
    os.utime(source, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))
    after = queue._dependency_fingerprint(stage, ctx, {})

    assert before != after


def test_checkpoint_rejects_stale_dependency_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))
    job_dir = config.jobs_dir() / "job"
    job_dir.mkdir(parents=True)
    job = SimpleNamespace(id="job", dir=job_dir)
    queue.write_checkpoint(job, "asr", 99, {"value": 1, "_checkpoint": {"dependency_fingerprint": "old"}})

    cached, issue = queue.read_checkpoint_detailed(job, "asr", 99, "new")

    assert cached is None
    assert issue is not None
    assert issue.code == "CHECKPOINT_DEPENDENCY_STALE"


def test_score_dependency_fingerprint_includes_quality_versions(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "profile with spaces"))
    settings = config.Settings()
    job = SimpleNamespace(id="job", source_type="file", source="C:\\Videos\\source.mp4", dir=config.jobs_dir() / "job")
    ctx = queue.StageContext(job=job, settings=settings, progress=lambda *_: None)
    stage = ScoreStage()

    before = queue._dependency_fingerprint(stage, ctx, {})
    settings.quality_mode = "best"
    quality_changed = queue._dependency_fingerprint(stage, ctx, {})
    settings.quality_mode = "private"
    settings.output_preference = "more"
    output_changed = queue._dependency_fingerprint(stage, ctx, {})
    settings.output_preference = "recommended"
    monkeypatch.setattr(constants, "active", lambda: {"version": 2})
    calibration_changed = queue._dependency_fingerprint(stage, ctx, {})
    monkeypatch.setattr(providers, "RUBRIC_CACHE_VERSION", "balanced-v2")
    rubric_changed = queue._dependency_fingerprint(stage, ctx, {})

    assert before != quality_changed
    assert before != output_changed
    assert before != calibration_changed
    assert before != rubric_changed
