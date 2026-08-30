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
$qualificationRunId = [Guid]::NewGuid().ToString('N')
$qualificationService = "io.github.pavithranra.clipgauge.qualification.$qualificationRunId"
$qaPort = 9222
while (Get-NetTCPConnection -LocalPort $qaPort -State Listen -ErrorAction SilentlyContinue) { $qaPort += 1 }

function Remove-QualificationCredential {
  param([Parameter(Mandatory = $true)] [string] $Account)
  $target = "$Account.$qualificationService"
  & cmdkey.exe "/delete:$target" | Out-Null
  if ($LASTEXITCODE -notin @(0, 1)) { throw "qualification credential cleanup failed: $target ($LASTEXITCODE)" }
}

function Seed-HostileSessions {
  $jobs = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.clipgauge\jobs'
  New-Item -ItemType Directory -Force $jobs | Out-Null
  $records = @(
    @{ id = '20990830-120001-a1b2c3'; title = 'How I Tricked The Internet - MrBeast 2' },
    @{ id = '20990830-120002-d4e5f6'; title = 'Unicode session title for containment' }
  )
  foreach ($record in $records) {
    $dir = Join-Path $jobs $record.id
    New-Item -ItemType Directory -Force $dir | Out-Null
    $payload = @{ stage = 'ingest'; schema_version = 1; created_at = 0; data = @{ title = $record.title } } | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText((Join-Path $dir 'ingest.json'), $payload, [Text.UTF8Encoding]::new($false))
  }
}

function Remove-HostileSessions {
  $jobs = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.clipgauge\jobs'
  foreach ($id in @('20990830-120001-a1b2c3', '20990830-120002-d4e5f6', '20260825-120001-a1b2c3', '20260825-120002-d4e5f6')) {
    $path = Join-Path $jobs $id
    if (Test-Path -LiteralPath $path) { [IO.Directory]::Delete($path, $true) }
  }
}

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
  $ownerFacts = Get-ImageFacts $OwnerPath
  if (-not $ownerFacts.nonuniform) { throw "owner screenshot is blank or near-uniform: $OwnerPath" }
  $dialogFacts = Get-ImageFacts $dialogPath
  if ($dialogFacts.width -le 0 -or $dialogFacts.height -le 0 -or $dialogFacts.width -gt 4096 -or $dialogFacts.height -gt 4096) { throw "native dialog screenshot dimensions are implausible: $($dialogFacts.width)x$($dialogFacts.height)" }
  if (-not $dialogFacts.nonuniform) { throw "native dialog screenshot is blank or near-uniform: $dialogPath" }
  if ($dialogFacts.sha256 -eq $ownerFacts.sha256) { throw "native dialog screenshot unexpectedly matches owner screenshot: $dialogPath" }
  if (-not (Test-Path -LiteralPath $metadataPath)) { throw "native dialog metadata missing: $metadataPath" }
  $metadata = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
  if ($metadata.provider -ne 'OpenRouter Free') { throw "native dialog provider target mismatch: $metadataPath" }
  if ($metadata.target_viewport.width -ne $Width -or $metadata.target_viewport.height -ne $Height) { throw "native dialog metadata target viewport mismatch: $metadataPath" }
  if ($metadata.owner_screenshot -ne [System.IO.Path]::GetFileName($OwnerPath)) { throw "owner screenshot metadata mismatch: $metadataPath" }
  if ($metadata.native_dialog_screenshot -ne [System.IO.Path]::GetFileName($dialogPath)) { throw "native dialog screenshot metadata mismatch: $metadataPath" }
  if ($metadata.dialog_pid -ne "$($proc.Id)" -or -not $metadata.pid_matches_app) { throw "native dialog PID ownership mismatch: $metadataPath" }
  if ([string]$metadata.dialog_hwnd -notmatch '^\d+$' -or $metadata.class_name -ne '#32770' -or $metadata.title -ne 'ClipGauge') { throw "native dialog identity mismatch: $metadataPath" }
  if ($metadata.content_text_read_method -ne 'winapp-ui-get-value-json' -or -not $metadata.content_text_nonempty -or -not $metadata.expected_provider_observed -or -not $metadata.non_revocation_phrase_observed -or -not $metadata.ok_control_observed -or -not $metadata.cancel_control_observed) { throw "native dialog machine-readable UIA evidence incomplete: $metadataPath" }
  if (-not $metadata.confirmation_accepted -or -not $metadata.dialog_closed -or -not $metadata.post_removal_not_configured) { throw "native dialog semantic evidence incomplete: $metadataPath" }
  if ($metadata.owner_sha256 -and $metadata.owner_sha256 -ne $ownerFacts.sha256) { throw "owner screenshot hash metadata mismatch: $metadataPath" }
  if ($metadata.native_dialog_sha256 -and $metadata.native_dialog_sha256 -ne $dialogFacts.sha256) { throw "native dialog hash metadata mismatch: $metadataPath" }
  $contractPath = Join-Path $PSScriptRoot 'windows-ui-evidence-contract.mjs'
  $contractInput = [ordered]@{ provisional = $metadata; ownerFacts = $ownerFacts; dialogFacts = $dialogFacts } | ConvertTo-Json -Depth 20 -Compress
  $evidenceJson = $contractInput | node $contractPath --finalize
  if ($LASTEXITCODE -ne 0 -or -not $evidenceJson) { throw "native dialog evidence finalization failed: $metadataPath" }
  $evidenceJson | Set-Content -LiteralPath $metadataPath -Encoding utf8
  Write-Host "NATIVE_DIALOG_EVIDENCE_PASS $metadataPath $($dialogFacts.width)x$($dialogFacts.height) $($dialogFacts.sha256)"
}

