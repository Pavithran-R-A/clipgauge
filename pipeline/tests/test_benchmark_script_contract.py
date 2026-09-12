from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "qa_owner_cloud_benchmark.ps1"
LOCAL_SCRIPT = Path(__file__).parents[2] / "scripts" / "qa_owner_local_benchmark.ps1"


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
