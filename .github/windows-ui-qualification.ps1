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

function Validate-Image {
  param([Parameter(Mandatory = $true)] [string] $Path, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height)
  Add-Type -AssemblyName System.Drawing
  $bmp = [System.Drawing.Bitmap]::new($Path)
  try {
    if ($bmp.Width -ne $Width -or $bmp.Height -ne $Height) { throw "wrong screenshot dimensions for ${Path}: $($bmp.Width)x$($bmp.Height), expected ${Width}x${Height}" }
    $colors = New-Object 'System.Collections.Generic.HashSet[int]'
    $sampled = 0
    for ($y = 0; $y -lt $bmp.Height; $y += [Math]::Max(1, [int]($bmp.Height / 64))) {
      for ($x = 0; $x -lt $bmp.Width; $x += [Math]::Max(1, [int]($bmp.Width / 64))) {
        [void]$colors.Add($bmp.GetPixel($x, $y).ToArgb())
        $sampled++
      }
    }
    if ($colors.Count -lt 8) { throw "screenshot is blank or near-uniform: $Path" }
  } finally { $bmp.Dispose() }
}

function Hash-File([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Size-Window([int] $Width, [int] $Height) {
  Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ClipGaugeWindowSize {
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
  [ClipGaugeWindowSize]::MoveWindow([IntPtr]$proc.MainWindowHandle, 0, 0, $Width, $Height, $true) | Out-Null
  [ClipGaugeWindowSize]::SetForegroundWindow([IntPtr]$proc.MainWindowHandle) | Out-Null
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
  $args = @('.github/windows-ui-qualification.mjs', '--state', $State, '--suffix', $Suffix, '--output', $OutputDir, '--hwnd', "$($proc.MainWindowHandle.ToInt64())", '--sentinel', $Sentinel, '--port', '9222')
  & node @args
  if ($LASTEXITCODE -ne 0) { throw "semantic state qualification failed: $State $Suffix" }
  $capture = Invoke-WindowCapture "$State-$Suffix"
  Validate-Image $capture $Width $Height
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
