param(
  [Parameter(Mandatory = $true)] [string] $AppPath,
  [Parameter(Mandatory = $true)] [string] $OutputDir,
  [Parameter(Mandatory = $true)] [string] $Fixture,
  [int] $Port = 9237
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$cdp = Join-Path $OutputDir 'webview2-cdp'
New-Item -ItemType Directory -Force $cdp | Out-Null
$env:CLIPGAUGE_QA_WEBVIEW2_CDP = '1'
$env:WEBVIEW2_USER_DATA_FOLDER = $cdp
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
$proc = Start-Process -FilePath $AppPath -PassThru
try {
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline) {
    $proc.Refresh()
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { break }
    Start-Sleep -Milliseconds 500
  }
  $proc.Refresh()
  if ($proc.MainWindowHandle -eq [IntPtr]::Zero) { throw 'lifecycle app window unavailable' }
  & node (Join-Path $PSScriptRoot 'windows-ui-creator-lifecycle.mjs') --port "$Port" --output (Join-Path $OutputDir 'lifecycle.json') --fixture $Fixture --job-id '20260829-202013-296b18'
  if ($LASTEXITCODE -ne 0) { throw "creator lifecycle failed with exit code $LASTEXITCODE" }
} finally {
  if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
  Remove-Item Env:CLIPGAUGE_QA_WEBVIEW2_CDP -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_USER_DATA_FOLDER -ErrorAction SilentlyContinue
  Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS -ErrorAction SilentlyContinue
}
