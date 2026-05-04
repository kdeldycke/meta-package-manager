$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.4.1/mpm-6.4.1-windows-x64.exe'
$checksumX64 = '98C041E6A551F306558E12599583CE5F2A793012A14EEAB1D88EC94BDE9EC5BC'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.4.1/mpm-6.4.1-windows-arm64.exe'
$checksumArm64 = '4A540F9E5C78E2A24AD125171A26198183180D5002269FD367D9DB900E53FBDA'

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
