$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v7.6.1/meta-package-manager-7.6.1-windows-x64.exe'
$checksumX64 = '2544B48C6E90BFADA2DA4A61195267F11CF7C33B7DEEE7E70DDB355C453A4F0E'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v7.6.1/meta-package-manager-7.6.1-windows-arm64.exe'
$checksumArm64 = '3766AB116095F538483000B61FCE5C2345019962F49F26FE9F8888C376393788'

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
