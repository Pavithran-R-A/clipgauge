param(
  [Parameter(Mandatory = $true)] [string] $AppPath,
  [Parameter(Mandatory = $true)] [string] $OutputDir,
  [Parameter(Mandatory = $true)] [string] $Sentinel
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$winapp = (Get-Command winapp -ErrorAction Stop).Source
$appName = [System.IO.Path]::GetFileNameWithoutExtension($AppPath)
$proc = $null

function Invoke-WindowCapture {
  param([Parameter(Mandatory = $true)] [string] $Name)
  $path = Join-Path $OutputDir "$Name.png"
  & $winapp ui screenshot -w "$($proc.MainWindowHandle.ToInt64())" --output $path | Out-Host
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $path)) { throw "native screenshot failed: $Name" }
  return $path
}

function Get-ImageFacts {
  param([Parameter(Mandatory = $true)] [string] $Path)
  if (-not (Test-Path -LiteralPath $Path)) { throw "screenshot missing: $Path" }
  Add-Type -AssemblyName System.Drawing
  $bmp = [System.Drawing.Bitmap]::new($Path)
  try {
    $colors = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($y = 0; $y -lt $bmp.Height; $y += [Math]::Max(1, [int]($bmp.Height / 64))) {
      for ($x = 0; $x -lt $bmp.Width; $x += [Math]::Max(1, [int]($bmp.Width / 64))) {
        [void]$colors.Add($bmp.GetPixel($x, $y).ToArgb())
      }
    }
    return [ordered]@{
      path = [System.IO.Path]::GetFileName($Path)
      width = $bmp.Width
      height = $bmp.Height
      sha256 = Hash-File $Path
      sampled_colors = $colors.Count
      nonuniform = ($colors.Count -ge 8)
    }
  } finally { $bmp.Dispose() }
}

function Validate-Image {
  param([Parameter(Mandatory = $true)] [string] $Path, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height)
  $facts = Get-ImageFacts $Path
  if ($facts.width -ne $Width -or $facts.height -ne $Height) { throw "wrong screenshot dimensions for ${Path}: $($facts.width)x$($facts.height), expected ${Width}x${Height}" }
  if (-not $facts.nonuniform) { throw "screenshot is blank or near-uniform: $Path" }
  return $facts
}

