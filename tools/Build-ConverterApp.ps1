param([string]$Output = 'build/ConverterWorkbench', [switch]$SkipRuntime, [switch]$IncludeLocalRules)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimePython = (Get-Command python -CommandType Application | Select-Object -First 1).Source
$appOutput = [IO.Path]::GetFullPath((Join-Path $projectRoot $Output))
if (-not $appOutput.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build output must stay inside project.' }
$taskRuleArgs = @()
if ($IncludeLocalRules) { $taskRuleArgs += '--include-local-rules' }
if (-not $SkipRuntime) {
    & $runtimePython -X utf8 "$PSScriptRoot/package_converter_app.py" --root $projectRoot --out $appOutput @taskRuleArgs
    if ($LASTEXITCODE -ne 0) { throw 'Runtime packaging failed.' }
} else {
    & $runtimePython -X utf8 "$PSScriptRoot/package_converter_app.py" --root $projectRoot --out $appOutput --refresh-code @taskRuleArgs
    if ($LASTEXITCODE -ne 0) { throw 'Application refresh failed.' }
}
. "$PSScriptRoot/Enter-DevEnvironment.ps1"
& rc /nologo /i "$PSScriptRoot" "/fo$appOutput/launcher.res" "$PSScriptRoot/converter_launcher.rc"
if ($LASTEXITCODE -ne 0) { throw 'Launcher icon compilation failed.' }
& cl /nologo /std:c++17 /O2 /MT /utf-8 /EHsc "$PSScriptRoot/converter_launcher.cpp" "$appOutput/launcher.res" "/Fe:$appOutput/EU5Converter.exe" "/Fo:$appOutput/launcher.obj" /link /SUBSYSTEM:WINDOWS user32.lib
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
& $runtimePython -X utf8 "$PSScriptRoot/package_converter_app.py" --root $projectRoot --out $appOutput --seal
if ($LASTEXITCODE -ne 0) { throw 'Manifest generation failed.' }
Write-Host "Built: $appOutput/EU5Converter.exe"
