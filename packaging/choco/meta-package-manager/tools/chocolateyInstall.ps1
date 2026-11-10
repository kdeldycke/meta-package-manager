$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v8.3.0/meta-package-manager-8.3.0-windows-x64.exe'
$checksumX64 = '502C4C5F1DA095A8AC915B49A004AB18EBF857A0688EB9509D9A7DD37122961A'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v8.3.0/meta-package-manager-8.3.0-windows-arm64.exe'
$checksumArm64 = '1BBBE355AAF8748C49764CB1A8D1C1F316F8DE811A1ECFB09522523DCF3B351E'

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
