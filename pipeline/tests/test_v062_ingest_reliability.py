import os
from pathlib import Path

import pytest

from clipgauge_pipeline.ingest import ytdlp
from clipgauge_pipeline.ingest import youtube_compat


def _stream_failure(tmp_path: Path) -> Path:
    if os.name == "nt":
        path = tmp_path / "yt-dlp-stream-failure.cmd"
        path.write_text(
            "@echo off\n"
            "echo stdout-only reason: transfer stalled\n"
            "echo stderr context: HTTP Error 429: Too Many Requests 1>&2\n"
            "exit /b 1\n",
            encoding="utf-8",
        )
        return path
    path = tmp_path / "yt-dlp-stream-failure"
    path.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'stdout-only reason: transfer stalled'\n"
        "printf '%s\\n' 'stderr context: HTTP Error 429: Too Many Requests' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_nonzero_ytdlp_keeps_bounded_tails_from_both_streams(tmp_path):
    with pytest.raises(ytdlp.YtDlpError) as exc_info:
        ytdlp._run(_stream_failure(tmp_path), [], inactivity_timeout=1.0)

    error = exc_info.value
    assert error.code == "YTDLP_RATE_LIMITED"
    assert error.details["exit_code"] == 1
    assert "stdout-only reason" in error.details["stdout_tail"]
    assert "HTTP Error 429" in error.details["stderr_tail"]
    assert len(error.details["stdout_tail"]) <= ytdlp.MAX_DIAGNOSTIC_TAIL
    assert len(error.details["stderr_tail"]) <= ytdlp.MAX_DIAGNOSTIC_TAIL


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("PO token required for GVS", "YTDLP_ATTESTATION_REQUIRED"),
        ("Please sign in to confirm your age", "YTDLP_LOGIN_REQUIRED"),
        ("This video is private", "YTDLP_PRIVATE"),
        ("This video is age-restricted", "YTDLP_AGE_RESTRICTED"),
        ("This video is not available in your country", "YTDLP_REGION_RESTRICTED"),
        ("Video unavailable; it may have been deleted", "YTDLP_UNAVAILABLE"),
        ("Could not resolve host: youtube.com", "YTDLP_DNS_FAILED"),
        ("Connection reset by peer", "YTDLP_NETWORK_FAILED"),
        ("Download failed after the transfer started", "YTDLP_TRANSFER_FAILED"),
        ("PO token provider failed to respond", "YTDLP_PROVIDER_FAILED"),
        ("Requested format is not available", "YTDLP_FORMAT_UNAVAILABLE"),
        ("HTTP Error 429: Too Many Requests", "YTDLP_RATE_LIMITED"),
        ("yt-dlp exited with code 1", "YTDLP_UNKNOWN_FAILURE"),
    ],
)
def test_ytdlp_failure_classifier_covers_creator_states(message, expected):
    assert ytdlp.classify_error(message) == expected


def test_attestation_recovery_tries_documented_fallback_once(monkeypatch):
    attempts = []
    invalidations = []

    def operation(method):
        attempts.append(method)
        raise ytdlp.YtDlpError(
            "HTTP Error 403: Forbidden",
            code="YTDLP_ATTESTATION_REQUIRED",
            details={"failure_phase": "GVS_TRANSFER", "http_status": 403},
        )

    monkeypatch.setattr(ytdlp.youtube_compat, "invalidate_public_compatibility", lambda: invalidations.append(True))
    monkeypatch.setattr(ytdlp, "_stop_operation_provider", lambda: None)

    with pytest.raises(ytdlp.YtDlpError) as exc_info:
        ytdlp._run_youtube_recovery(
            lambda: operation(attempts[-1] if attempts else "mweb"),
            source_url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            cookies_from_browser=None,
            compatibility_method="mweb",
            operation_for_method=operation,
        )

    assert attempts == ["mweb", "mweb", "web_safari"]
    assert invalidations == [True]
    assert exc_info.value.details["recovery"] == "web_safari_fallback"


def test_compatibility_diagnostic_redacts_stream_tails():
    diagnostic = ytdlp.compatibility_diagnostic(
        phase="GVS_TRANSFER",
        method="mweb",
        stderr="ERROR: HTTP Error 403: Forbidden token=secret-value",
        stdout="provider_response token=stdout-secret",
        exit_code=1,
    )

    assert diagnostic["method"] == "mweb"
    assert diagnostic["exit_code"] == 1
    assert "secret-value" not in diagnostic["stderr_tail"]
    assert "stdout-secret" not in diagnostic["stdout_tail"]
    assert diagnostic["http_status"] == 403


def test_public_transfer_failure_preserves_last_success(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, "home_dir", lambda: tmp_path)
    youtube_compat.record_public_compatibility_success(method="mweb", ytdlp_version="2026.08.19")
    previous = youtube_compat.public_compatibility_status()["last_successful_public_transfer_at"]

    youtube_compat.record_public_compatibility_attempt(error_code="YTDLP_RATE_LIMITED")
    current = youtube_compat.public_compatibility_status()

    assert current["verified"] is False
    assert current["last_successful_public_transfer_at"] == previous
    assert current["last_public_transfer_result"] == "failed"
    assert current["last_public_transfer_error_code"] == "YTDLP_RATE_LIMITED"