function Hash-File([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ClipGaugeNativeDisplay {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left; public int Top; public int Right; public int Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct Point { public int X; public int Y; }
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] public struct MonitorInfo {
    public int cbSize;
    public Rect rcMonitor;
    public Rect rcWork;
    public uint dwFlags;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szDevice;
  }
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr dpiContext);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out Rect rect);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref Point point);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr MonitorFromWindow(IntPtr hWnd, uint flags);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool GetMonitorInfo(IntPtr hMonitor, ref MonitorInfo info);
  [DllImport("user32.dll")] public static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern int GetAwarenessFromDpiAwarenessContext(IntPtr value);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hWnd, uint attribute, out Rect value, int size);
}

"@
function Convert-NativeRect($Rect) {
  return [ordered]@{
    left = [int]$Rect.Left
    top = [int]$Rect.Top
    right = [int]$Rect.Right
    bottom = [int]$Rect.Bottom
    width = [int]($Rect.Right - $Rect.Left)
    height = [int]($Rect.Bottom - $Rect.Top)
  }
}

function Get-DpiAwarenessLabel([int] $Value) {
  switch ($Value) {
    0 { return 'unaware' }
    1 { return 'system' }
    2 { return 'per-monitor' }
    default { return 'invalid' }
  }
}

function Get-NativeWindowFacts([IntPtr] $Handle) {
  [ClipGaugeNativeDisplay]::SetThreadDpiAwarenessContext([IntPtr](-4)) | Out-Null
  $window = New-Object ClipGaugeNativeDisplay+Rect
  $client = New-Object ClipGaugeNativeDisplay+Rect
  $origin = New-Object ClipGaugeNativeDisplay+Point
  $extended = New-Object ClipGaugeNativeDisplay+Rect
  $monitorInfo = New-Object ClipGaugeNativeDisplay+MonitorInfo
  $monitorInfo.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($monitorInfo)
  if (-not [ClipGaugeNativeDisplay]::GetWindowRect($Handle, [ref]$window)) { throw 'GetWindowRect failed' }
  if (-not [ClipGaugeNativeDisplay]::GetClientRect($Handle, [ref]$client)) { throw 'GetClientRect failed' }
  if (-not [ClipGaugeNativeDisplay]::ClientToScreen($Handle, [ref]$origin)) { throw 'ClientToScreen failed' }
  $monitor = [ClipGaugeNativeDisplay]::MonitorFromWindow($Handle, 2)
  if ($monitor -eq [IntPtr]::Zero -or -not [ClipGaugeNativeDisplay]::GetMonitorInfo($monitor, [ref]$monitorInfo)) { throw 'GetMonitorInfo failed' }
  $dwmResult = [ClipGaugeNativeDisplay]::DwmGetWindowAttribute($Handle, 9, [ref]$extended, [Runtime.InteropServices.Marshal]::SizeOf($extended))
  if ($dwmResult -ne 0) { $extended = $window }
  $dpi = [ClipGaugeNativeDisplay]::GetDpiForWindow($Handle)
  $awareness = [ClipGaugeNativeDisplay]::GetAwarenessFromDpiAwarenessContext([ClipGaugeNativeDisplay]::GetWindowDpiAwarenessContext($Handle))
  return [ordered]@{
    dpi_for_window = [int]$dpi
    dpi_awareness = Get-DpiAwarenessLabel $awareness
    dpi_awareness_value = [int]$awareness
    window_rect = Convert-NativeRect $window
    native_client_rect = Convert-NativeRect $client
    client_origin_screen = [ordered]@{ x = [int]$origin.X; y = [int]$origin.Y }
    dwm_extended_frame_bounds = Convert-NativeRect $extended
    monitor_physical_rect = Convert-NativeRect $monitorInfo.rcMonitor
    monitor_work_area = Convert-NativeRect $monitorInfo.rcWork
  }
}

