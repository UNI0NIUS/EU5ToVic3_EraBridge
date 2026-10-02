param([Parameter(Mandatory=$true)][string]$Package)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$packagePath=(Resolve-Path -LiteralPath $Package).Path
if (-not $packagePath.StartsWith($projectRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Package must be inside workspace' }
if (Get-Process victoria3 -ErrorAction SilentlyContinue) { throw 'Victoria 3 is running; installation deferred' }
$report=Get-Content -LiteralPath (Join-Path $packagePath 'package_report.json') -Raw | ConvertFrom-Json -AsHashtable
if ($report.status -ne 'passed_static_runtime_pending') { throw 'Unverified package' }
foreach ($file in $report.input_sha256.Keys) {
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $report.input_sha256[$file]) { throw "Changed package input: $file" }
}
function Get-Manifest([string]$Folder) {
    $result=@{}
    foreach ($file in Get-ChildItem -LiteralPath $Folder -File -Recurse -Force) {
        $relative=[IO.Path]::GetRelativePath($Folder,$file.FullName).Replace('\','/')
        $result[$relative]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $result
}
function Assert-Manifest($Actual,$Expected,[string]$Label) {
    if ($Actual.Count -ne $Expected.Count) { throw "$Label file count changed" }
    foreach ($name in $Expected.Keys) { if ($Actual[$name] -ne $Expected[$name]) { throw "$Label changed: $name" } }
}
$source=[IO.Path]::GetFullPath($report.mod_directory)
if (-not $source.StartsWith($packagePath+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid source mod' }
Assert-Manifest (Get-Manifest $source) $report.output_sha256 'Candidate'
$previous=Get-Content -LiteralPath (Join-Path $report.previous_package 'package_report.json') -Raw | ConvertFrom-Json -AsHashtable
$gameUser=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Paradox Interactive/Victoria 3'
$modRoot=[IO.Path]::GetFullPath((Join-Path $gameUser 'mod'))
$target=[IO.Path]::GetFullPath((Join-Path $modRoot 'eu5_m5_1337_test'))
if ([IO.Path]::GetDirectoryName($target) -ne $modRoot -or [IO.Path]::GetFileName($target) -ne 'eu5_m5_1337_test') { throw 'Invalid install target' }
$descriptor=Join-Path $modRoot 'eu5_m5_1337_test.mod'
Assert-Manifest (Get-Manifest $target) $previous.output_sha256 'Installed 1337'
if ((Get-FileHash -LiteralPath $descriptor).Hash -ne (Get-FileHash -LiteralPath (Join-Path $report.previous_package 'eu5_m5_1337_test.mod')).Hash) { throw 'Installed descriptor changed' }
$other=Join-Path $modRoot 'eu5_economy_test';$otherBefore=Get-Manifest $other
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss-ffff'
$backupRoot=[IO.Path]::GetFullPath((Join-Path $gameUser 'eu5_converter_backups'))
$backup=[IO.Path]::GetFullPath((Join-Path $backupRoot ('1337-'+$stamp)))
$stage=[IO.Path]::GetFullPath((Join-Path $modRoot ('eu5_1337_staging_'+$stamp)))
if ([IO.Path]::GetDirectoryName($backup) -ne $backupRoot -or [IO.Path]::GetDirectoryName($stage) -ne $modRoot) { throw 'Backup or staging path escaped' }
if ((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $stage)) { throw 'Backup/staging already exists' }
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $descriptor -Destination (Join-Path $backup 'eu5_m5_1337_test.mod')
Copy-Item -LiteralPath $source -Destination $stage -Recurse
Assert-Manifest (Get-Manifest $stage) $report.output_sha256 'Staged 1337'
if (Get-Process victoria3 -ErrorAction SilentlyContinue) { throw 'Victoria 3 started; installation deferred' }
Move-Item -LiteralPath $target -Destination (Join-Path $backup 'eu5_m5_1337_test')
try {
    Move-Item -LiteralPath $stage -Destination $target
    Copy-Item -LiteralPath (Join-Path $packagePath 'eu5_m5_1337_test.mod') -Destination $descriptor -Force
    Assert-Manifest (Get-Manifest $target) $report.output_sha256 'Installed update'
    Assert-Manifest (Get-Manifest $other) $otherBefore '1780 installation'
} catch {
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination (Join-Path $backup 'failed_candidate') }
    Move-Item -LiteralPath (Join-Path $backup 'eu5_m5_1337_test') -Destination $target
    Copy-Item -LiteralPath (Join-Path $backup 'eu5_m5_1337_test.mod') -Destination $descriptor -Force
    throw
}
$record=@{status='installed_static_verified_runtime_pending';version=$report.version;name=$report.mod_name;package=$packagePath;target=$target;verified_files=$report.output_sha256.Count;backup=$backup;previous_1780_unchanged=$true;playset_changed=$false;new_campaign_required=$true;timestamp=(Get-Date).ToUniversalTime().ToString('o')}
$json=$record | ConvertTo-Json -Depth 10
$json | Set-Content -LiteralPath (Join-Path $packagePath 'installation.json') -Encoding utf8
$json | Set-Content -LiteralPath (Join-Path $projectRoot '.local/conversion/1337-20261002/installation.json') -Encoding utf8
$json | Set-Content -LiteralPath (Join-Path $projectRoot '.local/conversion/1337-installation-latest.json') -Encoding utf8
Write-Output $json
