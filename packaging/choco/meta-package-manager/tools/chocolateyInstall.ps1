$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.4.2/mpm-6.4.2-windows-x64.exe'
$checksumX64 = 'E475388A2EE78C73061BAE4BE54994581E03172F5D4D66D7A37B98E91C64299C'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.4.2/mpm-6.4.2-windows-arm64.exe'
$checksumArm64 = 'BF502E1C5D7E6BF457E113C9109E0DA68E3841D7278FA78001DFB12290E9BBC7'

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