function Set-LogicalWindowSize {
  param([Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height)
  $handle = [IntPtr]::Zero
  $facts = $null
  $readyDeadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $readyDeadline) {
    $proc.Refresh()
    $handle = [IntPtr]$proc.MainWindowHandle
    if ($handle -eq [IntPtr]::Zero) {
      Start-Sleep -Milliseconds 250
      continue
    }
    try { $facts = Get-NativeWindowFacts $handle } catch { $facts = $null }
    if ($facts -and $facts.native_client_rect.width -gt 0 -and $facts.native_client_rect.height -gt 0) { break }
    Start-Sleep -Milliseconds 250
  }
  if (-not $facts -or $facts.native_client_rect.width -le 0 -or $facts.native_client_rect.height -le 0) { throw 'native window client geometry never became valid' }
  $scale = $facts.dpi_for_window / 96.0
  $clientWidth = [int][Math]::Floor($Width * $scale)
  $clientHeight = [int][Math]::Floor($Height * $scale)
  $frameWidth = $facts.window_rect.width - $facts.native_client_rect.width
  $frameHeight = $facts.window_rect.height - $facts.native_client_rect.height
  Write-Host "NATIVE_RESIZE_BASE window=$($facts.window_rect.width)x$($facts.window_rect.height) client=$($facts.native_client_rect.width)x$($facts.native_client_rect.height) frame=${frameWidth}x${frameHeight}"
  $outerWidth = $clientWidth + $frameWidth
  $outerHeight = $clientHeight + $frameHeight
  $observed = $null
  for ($attempt = 1; $attempt -le 8; $attempt++) {
    if (-not [ClipGaugeNativeDisplay]::MoveWindow($handle, $facts.window_rect.left, $facts.window_rect.top, $outerWidth, $outerHeight, $true)) { throw 'native logical resize failed' }
    [ClipGaugeNativeDisplay]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 750
    $observed = Get-NativeWindowFacts $handle
    if ($observed.native_client_rect.width -eq $clientWidth -and $observed.native_client_rect.height -eq $clientHeight) { break }
  }
  if ($observed.native_client_rect.width -ne $clientWidth -or $observed.native_client_rect.height -ne $clientHeight) {
    throw "native logical resize did not settle: requested ${clientWidth}x${clientHeight}, observed $($observed.native_client_rect.width)x$($observed.native_client_rect.height)"
  }
  Write-Host "LOGICAL_SIZE_REQUEST ${Width}x${Height} client_target=${clientWidth}x${clientHeight} scale=$scale observed=$($observed.native_client_rect.width)x$($observed.native_client_rect.height)"
}

