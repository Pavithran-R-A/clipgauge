param(
    [string]$Model = 'clipgauge-local/qwen3-4b-q4_k_m'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$clipgaugeRoot = Join-Path $env:USERPROFILE '.clipgauge'
$ownerId = '20260909-125228-3c050e'
$ownerJob = Join-Path $clipgaugeRoot "jobs\$ownerId"
$python = Join-Path $clipgaugeRoot 'runtimes\pipeline\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $ownerJob)) { throw "owner benchmark job is missing: $ownerId" }
if (-not (Test-Path -LiteralPath $python)) { throw 'pipeline environment is missing' }

$backupRoot = Join-Path ([IO.Path]::GetTempPath()) "clipgauge-local-benchmark-$([Guid]::NewGuid().ToString('N'))"
$backupJob = Join-Path $backupRoot 'job'
New-Item -ItemType Directory -Force $backupJob | Out-Null
Copy-Item -LiteralPath (Join-Path $clipgaugeRoot 'db.sqlite3') -Destination (Join-Path $backupRoot 'db.sqlite3')
Copy-Item -Path (Join-Path $ownerJob '*') -Destination $backupJob -Recurse -Force

$previousHome = $env:CLIPGAUGE_HOME
$previousPath = $env:PYTHONPATH
$env:CLIPGAUGE_HOME = $clipgaugeRoot
$env:PYTHONPATH = Join-Path $repoRoot 'pipeline'

try {
    $commandErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = @(& $python -m clipgauge_pipeline.cli --jsonl resume $ownerId --provider clipgauge-local --model $Model --quality-mode balanced 2>&1 | ForEach-Object { $_.ToString() })
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $commandErrorAction
    $scorePath = Join-Path $ownerJob 'score.json'
    if (-not (Test-Path -LiteralPath $scorePath)) {
        [pscustomobject]@{ exit = $exitCode; score_present = $false; output_tail = @($output | Select-Object -Last 8) } | ConvertTo-Json -Compress
        exit $exitCode
    }
    $score = (Get-Content -LiteralPath $scorePath -Raw | ConvertFrom-Json).data
    $settings = Get-Content -LiteralPath (Join-Path $ownerJob 'settings.json') -Raw | ConvertFrom-Json
    $candidateCount = (Get-Content -LiteralPath (Join-Path $ownerJob 'candidates.json') -Raw | ConvertFrom-Json).data.count
    $allEntries = @($score.clips) + @($score.borderline_candidates) + @($score.rejected_candidates)
    $qualityTiers = @($allEntries | ForEach-Object { $_.quality.quality_tier } | Group-Object | ForEach-Object { @{ name = $_.Name; count = $_.Count } })
    $rejectionReasons = @($score.rejected_candidates | ForEach-Object { $_.rejection_reasons } | Group-Object | ForEach-Object { @{ name = $_.Name; count = $_.Count } })
    [pscustomobject]@{
        exit = $exitCode
        outcome = $score.outcome
        code = $score.code
        provider = $score.provider_kind
        requested_model = $settings.provider_model
        quality_mode = $settings.quality_mode
        candidate_count = $candidateCount
        scored_count = $score.scored_count
        recommended_count = $score.strong_recommendation_count
        good_count = $score.good_recommendation_count
        other_count = @($score.borderline_candidates).Count
        quality_tiers = $qualityTiers
        rejection_reasons = $rejectionReasons
        output_tail = @($output | Select-Object -Last 12)
    } | ConvertTo-Json -Compress
    exit $exitCode
}
finally {
    Copy-Item -LiteralPath (Join-Path $backupRoot 'db.sqlite3') -Destination (Join-Path $clipgaugeRoot 'db.sqlite3') -Force
    Copy-Item -Path (Join-Path $backupJob '*') -Destination $ownerJob -Recurse -Force
    if ($null -eq $previousHome) { Remove-Item Env:CLIPGAUGE_HOME -ErrorAction SilentlyContinue } else { $env:CLIPGAUGE_HOME = $previousHome }
    if ($null -eq $previousPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $previousPath }
    if (Test-Path -LiteralPath $backupRoot) {
        Add-Type -AssemblyName Microsoft.VisualBasic
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($backupRoot, [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs, [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin) | Out-Null
    }
}
