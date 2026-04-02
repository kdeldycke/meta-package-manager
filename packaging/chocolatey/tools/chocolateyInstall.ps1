$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.2.1/mpm-6.2.1-windows-x64.exe'
$checksumX64 = '3edbaf472a6a154db6c2f9f33f935737eeead50a8a7159612ebe0ba930d3a47f'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.2.1/mpm-6.2.1-windows-arm64.exe'
$checksumArm64 = '136d9410d3887b1023e30f9e31f6e3d054d117ebd08cf50d7d8f83f87a3c6b39'

if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    $url = $urlArm64
    $checksum = $checksumArm64
} else {
    $url = $urlX64
    $checksum = $checksumX64
}

Get-ChocolateyWebFile -PackageName $env:ChocolateyPackageName `
    -FileFullPath (Join-Path $toolsDir 'mpm.exe') `
    -Url $url `
    -Checksum $checksum `
    -ChecksumType 'sha256'
