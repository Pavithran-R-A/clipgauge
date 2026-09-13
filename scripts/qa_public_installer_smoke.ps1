$ErrorActionPreference = 'Stop'
$setup = Join-Path $PSScriptRoot '..\app\src-tauri\target\release\bundle\nsis\ClipGauge_0.5.16_x64-setup.exe' | Resolve-Path
$profileRoot = Join-Path $env:USERPROFILE '.clipgauge'
$marker = Join-Path $profileRoot ("release-qualification-marker-{0}.txt" -f [Guid]::NewGuid().ToString('N'))

if (-not (Test-Path -LiteralPath $setup)) { throw 'rebuilt installer is missing' }
New-Item -ItemType Directory -Force $profileRoot | Out-Null
Set-Content -LiteralPath $marker -Value 'preserve-user-state' -Encoding utf8
try {
    Start-Process -FilePath $setup -ArgumentList '/S' -Wait -WindowStyle Hidden
    $uninstall = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue } |
        Where-Object { $_.DisplayName -eq 'ClipGauge' } |
        Select-Object -First 1
    $installRoot = if ($uninstall -and $uninstall.InstallLocation) {
        ([string]$uninstall.InstallLocation).Trim('"')
    } else {
        Join-Path $env:LOCALAPPDATA 'ClipGauge'
    }
    $exe = Join-Path $installRoot 'clipgauge-app.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'installed executable is missing' }
    if ((Get-Content -Raw -LiteralPath $marker).Trim() -ne 'preserve-user-state') {
        throw 'user profile marker was not preserved'
    }
    $process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
    try {
        $deadline = (Get-Date).AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 500
            $process.Refresh()
        } while ((Get-Date) -lt $deadline -and $process.MainWindowHandle -eq [IntPtr]::Zero -and -not $process.HasExited)
        $process.Refresh()
        [pscustomobject]@{
            installer = $setup.Path
            installed_executable = $exe
            installed_version = (Get-Item $exe).VersionInfo.ProductVersion
            window_ready = $process.MainWindowHandle -ne [IntPtr]::Zero
            profile_marker_preserved = $true
            process_exit = if ($process.HasExited) { $process.ExitCode } else { $null }
        } | ConvertTo-Json -Compress
    }
    finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
}
finally {
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
}
