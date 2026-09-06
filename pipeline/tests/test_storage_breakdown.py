import sqlite3

import pytest

from clipgauge_pipeline.storage import breakdown, cleanup, preview


def test_storage_breakdown_has_user_visible_categories_and_no_auto_delete(tmp_path):
    (tmp_path / "models" / "clipgauge-local").mkdir(parents=True)
    (tmp_path / "models" / "clipgauge-local" / "model.gguf").write_bytes(b"model")
    (tmp_path / "jobs" / "job-1" / "outputs").mkdir(parents=True)
    (tmp_path / "jobs" / "job-1" / "outputs" / "clip.mp4").write_bytes(b"clip")
    (tmp_path / "downloads").mkdir()
    (tmp_path / "downloads" / "partial.part").write_bytes(b"partial")

    rows = {row["category"]: row for row in breakdown(tmp_path)}

    assert set(rows) == {"components", "local-ai", "sessions", "rendered", "download-cache", "temp-partial", "diagnostics"}
    assert rows["local-ai"]["bytes"] == 5
    assert rows["rendered"]["bytes"] == 4
    assert rows["download-cache"]["deletable"] is True
    assert rows["sessions"]["deletable"] is False
    assert all(row["requires_confirmation"] for row in rows.values())


def test_cleanup_requires_confirmation_and_only_removes_safe_cache(tmp_path):
    partial = tmp_path / "downloads" / "partial.part"
    partial.parent.mkdir()
    partial.write_bytes(b"partial")
    result = preview(tmp_path, "safe-cache")
    assert result["paths"] == ["downloads/partial.part"]
    with pytest.raises(ValueError, match="confirmation"):
        cleanup(tmp_path, "safe-cache")
    removed = cleanup(tmp_path, "safe-cache", confirmed=True)
    assert removed["removed"] == ["downloads/partial.part"]
    assert not partial.exists()


def test_failed_session_cleanup_removes_artifacts_and_database_row(tmp_path):
    job_id = "20260818-155237-c6b118"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "source.mp4").write_bytes(b"source")
    with sqlite3.connect(tmp_path / "db.sqlite3") as connection:
        connection.executescript("CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT); CREATE TABLE stage_runs (job_id TEXT);")
        connection.execute("INSERT INTO jobs VALUES (?, 'failed')", (job_id,))
        connection.execute("INSERT INTO stage_runs VALUES (?)", (job_id,))
        connection.commit()
    result = cleanup(tmp_path, "failed-session", job_id, confirmed=True)
    assert result["removed"] == [f"jobs/{job_id}"]
    assert not job_dir.exists()
    with sqlite3.connect(tmp_path / "db.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM stage_runs").fetchone()[0] == 0
