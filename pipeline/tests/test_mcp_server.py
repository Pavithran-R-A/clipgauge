import json
import threading

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.jobs import queue
from clipgauge_pipeline.mcp_server import McpService, TOOLS, reject_secret_arguments
from clipgauge_pipeline.server.auth import authorize, is_loopback, require_server_token


def test_mcp_rejects_secret_shaped_arguments():
    with pytest.raises(ValueError):
        reject_secret_arguments({"source": "video.mp4", "api_key": "do-not-accept"})


def test_mcp_tools_are_protocol_safe_without_running_jobs(capsys):
    service = McpService()
    assert service.call("preflight", {})["ok"] is True
    assert service.call("list_providers", {})
    service._executor.shutdown(wait=False, cancel_futures=True)
    assert capsys.readouterr().out == ""


def test_mcp_resume_clears_cancel_marker_for_same_job(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    settings = json.dumps(config.Settings().to_json())
    job = queue.create_job("file", str(tmp_path / "media.mp4"), settings)
    marker = job.dir / "cancel.requested"
    marker.write_text("requested\n", encoding="utf-8")
    service = McpService()
    service._run_job = lambda _job: None
    try:
        result = service.call("resume_job", {"job_id": job.id})
        assert result == {"job_id": job.id, "status": "pending", "resumed": True}
        assert not marker.exists()
    finally:
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_mcp_resume_rejects_invalid_id_and_exposes_schema():
    assert "resume_job" in TOOLS
    service = McpService()
    try:
        with pytest.raises(ValueError, match="invalid job identifier"):
            service.call("resume_job", {"job_id": "../escape"})
    finally:
        service._executor.shutdown(wait=False, cancel_futures=True)


def test_mcp_resume_rejects_active_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    job = queue.create_job("file", str(tmp_path / "media.mp4"), json.dumps(config.Settings().to_json()))
    started = threading.Event()
    release = threading.Event()
    service = McpService()

    def blocking(_job):
        started.set()
        release.wait(timeout=5)

    service._run_job = blocking
    try:
        service._submit_job(job)
        assert started.wait(timeout=5)
        with pytest.raises(ValueError, match="already active"):
            service.call("resume_job", {"job_id": job.id})
    finally:
        release.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_pending_cancellation_is_distinct_from_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    job = queue.create_job("file", str(tmp_path / "media.mp4"), json.dumps(config.Settings().to_json()))
    service = McpService()
    try:
        result = service.cancel(job.id)
        assert result["cancel_requested"] is True
        assert queue.get_job(job.id).status == "cancelled"
    finally:
        service._executor.shutdown(wait=False, cancel_futures=True)


def test_terminal_cancellation_does_not_report_running(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    job = queue.create_job("file", str(tmp_path / "media.mp4"), json.dumps(config.Settings().to_json()))
    queue.set_job_status(job.id, "done")
    service = McpService()
    try:
        assert service.cancel(job.id) == {
            "job_id": job.id,
            "cancel_requested": False,
            "status": "done",
        }
        assert not (job.dir / "cancel.requested").exists()
    finally:
        service._executor.shutdown(wait=False, cancel_futures=True)


def test_server_auth_defaults_to_loopback():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    require_server_token("127.0.0.1", None)
    with pytest.raises(ValueError):
        require_server_token("0.0.0.0", None)
    assert authorize("secret", "secret")
    assert not authorize("wrong", "secret")