function Invoke-ClientCapture {
  param([Parameter(Mandatory = $true)] [string] $Name)
  Add-Type -AssemblyName System.Drawing
  $facts = Get-NativeWindowFacts ([IntPtr]$proc.MainWindowHandle)
  $width = $facts.native_client_rect.width
  $height = $facts.native_client_rect.height
  if ($width -le 0 -or $height -le 0) { throw "native client size is invalid: ${width}x${height}" }
  $path = Join-Path $OutputDir "$Name.png"
  Remove-Item -Force -ErrorAction SilentlyContinue $path
  $bitmap = [System.Drawing.Bitmap]::new($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $origin = $facts.client_origin_screen
    $graphics.CopyFromScreen([int]$origin.x, [int]$origin.y, 0, 0, $bitmap.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
  }
  if (-not (Test-Path -LiteralPath $path)) { throw "client screenshot failed: $Name" }
  return $path
}

function Validate-DisplayEvidence {
  param([Parameter(Mandatory = $true)] [string] $State, [Parameter(Mandatory = $true)] [string] $Suffix, [Parameter(Mandatory = $true)] [string] $ClientPath)
  $displayPath = Join-Path $OutputDir "display-$State-$Suffix.json"
  if (-not (Test-Path -LiteralPath $displayPath)) { throw "display facts missing: $displayPath" }
  $facts = Get-Content -Raw -LiteralPath $displayPath | ConvertFrom-Json
  $native = Get-NativeWindowFacts ([IntPtr]$proc.MainWindowHandle)
  foreach ($property in $native.Keys) { $facts | Add-Member -MemberType NoteProperty -Name $property -Value $native[$property] -Force }
  $captureFacts = Get-ImageFacts $ClientPath
  $facts | Add-Member -MemberType NoteProperty -Name client_capture -Value ([ordered]@{ width = $captureFacts.width; height = $captureFacts.height; sha256 = $captureFacts.sha256 }) -Force
  $json = $facts | ConvertTo-Json -Depth 30
  $json | Set-Content -LiteralPath $displayPath -Encoding utf8
  $contractPath = Join-Path $PSScriptRoot 'windows-ui-dpi-contract.mjs'
  $contractResult = $json | node $contractPath --validate
  if ($LASTEXITCODE -ne 0 -or -not $contractResult) { throw "display contract failed: $displayPath $contractResult" }
  Write-Host "DISPLAY_EVIDENCE_PASS $displayPath client=$($captureFacts.width)x$($captureFacts.height) dpi=$($native.dpi_for_window) awareness=$($native.dpi_awareness)"
}

$cdp = Join-Path $OutputDir 'webview2-cdp'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $cdp
New-Item -ItemType Directory -Force $cdp | Out-Null
$env:CLIPGAUGE_QA_WEBVIEW2_CDP = '1'
$env:CLIPGAUGE_QUALIFICATION_VAULT_SERVICE = $qualificationService
$env:WEBVIEW2_USER_DATA_FOLDER = $cdp
$env:CLIPGAUGE_QA_WEBVIEW2_PORT = "$qaPort"
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$qaPort"
$chocoRoot = if ($env:ChocolateyInstall) { $env:ChocolateyInstall } else { 'C:\ProgramData\chocolatey' }
$realFfmpeg = Get-ChildItem -Path (Join-Path $chocoRoot 'lib\ffmpeg') -Filter 'ffmpeg.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
$realFfmpegPath = if ($realFfmpeg) { $realFfmpeg.FullName } else { (Get-Command ffmpeg -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path -Parent $realFfmpegPath);$env:PATH"
Write-Host "qualification system FFmpeg: $realFfmpegPath"
Seed-HostileSessions
$proc = Start-Process -FilePath $AppPath -PassThru
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  $proc.Refresh()
  if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { break }
  Start-Sleep -Milliseconds 500
}
$proc.Refresh()
if ($proc.MainWindowHandle -eq [IntPtr]::Zero) { throw 'installed ClipGauge window handle unavailable' }

function Restart-QualificationApp {
  if ($script:proc -and -not $script:proc.HasExited) { Stop-Process -Id $script:proc.Id -Force }
  Start-Sleep -Seconds 2
  $script:proc = Start-Process -FilePath $AppPath -PassThru
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline) {
    $script:proc.Refresh()
    if ($script:proc.MainWindowHandle -ne [IntPtr]::Zero) { break }
    Start-Sleep -Milliseconds 500
  }
  $script:proc.Refresh()
  if ($script:proc.MainWindowHandle -eq [IntPtr]::Zero) { throw 'restarted ClipGauge window handle unavailable' }
  Write-Host "QUALIFICATION_APP_RESTARTED pid=$($script:proc.Id)"
}

function Invoke-State {
  param([Parameter(Mandatory = $true)] [string] $State, [Parameter(Mandatory = $true)] [int] $Width, [Parameter(Mandatory = $true)] [int] $Height, [Parameter(Mandatory = $true)] [string] $Suffix)
  Set-LogicalWindowSize $Width $Height
  $args = @('.github/windows-ui-qualification.mjs', '--state', $State, '--suffix', $Suffix, '--output', $OutputDir, '--hwnd', "$($proc.MainWindowHandle.ToInt64())", '--pid', "$($proc.Id)", '--sentinel', $Sentinel, '--target-width', "$Width", '--target-height', "$Height", '--port', "$qaPort")
  & node @args
  if ($LASTEXITCODE -ne 0) { throw "semantic state qualification failed: $State $Suffix" }
  $capture = Join-Path $OutputDir "$State-$Suffix.png"
  $cdpCapture = Join-Path $OutputDir "$State-$Suffix-cdp.png"
  if (Test-Path -LiteralPath $capture) { Move-Item -LiteralPath $capture -Destination $cdpCapture -Force }
  $clientCapture = Invoke-ClientCapture "$State-$Suffix"
  Validate-DisplayEvidence $State $Suffix $clientCapture
  $fullCapture = Invoke-WindowCapture "$State-$Suffix-full"
  $fullFacts = Get-ImageFacts $fullCapture
  if (-not $fullFacts.nonuniform) { throw "full-window screenshot is blank or near-uniform: $fullCapture" }
  if ($State -eq 'credential-removal-confirmation') {
    Validate-NativeDialogEvidence $State $Suffix $Width $Height $clientCapture
  }
}

