param(
  [Parameter(Mandatory = $true)] [string] $AppPath,
  [Parameter(Mandatory = $true)] [string] $OutputDir,
  [Parameter(Mandatory = $true)] [string] $Sentinel
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$winapp = (Get-Command winapp -ErrorAction Stop).Source
$appName = [System.IO.Path]::GetFileNameWithoutExtension($AppPath)
$proc = Start-Process -FilePath $AppPath -PassThru
$started = Get-Date
while ((Get-Date) -lt $started.AddSeconds(30)) {
  $proc.Refresh()
  if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { break }
  Start-Sleep -Milliseconds 500
}
$proc.Refresh()
if ($proc.MainWindowHandle -eq [IntPtr]::Zero) { throw 'installed ClipGauge window handle unavailable' }
$hwnd = $proc.MainWindowHandle.ToInt64()
Write-Host "ClipGauge process=$($proc.Id) hwnd=$hwnd app=$appName"

function Run-Winapp {
  param([Parameter(Mandatory = $true)] [string[]] $Arguments)
  $output = & $winapp @Arguments 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) {
    Write-Host $output
    throw "winapp failed (exit $LASTEXITCODE): $($Arguments -join ' ')"
  }
  return $output
}

function Wait-UI {
  param([Parameter(Mandatory = $true)] [string] $Selector, [int] $TimeoutMs = 120000)
  Write-Host "wait-for: $Selector"
  Run-Winapp @('ui', 'wait-for', $Selector, '-w', "$hwnd", '--timeout', "$TimeoutMs") | Out-Host
}

function Invoke-UI {
  param([Parameter(Mandatory = $true)] [string] $Selector)
  Write-Host "invoke: $Selector"
  Run-Winapp @('ui', 'invoke', $Selector, '-w', "$hwnd") | Out-Host
}

function Invoke-AnyUI {
  param([Parameter(Mandatory = $true)] [string] $Selector)
  Write-Host "invoke app-wide: $Selector"
  Run-Winapp @('ui', 'invoke', $Selector, '-a', $appName) | Out-Host
}

function Wait-AnyUI {
  param([Parameter(Mandatory = $true)] [string] $Selector, [int] $TimeoutMs = 30000)
  Write-Host "wait-for app-wide: $Selector"
  Run-Winapp @('ui', 'wait-for', $Selector, '-a', $appName, '--timeout', "$TimeoutMs") | Out-Host
}

function Set-UIValue {
  param([Parameter(Mandatory = $true)] [string] $Selector, [Parameter(Mandatory = $true)] [string] $Value)
  Write-Host "set-value: $Selector"
  Run-Winapp @('ui', 'set-value', $Selector, $Value, '-w', "$hwnd") | Out-Host
}

function Scroll-Into-View {
  param([Parameter(Mandatory = $true)] [string] $Selector)
  Write-Host "scroll-into-view: $Selector"
  Run-Winapp @('ui', 'scroll-into-view', $Selector, '-w', "$hwnd") | Out-Host
}

function Capture {
  param([Parameter(Mandatory = $true)] [string] $Name)
  $path = Join-Path $OutputDir "$Name.png"
  Write-Host "screenshot: $path"
  Run-Winapp @('ui', 'screenshot', '-w', "$hwnd", '--output', $path) | Out-Host
  if (-not (Test-Path $path)) { throw "screenshot missing: $path" }
  return $path
}

function Inspect-UI {
  param([Parameter(Mandatory = $true)] [string] $Name)
  $path = Join-Path $OutputDir "$Name-ui.txt"
  Run-Winapp @('ui', 'inspect', '-w', "$hwnd", '--depth', '12') | Tee-Object -FilePath $path | Out-Host
  return $path
}

