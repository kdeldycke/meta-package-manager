$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$urlX64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.3.0/mpm-6.3.0-windows-x64.exe'
$checksumX64 = 'B32584E572DDA6302D89BF3F76C85480E39330BF4BE3296EA0412FFD1A72C731'
$urlArm64 = 'https://github.com/kdeldycke/meta-package-manager/releases/download/v6.3.0/mpm-6.3.0-windows-arm64.exe'
$checksumArm64 = 'CA800D389DC84EA8A2D66E069B8D6EB65E9DFA9ED47B779E4AFA8FC909CB5521'

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