function Validate-NativeDialogEvidence {
  param([Parameter(Mandatory = $true)] [string] $State, [Parameter(Mandatory = $true)] [string] $Suffix, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height, [Parameter(Mandatory = $true)] [string] $OwnerPath)
  $dialogPath = Join-Path $OutputDir "$State-dialog-$Suffix.png"
  $metadataPath = Join-Path $OutputDir "$State-$Suffix.json"
  $ownerFacts = Validate-Image $OwnerPath $Width $Height
  $dialogFacts = Get-ImageFacts $dialogPath
  if ($dialogFacts.width -le 0 -or $dialogFacts.height -le 0 -or $dialogFacts.width -gt 4096 -or $dialogFacts.height -gt 4096) { throw "native dialog screenshot dimensions are implausible: $($dialogFacts.width)x$($dialogFacts.height)" }
  if (-not $dialogFacts.nonuniform) { throw "native dialog screenshot is blank or near-uniform: $dialogPath" }
  if ($dialogFacts.sha256 -eq $ownerFacts.sha256) { throw "native dialog screenshot unexpectedly matches owner screenshot: $dialogPath" }
  if (-not (Test-Path -LiteralPath $metadataPath)) { throw "native dialog metadata missing: $metadataPath" }
  $metadata = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
  if ($metadata.target_viewport.width -ne $Width -or $metadata.target_viewport.height -ne $Height) { throw "native dialog metadata target viewport mismatch: $metadataPath" }
  if ($metadata.native_dialog.pid -ne "$($proc.Id)" -or -not $metadata.native_dialog.pid_matches_app) { throw "native dialog PID ownership mismatch: $metadataPath" }
  if ($metadata.native_dialog.class_name -ne '#32770' -or $metadata.native_dialog.title -ne 'ClipGauge') { throw "native dialog class/title mismatch: $metadataPath" }
  if (-not $metadata.native_dialog.ui_automation_inspected -or -not $metadata.native_dialog.controls_observed -or -not $metadata.native_dialog.message_text_observed) { throw "native dialog UIA evidence incomplete: $metadataPath" }
  if (-not $metadata.semantic.remove_clicked -or -not $metadata.semantic.confirmation_accepted -or -not $metadata.semantic.dialog_closed -or -not $metadata.semantic.post_removal_not_configured) { throw "native dialog semantic evidence incomplete: $metadataPath" }
  $evidence = [ordered]@{
    target_viewport = [ordered]@{ width = $Width; height = $Height }
    owner = $ownerFacts
    native_dialog = [ordered]@{ image = $dialogFacts; hwnd = [string]$metadata.native_dialog.hwnd; pid = [string]$metadata.native_dialog.pid; pid_matches_app = [bool]$metadata.native_dialog.pid_matches_app; class_name = [string]$metadata.native_dialog.class_name; title = [string]$metadata.native_dialog.title; ui_automation_inspected = [bool]$metadata.native_dialog.ui_automation_inspected; controls_observed = [bool]$metadata.native_dialog.controls_observed; message_text_observed = [bool]$metadata.native_dialog.message_text_observed; ui_automation_excerpt = [string]$metadata.native_dialog.ui_automation_excerpt }
    semantic = $metadata.semantic
  }
  $evidence | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $metadataPath -Encoding utf8
  Write-Host "NATIVE_DIALOG_EVIDENCE_PASS $metadataPath $($dialogFacts.width)x$($dialogFacts.height) $($dialogFacts.sha256)"
}

function Hash-File([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Size-Window([int] $Width, [int] $Height) {
  Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ClipGaugeWindowSize {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
}
"@
  $handle = [IntPtr]$proc.MainWindowHandle
  $probe = Join-Path $OutputDir '.window-size-probe.png'
  $windowWidth = $Width
  $windowHeight = $Height
  for ($attempt = 1; $attempt -le 4; $attempt++) {
    [ClipGaugeWindowSize]::MoveWindow($handle, 0, 0, $windowWidth, $windowHeight, $true) | Out-Null
    [ClipGaugeWindowSize]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 700
    Remove-Item -Force -ErrorAction SilentlyContinue $probe
    & $winapp ui screenshot -w "$($handle.ToInt64())" --output $probe | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $probe)) { continue }
    Add-Type -AssemblyName System.Drawing
    $bmp = [System.Drawing.Bitmap]::new($probe)
    try {
      $actualWidth = $bmp.Width
      $actualHeight = $bmp.Height
    } finally { $bmp.Dispose() }
    if ($actualWidth -eq $Width -and $actualHeight -eq $Height) { break }
    $windowWidth += $Width - $actualWidth
    $windowHeight += $Height - $actualHeight
  }
  Remove-Item -Force -ErrorAction SilentlyContinue $probe
  [ClipGaugeWindowSize]::SetForegroundWindow($handle) | Out-Null
  Start-Sleep -Milliseconds 500
}

$cdp = Join-Path $OutputDir 'webview2-cdp'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $cdp
New-Item -ItemType Directory -Force $cdp | Out-Null
$env:CLIPGAUGE_QA_WEBVIEW2_CDP = '1'
$env:WEBVIEW2_USER_DATA_FOLDER = $cdp
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=9222"
$chocoRoot = if ($env:ChocolateyInstall) { $env:ChocolateyInstall } else { 'C:\ProgramData\chocolatey' }
$realFfmpeg = Get-ChildItem -Path (Join-Path $chocoRoot 'lib\ffmpeg') -Filter 'ffmpeg.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
$realFfmpegPath = if ($realFfmpeg) { $realFfmpeg.FullName } else { (Get-Command ffmpeg -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path -Parent $realFfmpegPath);$env:PATH"
Write-Host "qualification system FFmpeg: $realFfmpegPath"
$proc = Start-Process -FilePath $AppPath -PassThru
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  $proc.Refresh()
  if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { break }
  Start-Sleep -Milliseconds 500
}
$proc.Refresh()
if ($proc.MainWindowHandle -eq [IntPtr]::Zero) { throw 'installed ClipGauge window handle unavailable' }