function Validate-Image {
  param([Parameter(Mandatory = $true)] [string] $Path, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height)
  Add-Type -AssemblyName System.Drawing
  $bmp = [System.Drawing.Bitmap]::new($Path)
  try {
    if ($bmp.Width -ne $Width -or $bmp.Height -ne $Height) { throw "wrong screenshot dimensions for ${Path}: $($bmp.Width)x$($bmp.Height), expected ${Width}x${Height}" }
    $counts = @{}
    $sampled = 0
    for ($y = 0; $y -lt $bmp.Height; $y += [Math]::Max(1, [int]($bmp.Height / 64))) {
      for ($x = 0; $x -lt $bmp.Width; $x += [Math]::Max(1, [int]($bmp.Width / 64))) {
        $key = $bmp.GetPixel($x, $y).ToArgb().ToString()
        if (-not $counts.ContainsKey($key)) { $counts[$key] = 0 }
        $counts[$key]++
        $sampled++
      }
    }
    if ($counts.Count -lt 8) { throw "screenshot is blank or near-uniform: $Path" }
    $dominant = ($counts.Values | Measure-Object -Maximum).Maximum
    if (($dominant / [double]$sampled) -gt 0.985) { throw "screenshot is near-uniform: $Path" }
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
  [ClipGaugeWindowSize]::MoveWindow([IntPtr]$hwnd, 0, 0, $Width, $Height, $true) | Out-Null
  [ClipGaugeWindowSize]::SetForegroundWindow([IntPtr]$hwnd) | Out-Null
  Start-Sleep -Seconds 2
}

function Reset-To-Top { Run-Winapp @('ui', 'scroll', 'Setup & Storage', '--to', 'top', '-w', "$hwnd") | Out-Host }

function Capture-Resolution([int] $Width, [int] $Height, [string] $Suffix) {
  Size-Window $Width $Height
  Inspect-UI "initial-$Suffix"

  Invoke-UI 'Setup & Storage'
  Wait-UI 'Setup & Storage'
  Wait-UI 'Ready to create clips'
  Wait-UI 'Ready · System'
  Wait-UI 'System component reused'
  $setup = Capture "setup-$Suffix"
  Validate-Image $setup $Width $Height
  Inspect-UI "setup-$Suffix"

  Scroll-Into-View 'Install ClipGauge Local'
  Wait-UI 'Run scoring locally'
  Wait-UI 'Install ClipGauge Local'
  $local = Capture "local-ai-$Suffix"
  Validate-Image $local $Width $Height
  Inspect-UI "local-ai-$Suffix"

  Invoke-UI 'AI Providers'
  Wait-UI 'AI Providers'
  Wait-UI 'OpenRouter Free'
  Wait-UI 'Not configured'
  $baseline = Capture "providers-$Suffix"
  Validate-Image $baseline $Width $Height
  Inspect-UI "providers-$Suffix"

  Invoke-UI 'OpenRouter Free'
  Wait-UI 'OpenRouter Free'
  Set-UIValue 'API key' $Sentinel
  Invoke-UI 'Save'
  Wait-UI 'Credential saved'
  $saved = Capture "openrouter-saved-$Suffix"
  Validate-Image $saved $Width $Height
  Inspect-UI "openrouter-saved-$Suffix"

  Invoke-UI 'Test connection'
  Wait-UI 'Connected'
  $connected = Capture "openrouter-connected-$Suffix"
  Validate-Image $connected $Width $Height
  Inspect-UI "openrouter-connected-$Suffix"

  Invoke-UI 'Gemini'
  Wait-UI 'Gemini'
  Set-UIValue 'API key' $Sentinel
  Invoke-UI 'Save'
  Wait-UI 'Credential saved'
  $gemini = Capture "gemini-saved-unverified-$Suffix"
  Validate-Image $gemini $Width $Height
  Inspect-UI "gemini-saved-unverified-$Suffix"

  Invoke-UI 'Remove'
  Wait-UI 'does not revoke the provider key'
  $removal = Capture "credential-removal-confirmation-$Suffix"
  Validate-Image $removal $Width $Height
  Inspect-UI "credential-removal-confirmation-$Suffix"
  Invoke-AnyUI 'OK'
  Wait-UI 'Not configured'

  Invoke-UI 'OpenRouter Free'
  Wait-UI 'OpenRouter Free'
  Invoke-UI 'Remove'
  Wait-AnyUI 'does not revoke the provider key'
  Invoke-AnyUI 'OK'
  Wait-UI 'Not configured'

  [pscustomobject]@{
    setup = (Hash-File $setup)
    local = (Hash-File $local)
    baseline = (Hash-File $baseline)
    saved = (Hash-File $saved)
    connected = (Hash-File $connected)
    gemini = (Hash-File $gemini)
    removal = (Hash-File $removal)
  } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $OutputDir "hashes-$Suffix.json")
}

try {
  Capture-Resolution 1366 768 '1366x768'
  if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) { throw 'ClipGauge exited before second resolution' }
  Capture-Resolution 1920 1080 '1920x1080'

  $pairs = @(
    @('providers-1366x768.png', 'local-ai-1366x768.png'),
    @('providers-1920x1080.png', 'local-ai-1920x1080.png'),
    @('openrouter-saved-1366x768.png', 'openrouter-connected-1366x768.png'),
    @('openrouter-saved-1920x1080.png', 'openrouter-connected-1920x1080.png')
  )
  foreach ($pair in $pairs) {
    $left = Hash-File (Join-Path $OutputDir $pair[0])
    $right = Hash-File (Join-Path $OutputDir $pair[1])
    if ($left -eq $right) { throw "screenshots unexpectedly identical: $($pair -join ' == ')" }
  }
  $sentinelHit = Get-ChildItem -LiteralPath $OutputDir -Recurse -File | Where-Object { Select-String -LiteralPath $_.FullName -Pattern $Sentinel -SimpleMatch -Quiet -ErrorAction SilentlyContinue } | Select-Object -First 1
  if ($sentinelHit) { throw "sentinel appeared in evidence artifact: $($sentinelHit.FullName)" }
  Get-ChildItem -LiteralPath $OutputDir -Filter '*.png' | ForEach-Object { Write-Host "$($_.Name) $(Hash-File $_.FullName) $($_.Length) bytes" }
  Write-Host 'WINDOWS_UI_QUALIFICATION=PASS'
} finally {
  if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $proc.Id -Force }
}
