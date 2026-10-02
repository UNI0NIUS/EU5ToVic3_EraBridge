param([int]$Port = 8769, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$dataPath = Join-Path $projectRoot '.local\m3\terrain-workstation-1337-rereview'
$env:PYTHONUTF8 = '1'
if (-not (Test-Path (Join-Path $dataPath 'data.json'))) {
    & $pythonPath (Join-Path $PSScriptRoot 'build_1337_empty_review.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not build terrain data.' }
}
$serviceUrl = "http://127.0.0.1:$Port"
try { $session = Invoke-RestMethod "$serviceUrl/api/session" -TimeoutSec 2; $ready = $true } catch { $ready = $false }
if ($ready -and $session.reviews.schema -ne 'terrain-references-v1') { throw 'Port is used by another workstation. Choose another port.' }
if (-not $ready) {
    $scriptPath = Join-Path $PSScriptRoot 'serve_terrain_workstation.py'
    Start-Process -FilePath $pythonPath -ArgumentList @(('"' + $scriptPath + '"'), '--port', $Port, '--data', ('"' + $dataPath + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataPath 'server.log') -RedirectStandardError (Join-Path $dataPath 'server-error.log')
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $session = Invoke-RestMethod "$serviceUrl/api/session" -TimeoutSec 2; $ready = $session.reviews.schema -eq 'terrain-references-v1'; if ($ready) { break } } catch {}
    }
}
if (-not $ready) { throw 'Terrain workstation did not start. See .local/m3/terrain-workstation-1337/server-error.log' }
if (-not $NoOpen) { Start-Process $serviceUrl }
Write-Output "1337 workstation: $serviceUrl"
