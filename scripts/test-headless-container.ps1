param(
    [string]$Image = "clipgauge-headless:test"
)

docker build -f Dockerfile.headless -t $Image .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$container = docker run -d -e CLIPGAUGE_SERVER_TOKEN=local-test-token -p 18732:8732 $Image
try {
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Start-Sleep -Seconds 5
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:18732/v1/health"
    if (-not $health.ok) { throw "headless health failed" }
    $ready = Invoke-RestMethod -Headers @{ "X-ClipGauge-Token" = "local-test-token" } -Uri "http://127.0.0.1:18732/v1/readiness"
    if (-not $ready.ok) { throw "headless readiness failed" }
} finally {
    docker rm -f $container | Out-Null
}
