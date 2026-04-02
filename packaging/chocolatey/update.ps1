Import-Module Chocolatey-AU

function global:au_GetLatest {
    $release = Invoke-RestMethod 'https://api.github.com/repos/kdeldycke/meta-package-manager/releases/latest'
    $version = $release.tag_name.TrimStart('v')
    $baseUrl = "https://github.com/kdeldycke/meta-package-manager/releases/download/v$version"

    $urlX64 = "$baseUrl/mpm-windows-x64.exe"
    $urlArm64 = "$baseUrl/mpm-windows-arm64.exe"

    # Download binaries to compute checksums.
    $tempDir = Join-Path $env:TEMP "mpm-choco-$version"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    $x64Path = Join-Path $tempDir 'mpm-windows-x64.exe'
    $arm64Path = Join-Path $tempDir 'mpm-windows-arm64.exe'

    Invoke-WebRequest -Uri $urlX64 -OutFile $x64Path
    Invoke-WebRequest -Uri $urlArm64 -OutFile $arm64Path

    $checksumX64 = (Get-FileHash -Path $x64Path -Algorithm SHA256).Hash
    $checksumArm64 = (Get-FileHash -Path $arm64Path -Algorithm SHA256).Hash

    Remove-Item $tempDir -Recurse -Force

    @{
        Version       = $version
        UrlX64        = $urlX64
        UrlArm64      = $urlArm64
        ChecksumX64   = $checksumX64
        ChecksumArm64 = $checksumArm64
    }
}

function global:au_SearchReplace {
    @{
        ".\tools\chocolateyInstall.ps1" = @{
            "(^\`$urlX64\s*=\s*)'.*'"         = "`${1}'$($Latest.UrlX64)'"
            "(^\`$checksumX64\s*=\s*)'.*'"    = "`${1}'$($Latest.ChecksumX64)'"
            "(^\`$urlArm64\s*=\s*)'.*'"       = "`${1}'$($Latest.UrlArm64)'"
            "(^\`$checksumArm64\s*=\s*)'.*'"  = "`${1}'$($Latest.ChecksumArm64)'"
        }
        ".\legal\VERIFICATION.txt" = @{
            "(?i)(x64:\s+)https://.*"         = "`${1}$($Latest.UrlX64)"
            "(?i)(ARM64:\s+)https://.*"       = "`${1}$($Latest.UrlArm64)"
            "(?i)(x64 checksum:\s+).*"        = "`${1}$($Latest.ChecksumX64)"
            "(?i)(ARM64 checksum:\s+).*"      = "`${1}$($Latest.ChecksumArm64)"
        }
        ".\meta-package-manager.nuspec" = @{
            "(<releaseNotes>)[^<]*(</releaseNotes>)" = "`${1}https://github.com/kdeldycke/meta-package-manager/releases/tag/v$($Latest.Version)`${2}"
        }
    }
}

Update-Package -ChecksumFor none
