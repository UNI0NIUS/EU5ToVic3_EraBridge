param([switch]$ConfigureOnly, [switch]$SkipTests, [int]$Jobs = 8)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/Enter-DevEnvironment.ps1"
$projectRoot = Split-Path $PSScriptRoot -Parent
$logRoot = Join-Path $projectRoot '.local/m0'
New-Item -ItemType Directory -Force $logRoot | Out-Null
Push-Location $projectRoot
try {
    & cmake --preset x64-release-windows -DBUILD_FRONTEND=OFF "-DCMAKE_MAKE_PROGRAM=$projectRoot/.tools/python/Scripts/ninja.exe" "-DRAKALY_DIR=$projectRoot/.tools/rakaly-0.12.7/librakaly-0.12.7-win-msvc" 2>&1 | Tee-Object "$logRoot/configure.log"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
    if ($ConfigureOnly) { return }
    & cmake --build --preset build-x64-release-windows --target EU5ToVic3Converter EU5ToVic3Tests --parallel $Jobs 2>&1 | Tee-Object "$logRoot/build.log"
    if ($LASTEXITCODE -ne 0) { throw 'Build failed; see .local/m0/build.log.' }
    if (-not $SkipTests) {
        & ctest --test-dir build/x64-release-windows --output-on-failure --output-junit "$logRoot/ctest.xml" 2>&1 | Tee-Object "$logRoot/test.log"
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed; see .local/m0/test.log.' }
    }
} finally { Pop-Location }