function Invoke-State {
  param([Parameter(Mandatory = $true)] [string] $State, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height, [Parameter(Mandatory = $true)] [string] $Suffix)
  Size-Window $Width $Height
  $args = @('.github/windows-ui-qualification.mjs', '--state', $State, '--suffix', $Suffix, '--output', $OutputDir, '--hwnd', "$($proc.MainWindowHandle.ToInt64())", '--pid', "$($proc.Id)", '--sentinel', $Sentinel, '--target-width', "$Width", '--target-height', "$Height", '--port', '9222')
  & node @args
  if ($LASTEXITCODE -ne 0) { throw "semantic state qualification failed: $State $Suffix" }
  $capture = Join-Path $OutputDir "$State-$Suffix.png"
  if ($State -ne 'credential-removal-confirmation') {
    $capture = Invoke-WindowCapture "$State-$Suffix"
  }
  Validate-Image $capture $Width $Height
  if ($State -eq 'credential-removal-confirmation') {
    Validate-NativeDialogEvidence $State $Suffix $Width $Height $capture
  }
}

try {
  Invoke-State 'setup' 1366 768 '1366x768'
  Invoke-State 'local-ai' 1366 768 '1366x768'
  Invoke-State 'providers' 1366 768 '1366x768'
  Invoke-State 'openrouter-saved' 1366 768 '1366x768'
  Invoke-State 'openrouter-connected' 1366 768 '1366x768'
  Invoke-State 'gemini-saved-unverified' 1366 768 '1366x768'
  Invoke-State 'credential-removal-confirmation' 1366 768 '1366x768'
  Invoke-State 'setup' 1920 1080 '1920x1080'
  Invoke-State 'local-ai' 1920 1080 '1920x1080'
  Invoke-State 'providers' 1920 1080 '1920x1080'
  Invoke-State 'openrouter-saved' 1920 1080 '1920x1080'
  Invoke-State 'openrouter-connected' 1920 1080 '1920x1080'
  Invoke-State 'gemini-saved-unverified' 1920 1080 '1920x1080'
  Invoke-State 'credential-removal-confirmation' 1920 1080 '1920x1080'

  $pairs = @(
    @('providers-1366x768.png', 'local-ai-1366x768.png'),
    @('providers-1920x1080.png', 'local-ai-1920x1080.png'),
    @('openrouter-saved-1366x768.png', 'openrouter-connected-1366x768.png'),
    @('openrouter-saved-1920x1080.png', 'openrouter-connected-1920x1080.png')
  )
  foreach ($pair in $pairs) {
    if ((Hash-File (Join-Path $OutputDir $pair[0])) -eq (Hash-File (Join-Path $OutputDir $pair[1]))) { throw "screenshots unexpectedly identical: $($pair -join ' == ')" }
  }
  $sentinelHit = Get-ChildItem -LiteralPath $OutputDir -Recurse -File | Where-Object { Select-String -LiteralPath $_.FullName -Pattern $Sentinel -SimpleMatch -Quiet -ErrorAction SilentlyContinue } | Select-Object -First 1
  if ($sentinelHit) { throw "sentinel appeared in evidence artifact: $($sentinelHit.FullName)" }
  Get-ChildItem -LiteralPath $OutputDir -Filter '*.png' | ForEach-Object { Write-Host "$($_.Name) $(Hash-File $_.FullName) $($_.Length) bytes" }
  Write-Host 'WINDOWS_UI_QUALIFICATION=PASS'
} finally {
  if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
  Remove-Item Env:CLIPGAUGE_QA_WEBVIEW2_CDP -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_USER_DATA_FOLDER -ErrorAction SilentlyContinue
}
