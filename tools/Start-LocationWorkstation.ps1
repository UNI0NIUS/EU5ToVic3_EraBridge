param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$dataPath = Join-Path $projectRoot '.local\m4\location-workstation'
if (-not (Test-Path (Join-Path $dataPath 'data.json'))) {
    & $pythonPath (Join-Path $PSScriptRoot 'build_location_workstation.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not build map data.' }
}
$serviceUrl = "http://127.0.0.1:$Port"
try { $null = Invoke-RestMethod "$serviceUrl/api/session" -TimeoutSec 2; $ready = $true } catch { $ready = $false }
if (-not $ready) {
    $scriptPath = Join-Path $PSScriptRoot 'serve_location_workstation.py'
    Start-Process -FilePath $pythonPath -ArgumentList @(('"' + $scriptPath + '"'), '--port', $Port) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataPath 'server.log') -RedirectStandardError (Join-Path $dataPath 'server-error.log')
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $null = Invoke-RestMethod "$serviceUrl/api/session" -TimeoutSec 2; $ready = $true; break } catch {}
    }
}
if (-not $ready) { throw 'Workstation did not start. See .local/m4/location-workstation/server-error.log' }
Start-Process $serviceUrl
Write-Output "Workstation: $serviceUrl"
