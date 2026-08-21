"""Stage 1A terminal-protocol regressions; intentionally added before fixes."""

import json
import os
from pathlib import Path

import pytest

from clipgauge_pipeline import cli
from clipgauge_pipeline.ingest.ytdlp import YtDlpError
from clipgauge_pipeline.jobs import queue


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))


def _events(capsys):
    rows = []
    for line in capsys.readouterr().out.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _run(monkeypatch, stage, source="/tmp/input.mp4"):
    monkeypatch.setattr(cli, "_stages", lambda: [stage])
    return cli.main(["--jsonl", "run", source])


class MissingSourceStage(queue.Stage):
    name = "ingest"
    schema_version = 1

    def run(self, ctx):
        raise queue.StageError(
            "File not found: /tmp/input.mp4",
            code="INPUT_FILE_NOT_FOUND",
            retryable=False,
        )


class YtDlpFailureStage(queue.Stage):
    name = "ingest"
    schema_version = 1

    def run(self, ctx):
        try:
            raise YtDlpError("video unavailable after yt-dlp update")
        except YtDlpError as err:
            raise queue.StageError(
                f"yt-dlp could not process this video: {err}",
                code="YTDLP_METADATA_FAILED",
                retryable=True,
            ) from err


class ExplodingStage(queue.Stage):
    name = "score"
    schema_version = 1

    def run(self, ctx):
        raise RuntimeError("secret=AIza-test Authorization: Bearer meta-test")


class SpeakerLoadFailureStage(queue.Stage):
    name = "diarize"
    schema_version = 2

    def run(self, ctx):
        cause = RuntimeError("checkpoint=invalid secret=AIza-speaker-test")
        raise queue.StageError(
            "Speaker analysis couldn’t start. The speaker model could not be loaded. Retry the model download or continue without speaker-aware reframing.",
            code="SPEAKER_MODEL_LOAD_FAILED",
            retryable=True,
        ) from cause


class SuccessStage(queue.Stage):
    name = "ingest"
    schema_version = 1

    def run(self, ctx):
        return {"title": "fixture"}


def _fake_ytdlp(tmp_path, message: str) -> Path:
    if os.name == "nt":
        fake = tmp_path / "yt-dlp-fake.cmd"
        fake.write_text(f"@echo off\n>&2 echo ERROR: {message}\nexit /b 1\n")
    else:
        fake = tmp_path / "yt-dlp-fake"
        fake.write_text(f"#!/bin/sh\nprintf 'ERROR: {message}\\n' >&2\nexit 1\n")
        fake.chmod(0o755)
    return fake


def _assert_one_terminal(events):
    terminal = [e for e in events if e.get("event") == "terminal"]
    assert len(terminal) == 1
    assert all(e.get("event") != "exited" for e in events)
    return terminal[0]


def test_progress_protocol_v2_exposes_creator_fields(capsys):
    emit = cli._progress_printer(True)
    emit("diarize", -1.0, "Downloading speaker model…")
    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "progress"
    assert event["protocol_version"] == 2
    assert event["stage_id"] == "diarize"
    assert event["display_stage"] == "Identifying speakers"
    assert event["indeterminate"] is True
    assert event["one_time_download"] is True
    assert event["elapsed_seconds"] >= 0
    assert event["stage_elapsed_seconds"] >= 0


def test_missing_local_source_is_structured_terminal(monkeypatch, capsys):
    code = _run(monkeypatch, MissingSourceStage())
    events = _events(capsys)
    assert code == 1
    terminal = _assert_one_terminal(events)
    assert terminal["protocol_version"] == 2
    assert terminal["ok"] is False
    assert terminal["stage"] == "ingest"
    assert terminal["code"] == "INPUT_FILE_NOT_FOUND"
    assert terminal["retryable"] is False
    assert terminal["message"] == "File not found: /tmp/input.mp4"


def test_yt_dlp_failure_is_actionable_and_retryable(monkeypatch, capsys):
    code = _run(monkeypatch, YtDlpFailureStage(), "https://example.test/video")
    events = _events(capsys)
    assert code == 1
    terminal = _assert_one_terminal(events)
    assert terminal["stage"] == "ingest"
    assert terminal["code"].startswith("YTDLP_")
    assert terminal["retryable"] is True
    assert "yt-dlp" in terminal["message"] or "video" in terminal["message"]


