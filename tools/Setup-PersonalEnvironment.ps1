param([string]$PythonCommand = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolsRoot = Join-Path $projectRoot '.tools'
New-Item -ItemType Directory -Force $toolsRoot | Out-Null

function Get-VerifiedFile([string]$Url, [string]$Destination, [string]$Sha256) {
    if (-not (Test-Path -LiteralPath $Destination) -or
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Sha256) {
        Invoke-WebRequest -Uri $Url -OutFile $Destination
    }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Sha256) {
        throw "Hash mismatch: $Destination. Review changed upstream content before updating the lock."
    }
}

# Reviewed extraction helper. The compiler and SDK payloads come from Microsoft;
# this helper validates their hashes from Microsoft's package manifest.
$helper = Join-Path $toolsRoot 'portable-msvc.py'
Get-VerifiedFile 'https://gist.githubusercontent.com/mmozeiko/7f3162ec2988e81e56d5c4e22cde9977/raw/portable-msvc.py' $helper '1791cccca594ff083ce8d3e0a139e6156d2c312e24332a909e608010f0230a51'
Push-Location $toolsRoot
try {
    foreach ($name in @('msvc', 'downloads')) {
        $target = [System.IO.Path]::GetFullPath((Join-Path $toolsRoot $name))
        if (-not $target.StartsWith($toolsRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Extraction target escapes project tools directory.'
        }
        if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw 'Extraction target must not be a junction or symlink.'
        }
    }
    if (-not (Test-Path 'msvc/setup_x64.bat')) {
        & $PythonCommand -u $helper --vs 2022 --msvc-version 14.44 --sdk-version 26100 --accept-license
        if ($LASTEXITCODE -ne 0) { throw 'MSVC extraction failed.' }
    }
    if (-not (Test-Path 'python/Scripts/python.exe')) {
        & $PythonCommand -m venv python
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    & ./python/Scripts/python.exe -m pip install --disable-pip-version-check cmake==3.31.6 ninja==1.11.1.4
    if ($LASTEXITCODE -ne 0) { throw 'CMake/Ninja installation failed.' }
    New-Item -ItemType Directory -Force rakaly-0.12.7 | Out-Null
    Get-VerifiedFile 'https://github.com/rakaly/librakaly/releases/download/v0.12.7/librakaly-0.12.7-win-msvc.tar.gz' "$toolsRoot/rakaly-0.12.7/package.tar.gz" 'fca77183bf4d68dbc09cba2c422211a323e3770ce010e754bdc75adbec43caef'
    & tar -xzf rakaly-0.12.7/package.tar.gz -C rakaly-0.12.7
    if ($LASTEXITCODE -ne 0) { throw 'Rakaly extraction failed.' }
} finally { Pop-Location }
. "$PSScriptRoot/Enter-DevEnvironment.ps1"
& cmake --version
& ninja --version
