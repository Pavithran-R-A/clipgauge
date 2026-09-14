from clipgauge_pipeline import resource_guard, storage_estimate


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