def test_speaker_failure_is_typed_retryable_and_has_diagnostic(monkeypatch, capsys):
    code = _run(monkeypatch, SpeakerLoadFailureStage())
    events = _events(capsys)
    assert code == 1
    terminal = _assert_one_terminal(events)
    assert terminal["stage"] == "diarize"
    assert terminal["code"] == "SPEAKER_MODEL_LOAD_FAILED"
    assert terminal["retryable"] is True
    assert terminal["diagnostic_id"]
    assert terminal["code"] != "INTERNAL_ERROR"
    output = capsys.readouterr().out
    assert "AIza-speaker-test" not in output

    job_event = next(e for e in events if e.get("event") == "job")
    diagnostics = list(queue.get_job(job_event["job_id"]).dir.glob("diagnostics/*.log"))
    assert diagnostics
    diagnostic_text = diagnostics[0].read_text()
    assert "AIza-speaker-test" not in diagnostic_text
    assert "RuntimeError" in diagnostic_text


def test_unexpected_exception_is_redacted_and_has_diagnostic(monkeypatch, capsys):
    code = _run(monkeypatch, ExplodingStage())
    events = _events(capsys)
    assert code == 1
    terminal = _assert_one_terminal(events)
    assert terminal["code"] == "INTERNAL_ERROR"
    assert terminal["retryable"] is False
    assert terminal["diagnostic_id"]
    output = capsys.readouterr().out
    assert "AIza-test" not in output
    assert "meta-test" not in output

    job_event = next(e for e in events if e.get("event") == "job")
    diagnostics = list(queue.get_job(job_event["job_id"]).dir.glob("diagnostics/*.log"))
    assert diagnostics
    diagnostic_text = diagnostics[0].read_text()
    assert "AIza-test" not in diagnostic_text
    assert "meta-test" not in diagnostic_text
    assert "RuntimeError" in diagnostic_text


def test_success_has_exactly_one_terminal_event(monkeypatch, capsys):
    code = _run(monkeypatch, SuccessStage())
    events = _events(capsys)
    assert code == 0
    terminal = _assert_one_terminal(events)
    assert terminal["protocol_version"] == 2
    assert terminal["ok"] is True
    assert terminal["job_id"]
    assert terminal["stage"] == "pipeline"
    assert terminal["code"] == "OK"
    assert terminal["retryable"] is False


def test_real_ingest_translates_fake_ytdlp_failure(monkeypatch, tmp_path, capsys):
    from clipgauge_pipeline.ingest import stage as ingest_stage

    fake = _fake_ytdlp(tmp_path, "video unavailable after extractor failure")
    monkeypatch.setattr(ingest_stage.ytdlp, "ensure_ytdlp", lambda _progress: fake)
    monkeypatch.setattr(cli, "_stages", lambda: [ingest_stage.IngestStage()])
    code = cli.main(["--jsonl", "run", "https://example.test/video"])
    events = _events(capsys)
    assert code == 1
    terminal = _assert_one_terminal(events)
    assert terminal["code"] == "YTDLP_UNAVAILABLE"
    assert terminal["stage"] == "ingest"
    assert terminal["retryable"] is True


def test_disposable_fake_ytdlp_failure_is_cleaned(monkeypatch, tmp_path):
    from clipgauge_pipeline.ingest import ytdlp

    fake = _fake_ytdlp(tmp_path, "video unavailable")
    with pytest.raises(YtDlpError, match="video unavailable"):
        ytdlp._run(fake, [], inactivity_timeout=1.0)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("HTTP Error 403: Forbidden; PO token required", "YTDLP_ATTESTATION_REQUIRED"),
        ("This video requires you to sign in and use cookies", "YTDLP_LOGIN_REQUIRED"),
        ("This is a private video", "YTDLP_PRIVATE"),
        ("This video is age-restricted", "YTDLP_AGE_RESTRICTED"),
        ("This video is not available in your country", "YTDLP_REGION_RESTRICTED"),
        ("Video unavailable; it may have been deleted", "YTDLP_UNAVAILABLE"),
    ],
)
def test_ytdlp_failure_states_are_distinct(message, expected):
    from clipgauge_pipeline.ingest import ytdlp

    assert ytdlp.classify_error(message) == expected


def test_ytdlp_error_carries_stable_code_and_retryability():
    error = YtDlpError("HTTP Error 403: Forbidden", code="YTDLP_ATTESTATION_REQUIRED", retryable=True)
    assert error.code == "YTDLP_ATTESTATION_REQUIRED"
    assert error.retryable is True
