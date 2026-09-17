import json
from pathlib import Path

from clipgauge_pipeline import resource_guard, storage_estimate


RELEASE_WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "release.yml"


def test_model_e2e_uses_production_managed_runtime_lifecycle():
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "Start deterministic managed scoring runtime" not in source
    assert "llama-server.pid" not in source
    assert "CLIPGAUGE_QA_RUNTIME_TRACE: '1'" in source
    assert "model-e2e-memory.log" in source
    assert "memory.limit_in_bytes" in source
    assert "memory.current" in source
    assert 'snapshot pipeline "$pipeline_pid"' in source
    assert "_AVPHYS_PAGES" in source
    assert "sc_avphys_bytes" in source


def test_url_estimate_prefers_exact_size_metadata():
    estimate = storage_estimate.for_url_metadata(
        {"duration": 600, "filesize": 2 * 1024**3, "filesize_approx": 900 * 1024**2}
    )

    assert estimate["source_bytes"] == 2 * 1024**3
    assert estimate["source_size_confidence"] == "exact"
    assert estimate["required_bytes"] > 2 * 1024**3


def test_url_estimate_uses_approximate_size_when_exact_missing():
    estimate = storage_estimate.for_url_metadata(
        {"duration": 600, "filesize_approx": 900 * 1024**2}
    )

    assert estimate["source_bytes"] == 900 * 1024**2
    assert estimate["source_size_confidence"] == "approximate"


def test_url_estimate_does_not_treat_missing_size_as_zero():
    estimate = storage_estimate.for_url_metadata({"duration": 600})

    assert estimate["source_bytes"] > 1 * 1024**3
    assert estimate["source_size_confidence"] == "duration-fallback"


def test_url_estimate_uses_selected_requested_formats_not_catalogue_sum():
    estimate = storage_estimate.for_url_metadata({
        "duration": 600,
        "formats": [{"format_id": str(index), "filesize": 2 * 1024**3} for index in range(15)],
        "requested_formats": [
            {"format_id": "137", "filesize": 300 * 1024**2},
            {"format_id": "140", "filesize": 50 * 1024**2},
        ],
    })

    assert estimate["source_bytes"] == 350 * 1024**2
    assert estimate["source_size_confidence"] == "exact"


def test_url_estimate_ignores_alternative_catalogue_sizes():
    estimate = storage_estimate.for_url_metadata({
        "duration": 60,
        "formats": [{"format_id": "137", "filesize": 3 * 1024**3}, {"format_id": "140", "filesize": 50 * 1024**2}],
    })

    assert estimate["source_size_confidence"] == "duration-fallback"
    assert estimate["source_bytes"] != 3 * 1024**3 + 50 * 1024**2


def test_url_estimate_deduplicates_selected_stream_records():
    estimate = storage_estimate.for_url_metadata({
        "duration": 60,
        "requested_formats": [
            {"format_id": "137", "filesize": 300 * 1024**2},
            {"format_id": "137", "filesize": 300 * 1024**2},
            {"format_id": "140", "filesize": 50 * 1024**2},
        ],
    })

    assert estimate["source_bytes"] == 350 * 1024**2
    assert estimate["source_size_confidence"] == "exact"


def test_url_estimate_sums_selected_approximate_components():
    estimate = storage_estimate.for_url_metadata({
        "duration": 120,
        "formats": [{"format_id": "bad-alternative", "filesize": 8 * 1024**3}],
        "requested_formats": [
            {"format_id": "137", "filesize_approx": 100 * 1024**2},
            {"format_id": "140", "filesize_approx": 20 * 1024**2},
        ],
    })

    assert estimate["source_bytes"] == 120 * 1024**2
    assert estimate["source_size_confidence"] == "approximate"


def test_url_estimate_uses_selected_bitrate_before_duration_fallback():
    estimate = storage_estimate.for_url_metadata({
        "duration": 100,
        "formats": [{"tbr": 10_000}],
        "requested_formats": [{"format_id": "137", "tbr": 100}, {"format_id": "140", "tbr": 50}],
    })

    assert estimate["source_bytes"] == 1_875_000
    assert estimate["source_size_confidence"] == "bitrate-estimate"


def test_url_metadata_uses_the_production_download_selector(monkeypatch):
    from clipgauge_pipeline.ingest import ytdlp

    calls = []
    monkeypatch.setattr(ytdlp, "ensure_ytdlp", lambda _progress: "yt-dlp")
    monkeypatch.setattr(
        ytdlp,
        "_run",
        lambda _binary, args, **_kwargs: calls.append(args) or json.dumps({"id": "fixture", "title": "Fixture", "duration": 60, "url": "https://example.test/video"}),
    )

    ytdlp.fetch_meta("https://example.test/video", lambda *_: None)

    args = calls[0]
    selector_index = args.index("-f")
    assert args[selector_index + 1] == ytdlp.download_format_for("mweb")


def test_asr_headroom_blocks_low_commit_before_model_load():
    decision = resource_guard.asr_headroom_decision(
        {"available_ram_bytes": 8 * 1024**3, "available_page_file_bytes": 3 * 1024**3},
        selected_device="cuda",
    )

    assert decision.code == "ASR_RESOURCE_HEADROOM_LOW"
    assert decision.blocked is True
    assert decision.required_bytes > decision.available_bytes


def test_abrupt_asr_exit_classifies_known_native_failure():
    result = resource_guard.classify_abrupt_exit(
        stage="asr",
        accelerator="cuda/int8_float16",
        stderr="tokenizers.pyd stopped unexpectedly",
        raw_exit_status=0xC0000005,
    )

    assert result.code == "WINDOWS_ACCESS_VIOLATION"
    assert result.allow_cpu_resume is True
    assert result.exit_code_hex == "0xC0000005"


def test_abrupt_cuda_exit_has_cpu_recovery():
    result = resource_guard.classify_abrupt_exit(
        stage="asr",
        accelerator="cuda/int8_float16",
        stderr="tokenizers.pyd stopped unexpectedly",
        raw_exit_status=0xC0000409,
    )

    assert result.code == "CUDA_NATIVE_CRASH"
    assert result.allow_cpu_resume is True


def test_resource_signal_disables_cpu_recovery_after_native_cuda_exit():
    result = resource_guard.classify_abrupt_exit(
        stage="asr",
        accelerator="cuda/int8_float16",
        stderr="CUDA native process reported memory allocation failure",
        raw_exit_status=0xC0000409,
    )

    assert result.code == "PIPELINE_RESOURCE_EXHAUSTED"
    assert result.allow_cpu_resume is False


def test_unknown_exit_stays_unknown():
    result = resource_guard.classify_abrupt_exit(
        stage="render",
        accelerator=None,
        stderr="",
        raw_exit_status=17,
    )

    assert result.code == "PIPELINE_NATIVE_CRASH"
    assert result.allow_cpu_resume is False
