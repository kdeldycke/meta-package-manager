$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.2.1/mpm-windows-x64.exe'
$checksumX64 = '0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.2.1/mpm-windows-arm64.exe'
$checksumArm64 = '0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5'

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
