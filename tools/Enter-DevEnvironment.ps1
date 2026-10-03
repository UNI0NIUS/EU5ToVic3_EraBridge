param([string]$VisualStudioPath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolsRoot = Join-Path $projectRoot '.tools'
if (-not $VisualStudioPath) { $VisualStudioPath = Join-Path $toolsRoot 'VisualStudio2022' }
$taskVsDevCmd = Join-Path $VisualStudioPath 'Common7/Tools/VsDevCmd.bat'
if (Test-Path -LiteralPath $taskVsDevCmd) {
    $taskCommand = '"' + $taskVsDevCmd + '" -no_logo -arch=x64 -host_arch=x64 && set'
    $taskEnvironment = & $env:ComSpec /d /s /c $taskCommand
    if ($LASTEXITCODE -ne 0) { throw 'Visual Studio environment initialization failed.' }
    foreach ($taskLine in $taskEnvironment) {
        if ($taskLine -match '^([^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
    # Some parent environments contain both PATH and Path. VsDevCmd updates PATH;
    # importing the stale mixed-case entry must not replace the compiler paths.
    $taskCompilerPath = $taskEnvironment | Where-Object { $_ -cmatch '^PATH=' } | Select-Object -First 1
    if ($taskCompilerPath) { $env:PATH = $taskCompilerPath.Substring(5) }
    $env:PATH = "$toolsRoot/python/Lib/site-packages/cmake/data/bin;$toolsRoot/python/Scripts;$env:PATH"
    $env:PYTHONUTF8 = '1'
    Write-Host "Visual Studio C++ $env:VCToolsVersion, SDK $env:WindowsSDKVersion"
    return
}
$msvcRoot = Join-Path $toolsRoot 'msvc'
$compiler = Get-ChildItem "$msvcRoot/VC/Tools/MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdk = Get-ChildItem "$msvcRoot/Windows Kits/10/Include" -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $compiler -or -not $sdk) { throw 'Missing project-local MSVC/SDK; see docs/M0_ENVIRONMENT.md.' }
$compilerBin = Join-Path $compiler.FullName 'bin/Hostx64/x64'
$sdkBin = Join-Path $msvcRoot "Windows Kits/10/bin/$($sdk.Name)/x64"
$env:PATH = "$toolsRoot/python/Lib/site-packages/cmake/data/bin;$toolsRoot/python/Scripts;$compilerBin;$sdkBin;$sdkBin/ucrt;$env:PATH"
$env:INCLUDE = "$($compiler.FullName)/include;$($sdk.FullName)/ucrt;$($sdk.FullName)/shared;$($sdk.FullName)/um;$($sdk.FullName)/winrt;$($sdk.FullName)/cppwinrt"
$env:LIB = "$($compiler.FullName)/lib/x64;$msvcRoot/Windows Kits/10/Lib/$($sdk.Name)/ucrt/x64;$msvcRoot/Windows Kits/10/Lib/$($sdk.Name)/um/x64"
$env:VSCMD_ARG_HOST_ARCH = 'x64'
$env:VSCMD_ARG_TGT_ARCH = 'x64'
$env:VCToolsInstallDir = "$($compiler.FullName)/"
$env:VCToolsVersion = $compiler.Name
$env:WindowsSDKVersion = "$($sdk.Name)/"
$env:PYTHONUTF8 = '1'
Write-Host "Local MSVC $($compiler.Name), SDK $($sdk.Name)"