try {
  Invoke-State 'setup' 1366 768 '1366x768'
  Invoke-State 'local-ai' 1366 768 '1366x768'
  Invoke-State 'providers' 1366 768 '1366x768'
  Invoke-State 'openrouter-saved' 1366 768 '1366x768'
  Invoke-State 'openrouter-connected' 1366 768 '1366x768'
  Restart-QualificationApp
  Invoke-State 'openrouter-connected' 1366 768 '1366x768-restart'
  Invoke-State 'gemini-saved-unverified' 1366 768 '1366x768'
  Invoke-State 'credential-removal-confirmation' 1366 768 '1366x768'
  Restart-QualificationApp
  Invoke-State 'openrouter-remove' 1366 768 '1366x768-remove-restart'
  Invoke-State 'setup' 1920 1080 '1920x1080'
  Invoke-State 'local-ai' 1920 1080 '1920x1080'
  Invoke-State 'providers' 1920 1080 '1920x1080'
  Invoke-State 'openrouter-saved' 1920 1080 '1920x1080'
  Invoke-State 'openrouter-connected' 1920 1080 '1920x1080'
  Invoke-State 'gemini-saved-unverified' 1920 1080 '1920x1080'
  Invoke-State 'credential-removal-confirmation' 1920 1080 '1920x1080'
  Invoke-State 'setup' 1920 1200 '1920x1200'
  Invoke-State 'local-ai' 1920 1200 '1920x1200'
  Invoke-State 'providers' 1920 1200 '1920x1200'
  Invoke-State 'openrouter-saved' 1920 1200 '1920x1200'
  Invoke-State 'openrouter-connected' 1920 1200 '1920x1200'
  Invoke-State 'gemini-saved-unverified' 1920 1200 '1920x1200'
  Invoke-State 'credential-removal-confirmation' 1920 1200 '1920x1200'
  Invoke-State 'create' 1920 1200 '1920x1200'
  Invoke-State 'create-hostile' 1920 1200 '1920x1200'
  Invoke-State 'help' 1920 1200 '1920x1200'
  Invoke-State 'display-diagnostics' 1920 1200 '1920x1200'

  $additionalViewports = @(
    @(1280, 720, '1280x720'),
    @(1440, 900, '1440x900'),
    @(1536, 864, '1536x864'),
    @(1600, 900, '1600x900'),
    @(2560, 1440, '2560x1440'),
    @(3840, 2160, '3840x2160')
  )
  foreach ($viewport in $additionalViewports) {
    Invoke-State 'setup' $viewport[0] $viewport[1] $viewport[2]
    Invoke-State 'local-ai' $viewport[0] $viewport[1] $viewport[2]
    Invoke-State 'providers' $viewport[0] $viewport[1] $viewport[2]
    Invoke-State 'create-hostile' $viewport[0] $viewport[1] $viewport[2]
    Invoke-State 'help' $viewport[0] $viewport[1] $viewport[2]
  }

  $pairs = @(
    @('providers-1366x768-cdp.png', 'local-ai-1366x768-cdp.png'),
    @('providers-1920x1080-cdp.png', 'local-ai-1920x1080-cdp.png'),
    @('openrouter-saved-1366x768-cdp.png', 'openrouter-connected-1366x768-cdp.png'),
    @('openrouter-saved-1920x1080-cdp.png', 'openrouter-connected-1920x1080-cdp.png'),
    @('providers-1920x1200-cdp.png', 'local-ai-1920x1200-cdp.png'),
    @('openrouter-saved-1920x1200-cdp.png', 'openrouter-connected-1920x1200-cdp.png')
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
  Remove-Item Env:CLIPGAUGE_QA_WEBVIEW2_PORT -ErrorAction SilentlyContinue
  Remove-QualificationCredential 'provider_auth_preset-openrouter'
  Remove-QualificationCredential 'gemini_api_key'
  Remove-HostileSessions
  Remove-Item Env:CLIPGAUGE_QUALIFICATION_VAULT_SERVICE -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_USER_DATA_FOLDER -ErrorAction SilentlyContinue
}
