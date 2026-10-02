param(
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Environment = 'not independently classified',
    [string]$EU5,
    [string]$Game,
    [string]$Baseline,
    [string]$Save,
    [string]$Package
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskPython = Join-Path $taskRoot 'runtime/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '请从完整解压的发行目录运行此脚本。' }
$taskArgs = @('-X', 'utf8', (Join-Path $taskRoot 'tools/release_acceptance.py'), '--out', $Output, '--environment', $Environment)
foreach ($item in @(@('--eu5',$EU5), @('--game',$Game), @('--baseline',$Baseline), @('--save',$Save), @('--package',$Package))) {
    if ($item[1]) { $taskArgs += $item }
}
$taskOldPath = $env:PATH
$taskOldPythonPath = $env:PYTHONPATH
$taskOldPythonHome = $env:PYTHONHOME
try {
    $env:PATH = Join-Path $env:SystemRoot 'System32'
    $env:PYTHONPATH = $null
    $env:PYTHONHOME = $null
    & $taskPython @taskArgs
    if ($LASTEXITCODE -ne 0) { throw '验收失败，请查看输出目录中的 acceptance.json 和 failure.log。' }
} finally {
    $env:PATH = $taskOldPath
    $env:PYTHONPATH = $taskOldPythonPath
    $env:PYTHONHOME = $taskOldPythonHome
}
