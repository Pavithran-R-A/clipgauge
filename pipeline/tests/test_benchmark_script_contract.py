from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "qa_owner_cloud_benchmark.ps1"
LOCAL_SCRIPT = Path(__file__).parents[2] / "scripts" / "qa_owner_local_benchmark.ps1"
GITIGNORE = Path(__file__).parents[2] / ".gitignore"


def test_owner_benchmark_backup_is_guarded_and_atomic():
    source = SCRIPT.read_text(encoding="utf-8")

    backup_copy = source.index("Copy-Item -Path (Join-Path $ownerJob '*')")
    try_scope = source.index("try {")
    backup_ready = source.index("$backupReady = $false")
    backup_complete = source.index("$backupReady = $true")
    finally_scope = source.index("finally {", backup_complete)
    restore_guard = source.index("if ($backupReady) {")

    assert try_scope < backup_copy
    assert backup_ready < backup_copy
    assert backup_copy < backup_complete
    assert backup_complete < finally_scope
    assert finally_scope < restore_guard
    assert "Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $ownerJob $item.Name)" in source


def test_owner_benchmark_preflights_storage_before_creating_temp_state():
    source = SCRIPT.read_text(encoding="utf-8")

    preflight = source.index("$requiredBackupBytes =")
    temp_root = source.index("$backupRoot =")
    free_check = source.index("if ($freeBytes -lt $requiredBackupBytes)")

    assert preflight < temp_root
    assert free_check < temp_root


def test_local_owner_benchmark_has_the_same_backup_safety_contract():
    source = LOCAL_SCRIPT.read_text(encoding="utf-8")

    backup_copy = source.index("Copy-Item -Path (Join-Path $ownerJob '*')")
    try_scope = source.index("try {")
    backup_ready = source.index("$backupReady = $false")
    backup_complete = source.index("$backupReady = $true")
    finally_scope = source.index("finally {")
    restore_guard = source.index("if ($backupReady) {")

    assert try_scope < backup_copy
    assert backup_ready < backup_copy
    assert backup_copy < backup_complete < finally_scope < restore_guard
    assert "Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $ownerJob $item.Name)" in source


def test_local_owner_benchmark_discards_stale_score_before_resume():
    source = LOCAL_SCRIPT.read_text(encoding="utf-8")

    score_path = source.index("$scorePath = Join-Path $ownerJob 'score.json'")
    stale_cleanup = source.index("Remove-Item -LiteralPath $scorePath", score_path)
    resume = source.index("--jsonl resume", score_path)

    assert stale_cleanup < resume


def test_local_owner_benchmark_rejects_nonzero_runs_before_parsing_score():
    source = LOCAL_SCRIPT.read_text(encoding="utf-8")

    nonzero_exit = source.index("if ($exitCode -ne 0) {")
    score_parse = source.index("$score = (Get-Content -LiteralPath $scorePath")

    assert nonzero_exit < score_parse


def test_owner_benchmark_scripts_expose_fixed_candidate_fingerprint():
    for script in (SCRIPT, LOCAL_SCRIPT):
        source = script.read_text(encoding="utf-8")
        assert "ExpectedCandidateFingerprint" in source
        assert "--candidate-fingerprint" in source
        assert "candidate_fingerprint" in source


def test_public_installer_smoke_uses_a_unique_marker_path():
    script = Path(__file__).parents[2] / "scripts" / "qa_public_installer_smoke.ps1"
    source = script.read_text(encoding="utf-8")

    assert "Guid]::NewGuid" in source
    assert "release-qualification-marker-" in source


def test_local_qualification_bundles_are_explicitly_ignored():
    source = GITIGNORE.read_text(encoding="utf-8")

    for bundle in (
        ".candidate-artifact/",
        ".public-v0515/",
        ".qualification-artifact/",
        ".qualification-artifact-current/",
        ".qualification-artifact-success/",
        ".windows-pr40-artifact/",
        "app/.qa-artifacts/",
        "app/src-tauri/gen/schemas/windows-schema.json",
    ):
        assert bundle in source


def test_cpu_asr_qualification_forces_real_cpu_int8_execution():
    script = Path(__file__).parents[2] / "scripts" / "qa_cpu_asr.py"
    source = script.read_text(encoding="utf-8")

    assert 'WhisperModel(str(managed.asr_model_path()), device="cpu", compute_type="int8")' in source
    assert 'ctranslate2.get_supported_compute_types("cpu")' in source
    assert '"v041-jfk.flac"' in source
    assert 'payload["transcription"]' not in source
