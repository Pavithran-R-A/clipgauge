param(
    [ValidateSet('groq', 'openrouter')]
    [string]$Provider = 'groq',
    [string]$Model = 'openai/gpt-oss-20b'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$clipgaugeRoot = Join-Path $env:USERPROFILE '.clipgauge'
$ownerId = '20260909-125228-3c050e'
$ownerJob = Join-Path $clipgaugeRoot "jobs\$ownerId"
$python = Join-Path $clipgaugeRoot 'runtimes\pipeline\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $ownerJob)) {
    throw "owner benchmark job is missing: $ownerId"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'repository pipeline environment is missing'
}

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ClipGaugeOwnerCredentialReader {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct CREDENTIAL {
        public UInt32 Flags;
        public UInt32 Type;
        public IntPtr TargetName;
        public IntPtr Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public IntPtr TargetAlias;
        public IntPtr UserName;
    }
    [DllImport("Advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);
    [DllImport("Advapi32.dll", SetLastError=true)]
    static extern void CredFree(IntPtr credential);
    public static string Read(string target) {
        IntPtr pointer;
        if (!CredRead(target, 1, 0, out pointer)) return null;
        try {
            var credential = Marshal.PtrToStructure<CREDENTIAL>(pointer);
            if (credential.CredentialBlob == IntPtr.Zero || credential.CredentialBlobSize == 0) return null;
            var bytes = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, bytes, 0, bytes.Length);
            return Encoding.Unicode.GetString(bytes).TrimEnd('\0');
        } finally {
            CredFree(pointer);
        }
    }
}
"@

$account = "provider_auth_preset-$Provider"
$secretTarget = "LegacyGeneric:target=$account.io.github.pavithranra.clipgauge"
$secret = [ClipGaugeOwnerCredentialReader]::Read($secretTarget)
if (-not $secret) {
    throw "configured $Provider credential is unavailable"
}

if ($Provider -eq 'groq' -and $Model -notin @(
        'openai/gpt-oss-20b',
        'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'qwen/qwen3.6-27b'
    )) {
    throw 'Groq benchmark model is not in the current approved set'
}
if ($Provider -eq 'openrouter' -and [string]::IsNullOrWhiteSpace($Model)) {
    throw 'OpenRouter benchmark model cannot be empty'
}

$backupRoot = Join-Path ([IO.Path]::GetTempPath()) "clipgauge-owner-benchmark-$([Guid]::NewGuid().ToString('N'))"
$backupJob = Join-Path $backupRoot 'job'
$previousHome = $env:CLIPGAUGE_HOME
$previousPath = $env:PYTHONPATH
$providerEnv = if ($Provider -eq 'groq') { 'CLIPGAUGE_GROQ_API_KEY' } else { 'CLIPGAUGE_OPENROUTER_API_KEY' }
$previousKey = [Environment]::GetEnvironmentVariable($providerEnv, 'Process')
$backupReady = $false

try {
    New-Item -ItemType Directory -Force $backupJob | Out-Null
    Copy-Item -LiteralPath (Join-Path $clipgaugeRoot 'db.sqlite3') -Destination (Join-Path $backupRoot 'db.sqlite3')
    Copy-Item -Path (Join-Path $ownerJob '*') -Destination $backupJob -Recurse -Force
    $backupReady = $true

    $env:CLIPGAUGE_HOME = $clipgaugeRoot
    $env:PYTHONPATH = Join-Path $repoRoot 'pipeline'
    Set-Item -Path "Env:$providerEnv" -Value $secret

    $scorePath = Join-Path $ownerJob 'score.json'
    Remove-Item -LiteralPath $scorePath -Force -ErrorAction SilentlyContinue
    $commandErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = @(& $python -m clipgauge_pipeline.cli --jsonl resume $ownerId --provider $Provider --model $Model --quality-mode best 2>&1 | ForEach-Object { $_.ToString() })
    $ErrorActionPreference = $commandErrorAction
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        [pscustomobject]@{ exit = $exitCode; score_present = $false; output_tail = @($output | Select-Object -Last 12) } | ConvertTo-Json -Compress
        exit $exitCode
    }
    if (-not (Test-Path -LiteralPath $scorePath)) {
        [pscustomobject]@{ exit = $exitCode; score_present = $false; output_tail = @($output | Select-Object -Last 5) } | ConvertTo-Json -Compress
        exit $exitCode
    }

    $score = (Get-Content -LiteralPath $scorePath -Raw | ConvertFrom-Json).data
    $settings = Get-Content -LiteralPath (Join-Path $ownerJob 'settings.json') -Raw | ConvertFrom-Json
    $candidateCount = (Get-Content -LiteralPath (Join-Path $ownerJob 'candidates.json') -Raw | ConvertFrom-Json).data.count
    $clips = @($score.clips)
    $reported = 0
    $verified = 0
    $rejected = 0
    foreach ($clip in $clips) {
        if ($clip.t1_raw -and $clip.t1_raw.bait_phrases) {
            $reported += @($clip.t1_raw.bait_phrases).Count
        }
        foreach ($adjustment in @($clip.adjustments)) {
            if ($adjustment.rule -ne 'bait_verification') { continue }
            $verified += @($adjustment.verified_bait).Count
            $rejected += @($adjustment.rejected_bait).Count
        }
    }

    $actualModel = $score.model
    if (-not $actualModel -and $clips.Count -gt 0) {
        $actualModel = $clips[0].ledger.provenance.model
    }
    [pscustomobject]@{
        exit = $exitCode
        outcome = $score.outcome
        code = $score.code
        provider = $score.provider_kind
        requested_model = $settings.provider_model
        actual_model = $actualModel
        candidate_count = $candidateCount
        scored_count = $score.scored_count
        recommended_count = $score.strong_recommendation_count
        good_count = $score.good_recommendation_count
        other_count = @($score.borderline_candidates).Count
        clip_count = $clips.Count
        bait_reported = $reported
        bait_verified = $verified
        bait_rejected = $rejected
        first_clip_start = if ($clips.Count) { $clips[0].start } else { $null }
        first_clip_end = if ($clips.Count) { $clips[0].end } else { $null }
        output_tail = @($output | Select-Object -Last 12)
    } | ConvertTo-Json -Compress
    exit $exitCode
}
finally {
    if ($backupReady) {
        if (Test-Path -LiteralPath $ownerJob) {
            Remove-Item -LiteralPath $ownerJob -Recurse -Force
        }
        New-Item -ItemType Directory -Force (Split-Path -Parent $ownerJob) | Out-Null
        Copy-Item -LiteralPath $backupJob -Destination $ownerJob -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $backupRoot 'db.sqlite3') -Destination (Join-Path $clipgaugeRoot 'db.sqlite3') -Force
    }
    Remove-Item -LiteralPath $backupRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($null -eq $previousHome) { Remove-Item Env:CLIPGAUGE_HOME -ErrorAction SilentlyContinue } else { $env:CLIPGAUGE_HOME = $previousHome }
    if ($null -eq $previousPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $previousPath }
    if ($null -eq $previousKey) { Remove-Item "Env:$providerEnv" -ErrorAction SilentlyContinue } else { Set-Item -Path "Env:$providerEnv" -Value $previousKey }
}
