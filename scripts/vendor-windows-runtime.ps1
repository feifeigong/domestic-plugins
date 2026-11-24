[CmdletBinding()]
param(
    [string]$PluginRoot = (Join-Path $PSScriptRoot '../plugins/china-email')
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$version = '3.13.17'
# SHA-256 values from https://www.python.org/downloads/release/python-31317/
$checksums = [ordered]@{
    amd64 = '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38'
    arm64 = '7b58787a047b400edbfcb539aa3cdb4e2ed77bf0f22cae42b7c01cedd7dd6614'
}
$runtimeRoot = Join-Path (Resolve-Path -LiteralPath $PluginRoot).Path 'runtime/windows'
if (Test-Path -LiteralPath $runtimeRoot) {
    throw "Use a clean plugin checkout. The runtime directory already exists: $runtimeRoot"
}

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('china-email-runtime-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
foreach ($platform in $checksums.Keys) {
    $name = "python-$version-embed-$platform.zip"
    $archive = Join-Path $temporaryRoot $name
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$version/$name" -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $checksums[$platform]) {
        throw "SHA-256 verification failed for $name"
    }
    $unpacked = Join-Path $temporaryRoot $platform
    Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
    foreach ($required in 'python.exe', 'python313.dll', 'python313.zip', '_ssl.pyd', 'LICENSE.txt') {
        if (-not (Test-Path -LiteralPath (Join-Path $unpacked $required) -PathType Leaf)) {
            throw "Verified package $name is missing $required"
        }
    }
    Remove-Item -LiteralPath $archive
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
foreach ($platform in $checksums.Keys) {
    Copy-Item -LiteralPath (Join-Path $temporaryRoot $platform) -Destination $runtimeRoot -Recurse
    Write-Output "Bundled CPython $version for Windows $platform"
}
