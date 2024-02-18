# Benchmark

Attempting to unify all package managers is a Sisyphean task.

This did not prevent me or others to try to solve that problem. It is not easy to explain why
but [there might be a greater need for such tools](usecase.md) out there. Here is a list of some related projects I stumbled into and how they compares to `mpm`.

## Features

| Feature                                                  | `mpm` | `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| -------------------------------------------------------- | :---: | :------------: | :-----------: | :----------: | :----------: |
| Package manager autodetection                            |   ✓   |       ✓        |               |              |              |
| Unified CLI and options                                  |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| Multi-PM execution                                       |   ✓   |       ✓        |               |              |              |
| Package manager priority                                 |   ✓   |                |               |              |              |
| Consolidated output                                      |   ✓   |                |               |              |              |
| Configurable output                                      |   ✓   |                |               |              |              |
| Sortable output                                          |   ✓   |                |               |              |              |
| Colored output                                           |   ✓   |       ✓        |               |              |              |
| Version parsing and diff                                 |   ✓   |                |               |              |              |
| [purl](https://github.com/package-url/purl-spec) support |   ✓   |                |               |              |              |
| JSON export                                              |   ✓   |                |               |              |              |
| CSV export                                               |   ✓   |                |               |              |              |
| Markup export                                            |   ✓   |                |               |              |              |
| Configuration file                                       |   ✓   |       ✓        |       ✓       |              |      ✓       |
| Non-interactive                                          |   ✓   |       ✓        |       ✓       |              |              |
| Dry-run                                                  |   ✓   |       ✓        |       ✓       |              |              |
| Sudo elevation                                           |   ✓   |       ✓        |       ✓       |              |              |
| Desktop notifications                                    |       |       ✓        |               |              |              |
| Bash auto-completion                                     |   ✓   |                |               |              |              |
| Zsh auto-completion                                      |   ✓   |                |               |              |              |
| Fish auto-completion                                     |   ✓   |                |               |              |              |
| [XKCD #1654](https://xkcd.com/1654/)                     |   ✓   |                |               |              |              |
| [Xbar/SwiftBar plugin](bar-plugin.md)                    |   ✓   |                |               |              |              |

## Operations

| Operation                         | `mpm` | `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| --------------------------------- | :---: | :------------: | :-----------: | :----------: | :----------: |
| List available managers           |   ✓   |                |               |              |              |
| List installed packages           |   ✓   |                |       ✓       |              |      ✓       |
| List duplicate packages           |   ✓   |                |               |              |              |
| List outdated packages            |   ✓   |                |       ✓       |              |      ✓       |
| Search packages                   |   ✓   |                |       ✓       |      ✓       |      ✓       |
| Locate binaries (`which` command) |   ✓   |                |               |              |              |
| Install a package                 |   ✓   |                |       ✓       |      ✓       |      ✓       |
| Remove / Uninstall a package      |   ✓   |                |       ✓       |      ✓       |      ✓       |
| Upgrade single package            |   ✓   |                |       ✓       |              |      ✓       |
| Upgrade all packages              |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| Sync                              |   ✓   |                |       ✓       |      ✓       |      ✓       |
| Cleanup: caches                   |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| Cleanup: orphans                  |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| Backup / Lock / Freeze            |   ✓   |                |               |              |              |
| Restore                           |   ✓   |                |               |              |              |

## Package manager support

| Manager                 | `mpm` | `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| ----------------------- | :---: | :------------: | :-----------: | :----------: | :----------: |
| `0install`              |       |                |               |              |              |
| `antibody`              |       |       ✓        |               |              |              |
| `antigen`               |       |       ✓        |               |              |              |
| `apk`                   |       |                |       ✓       |      ✓       |              |
| `apm`                   |   ✓   |       ✓        |               |              |              |
| `apt`                   |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| `apt-cyg`               |       |                |               |      ✓       |              |
| `apt-mint`              |   ✓   |                |               |              |              |
| `asdf`                  |       |       ✓        |               |              |              |
| `aura`                  |       |       ✓        |               |              |              |
| `bin`                   |       |       ✓        |               |              |              |
| `brew`                  |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| `bun`                   |       |       ✓        |               |              |              |
| `cargo`                 |   ✓   |       ✓        |               |              |              |
| `cask`                  |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| `cave`                  |       |                |               |      ✓       |              |
| `chezmoi`               |       |       ✓        |               |              |              |
| `chocolatey`            |   ✓   |       ✓        |       ✓       |              |              |
| `choosenim`             |       |       ✓        |               |              |              |
| `chromebrew`            |       |                |               |              |      ✓       |
| `composer`              |   ✓   |       ✓        |               |              |              |
| `conda`                 |       |       ✓        |       ✓       |      ✓       |              |
| `containers`            |       |       ✓        |               |              |              |
| `dein`                  |       |       ✓        |               |              |              |
| `deno`                  |       |       ✓        |               |              |              |
| `distrobox`             |       |       ✓        |               |              |              |
| `dnf`                   |   ✓   |                |       ✓       |              |      ✓       |
| `dotnet`                |       |       ✓        |               |              |              |
| `emacs`                 |       |       ✓        |               |              |              |
| `emerge`                |   ✓   |       ✓        |       ✓       |      ✓       |      ✓       |
| `eopkg`                 |       |                |               |              |      ✓       |
| `etc-update`            |       |       ✓        |               |              |              |
| `fisher`                |       |       ✓        |               |              |              |
| `flatpak`               |   ✓   |       ✓        |               |              |      ✓       |
| `flutter`               |       |       ✓        |               |              |              |
| `fossil`                |       |       ✓        |               |              |              |
| `fwupdmgr`              |       |       ✓        |               |              |              |
| `gcloud`                |       |       ✓        |               |              |              |
| `gem`                   |   ✓   |       ✓        |               |              |      ✓       |
| `ghcup`                 |       |       ✓        |               |              |              |
| `git`                   |       |       ✓        |               |              |              |
| `github-cli-extensions` |       |       ✓        |               |              |              |
| `gnome-shell`           |       |       ✓        |               |              |              |
| `go`                    |       |       ✓        |               |              |              |
| `guix`                  |       |       ✓        |               |              |      ✓       |
| `haxelib`               |       |       ✓        |               |              |              |
| `home-manager`          |       |       ✓        |               |              |              |
| `jetpack`               |       |       ✓        |               |              |              |
| `julia`                 |       |       ✓        |               |              |              |
| `kakoune`               |       |       ✓        |               |              |              |
| `krew`                  |       |       ✓        |               |              |              |
| `macos`                 |       |       ✓        |               |              |              |
| `macports`              |       |       ✓        |       ✓       |      ✓       |      ✓       |
| `mas`                   |   ✓   |       ✓        |               |              |              |
| `micro`                 |       |       ✓        |               |              |              |
| `myrepos`               |       |       ✓        |               |              |              |
| `nala`                  |       |       ✓        |               |              |              |
| `neobundle`             |       |       ✓        |               |              |              |
| `nix`                   |       |       ✓        |               |              |      ✓       |
| `npm`                   |   ✓   |       ✓        |               |              |      ✓       |
| `oh-my-zsh`             |       |       ✓        |               |              |              |
| `opam`                  |       |       ✓        |               |              |              |
| `opkg`                  |   ✓   |                |               |      ✓       |              |
| `pacaur`                |   ✓   |                |               |              |              |
| `pacman`                |   ✓   |       ✓        |               |      ✓       |      ✓       |
| `pacstall`              |       |       ✓        |               |              |              |
| `pamac`                 |       |       ✓        |               |              |              |
| `paru`                  |   ✓   |       ✓        |               |              |              |
| `pearl`                 |       |       ✓        |               |              |              |
| `pihole`                |       |       ✓        |               |              |              |
| `pikaur`                |       |       ✓        |               |              |              |
| `pip`                   |   ✓   |       ✓        |       ✓       |              |      ✓       |
| `pipx`                  |   ✓   |       ✓        |               |              |              |
| `pkg`                   |       |       ✓        |               |              |      ✓       |
| `pkg-mgr`               |       |                |               |              |      ✓       |
| `pkg-tools`             |       |                |               |      ✓       |              |
| `pkgin`                 |       |       ✓        |               |              |              |
| `pkgng`                 |       |                |               |      ✓       |              |
| `plug`                  |       |       ✓        |               |              |              |
| `pnpm`                  |       |       ✓        |               |              |              |
| `podman`                |       |       ✓        |               |              |              |
| `powershell`            |       |       ✓        |               |              |              |
| `protonup`              |       |       ✓        |               |              |              |
| `raco`                  |       |       ✓        |               |              |              |
| `rcm`                   |       |       ✓        |               |              |              |
| `remotes`               |       |       ✓        |               |              |              |
| `restarts`              |       |       ✓        |               |              |              |
| `rtcl`                  |       |       ✓        |               |              |              |
| `rustup`                |       |       ✓        |               |              |              |
| `scoop`                 |   ✓   |       ✓        |       ✓       |              |      ✓       |
| `sdkman`                |       |       ✓        |               |              |              |
| `sheldon`               |       |       ✓        |               |              |              |
| `slapt-get`             |       |                |               |              |      ✓       |
| `snap`                  |   ✓   |       ✓        |               |              |      ✓       |
| `spack`                 |       |                |               |              |              |
| `sparkle`               |       |       ✓        |               |              |              |
| `spicetify`             |       |       ✓        |               |              |              |
| `stack`                 |       |       ✓        |               |              |              |
| `steamcmd`              |   ✓   |                |               |              |              |
| `sun-tools`             |       |                |               |      ✓       |              |
| `swupd`                 |       |                |               |      ✓       |              |
| `system`                |       |       ✓        |               |              |              |
| `tazpkg`                |       |                |               |      ✓       |              |
| `tldr`                  |       |       ✓        |               |              |              |
| `tlmgr`                 |       |       ✓        |       ✓       |      ✓       |              |
| `toolbx`                |       |       ✓        |               |              |              |
| `trizen`                |       |       ✓        |               |              |              |
| `vagrant`               |       |       ✓        |               |              |              |
| `vcpkg`                 |       |       ✓        |               |              |              |
| `voom`                  |       |       ✓        |               |              |              |
| `vscode`                |   ✓   |                |               |              |              |
| `vundle`                |       |       ✓        |               |              |              |
| `winget`                |       |       ✓        |               |              |              |
| `wsl`                   |       |       ✓        |               |              |              |
| `xbps`                  |       |                |       ✓       |      ✓       |      ✓       |
| `yadm`                  |       |       ✓        |               |              |              |
| `yarn`                  |   ✓   |       ✓        |               |              |              |
| `yay`                   |   ✓   |       ✓        |               |              |              |
| `yum`                   |   ✓   |                |               |      ✓       |      ✓       |
| `zim`                   |       |       ✓        |               |              |              |
| `zinit`                 |       |       ✓        |               |              |              |
| `zplug`                 |       |       ✓        |               |              |              |
| `zr`                    |       |       ✓        |               |              |              |
| `zypper`                |   ✓   |                |       ✓       |      ✓       |      ✓       |

## Operating system support

| OS      |         `mpm`          | `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| ------- | :--------------------: | :------------: | :-----------: | :----------: | :----------: |
| BSD     | 🅱️[^bsd_without_macos] |                |               |              |              |
| Linux   |       🐧[^linux]        |       🐧        |       🐧       |      🐧       |      🐧       |
| macOS   |           🍎            |       🍎        |       🍎       |      🍎       |      🍎       |
| Unix    |      `>_`[^unix]       |                |               |              |              |
| Windows |           🪟            |       🪟        |       🪟       |              |              |

## Distribution

| Package manager |                                                                                                         `mpm`                                                                                                         |                                                                                          `topgrade`[^1]                                                                                           |                                                                                     `pacaptr`[^2]                                                                                     |                                                                                 `pacapt`[^3]                                                                                  |                                                                                        `sysget`[^4]                                                                                         |
| --------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------: |
| Versions        |                               [![Packaging status](https://repology.org/badge/vertical-allrepos/meta-package-manager.svg)](https://repology.org/project/meta-package-manager/versions)                                |                                 [![Packaging status](https://repology.org/badge/vertical-allrepos/topgrade.svg)](https://repology.org/project/topgrade/versions)                                  |                                                                                                                                                                                       |                         [![Packaging status](https://repology.org/badge/vertical-allrepos/pacapt.svg)](https://repology.org/project/pacapt/versions)                          |                                [![Packaging status](https://repology.org/badge/vertical-allrepos/sysget.svg)](https://repology.org/project/sysget/versions)                                 |
| GitHub          | [![GitHub release (latest by SemVer)](https://img.shields.io/github/downloads/kdeldycke/meta-package-manager/latest/total?sort=semver&style=flat-square)](https://github.com/kdeldycke/meta-package-manager/releases) | [![GitHub release (latest by SemVer)](https://img.shields.io/github/downloads/topgrade-rs/topgrade/latest/total?sort=semver&style=flat-square)](https://github.com/topgrade-rs/topgrade/releases) | [![GitHub release (latest by SemVer)](https://img.shields.io/github/downloads/rami3l/pacaptr/latest/total?sort=semver&style=flat-square)](https://github.com/rami3l/pacaptr/releases) | [![GitHub release (latest by SemVer)](https://img.shields.io/github/downloads/icy/pacapt/latest/total?sort=semver&style=flat-square)](https://github.com/icy/pacapt/releases) | [![GitHub release (latest by SemVer)](https://img.shields.io/github/downloads/emilengler/sysget/latest/total?sort=semver&style=flat-square)](https://github.com/emilengler/sysget/releases) |
| macOS binary    |                                                                                                ✓ (`x86_64`, `aarch64`)                                                                                                |                                                                                           ✓ (`x86_64`)                                                                                            |                                                                          ✓(`x86_64`, `aarch64`, `universal`)                                                                          |                                                                                                                                                                               |                                                                                                                                                                                             |
| Linux binary    |                                                                                                     ✓ (`x86_64`)                                                                                                      |                                                                                 ✓ (`x86_64`, `aarch64`, `armv7`)                                                                                  |                                                                                     ✓ (`x86_64`)                                                                                      |                                                                                                                                                                               |                                                                                        ✓ (`x86_64`)                                                                                         |
| Windows binary  |                                                                                                     ✓ (`x86_64`)                                                                                                      |                                                                                           ✓ (`x86_64`)                                                                                            |                                                                                     ✓ (`x86_64`)                                                                                      |                                                                                                                                                                               |                                                                                                                                                                                             |
| Homebrew        |          [![homebrew downloads](https://img.shields.io/homebrew/installs/dm/meta-package-manager?style=flat-square)](https://github.com/Homebrew/homebrew-core/blob/master/Formula/meta-package-manager.rb)           |            [![homebrew downloads](https://img.shields.io/homebrew/installs/dm/topgrade?style=flat-square)](https://github.com/Homebrew/homebrew-core/blob/master/Formula/topgrade.rb)             |                                                                      [✓](https://github.com/rami3l/pacaptr#brew)                                                                      |    [![homebrew downloads](https://img.shields.io/homebrew/installs/dm/pacapt?style=flat-square)](https://github.com/Homebrew/homebrew-core/blob/master/Formula/pacapt.rb)     |                                                                                                                                                                                             |
| Macports        |                                                                                                                                                                                                                       |                                                                          [✓](https://ports.macports.org/port/topgrade/)                                                                           |                                                                                                                                                                                       |                                                                                                                                                                               |                                                                                                                                                                                             |
| Chocolatey      |                                                                                                                                                                                                                       |                                                                                                                                                                                                   |                          [![Chocolatey](https://img.shields.io/chocolatey/dt/pacaptr?style=flat-square)](https://community.chocolatey.org/packages/pacaptr)                           |                                                                                                                                                                               |                                                                                                                                                                                             |
| Crates.io       |                                                                                                                                                                                                                       |                                           [![Crates.io](https://img.shields.io/crates/d/topgrade?style=flat-square)](https://crates.io/crates/topgrade)                                           |                                      [![Crates.io](https://img.shields.io/crates/d/pacaptr?style=flat-square)](https://crates.io/crates/pacaptr)                                      |                                                                                                                                                                               |                                                                                                                                                                                             |
| PyPi            |                                     [![PyPI - Downloads](https://img.shields.io/pypi/dm/meta-package-manager?style=flat-square)](https://pypi.org/project/meta-package-manager/)                                      |                                                                                                                                                                                                   |                                                                                                                                                                                       |                                                                                                                                                                               |                                                                                                                                                                                             |
| AUR votes       |                                 [![AUR](https://img.shields.io/aur/votes/meta-package-manager?label=%20&style=flat-square)](https://aur.archlinux.org/packages/meta-package-manager)                                  |                                   [![AUR](https://img.shields.io/aur/votes/topgrade?label=%20&style=flat-square)](https://aur.archlinux.org/packages/topgrade)                                    |                                                                                                                                                                                       |                                                                                                                                                                               |                                                                                                                                                                                             |

## Activity

| Metrics                      | `mpm`                                                                                                                                                  | `topgrade`[^1]                                                                                                                              | `pacaptr`[^2]                                                                                                                              | `pacapt`[^3]                                                                                                                                 | `sysget`[^4]                                                                                             |
| ---------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------- |
| Watchers                     | ![GitHub](https://img.shields.io/github/watchers/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                           | ![GitHub](https://img.shields.io/github/watchers/topgrade-rs/topgrade?label=%20&style=flat-square)                                          | ![GitHub](https://img.shields.io/github/watchers/rami3l/pacaptr?label=%20&style=flat-square)                                               | ![GitHub](https://img.shields.io/github/watchers/icy/pacapt?label=%20&style=flat-square)                                                     | ![GitHub](https://img.shields.io/github/watchers/emilengler/sysget?label=%20&style=flat-square)          |
| Contributors                 | ![GitHub](https://img.shields.io/github/contributors/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/contributors/topgrade-rs/topgrade?label=%20&style=flat-square)                                      | ![GitHub](https://img.shields.io/github/contributors/rami3l/pacaptr?label=%20&style=flat-square)                                           | ![GitHub](https://img.shields.io/github/contributors/icy/pacapt?label=%20&style=flat-square)                                                 | ![GitHub](https://img.shields.io/github/contributors/emilengler/sysget?label=%20&style=flat-square)      |
| Commit activity              | ![GitHub](https://img.shields.io/github/commit-activity/m/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                  | ![GitHub](https://img.shields.io/github/commit-activity/m/topgrade-rs/topgrade?label=%20&style=flat-square)                                 | ![GitHub](https://img.shields.io/github/commit-activity/m/rami3l/pacaptr?label=%20&style=flat-square)                                      | ![GitHub](https://img.shields.io/github/commit-activity/m/icy/pacapt?label=%20&style=flat-square)                                            | ![GitHub](https://img.shields.io/github/commit-activity/m/emilengler/sysget?label=%20&style=flat-square) |
| Commits since latest release | ![GitHub](https://img.shields.io/github/commits-since/kdeldycke/meta-package-manager/latest?style=flat-square)                                         | ![GitHub](https://img.shields.io/github/commits-since/topgrade-rs/topgrade/latest?style=flat-square)                                        | ![GitHub](https://img.shields.io/github/commits-since/rami3l/pacaptr/latest?style=flat-square)                                             | ![GitHub](https://img.shields.io/github/commits-since/icy/pacapt/latest?style=flat-square)                                                   | ![GitHub](https://img.shields.io/github/commits-since/emilengler/sysget/latest?style=flat-square)        |
| Last release date            | ![GitHub](https://img.shields.io/github/release-date/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/release-date/topgrade-rs/topgrade?label=%20&style=flat-square)                                      | ![GitHub](https://img.shields.io/github/release-date/rami3l/pacaptr?label=%20&style=flat-square)                                           | ![GitHub](https://img.shields.io/github/release-date/icy/pacapt?label=%20&style=flat-square)                                                 | ![GitHub](https://img.shields.io/github/release-date/emilengler/sysget?label=%20&style=flat-square)      |
| Last commit                  | ![GitHub](https://img.shields.io/github/last-commit/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                        | ![GitHub](https://img.shields.io/github/last-commit/topgrade-rs/topgrade?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/last-commit/rami3l/pacaptr?label=%20&style=flat-square)                                            | ![GitHub](https://img.shields.io/github/last-commit/icy/pacapt?label=%20&style=flat-square)                                                  | ![GitHub](https://img.shields.io/github/last-commit/emilengler/sysget?label=%20&style=flat-square)       |
| Open issues                  | ![GitHub](https://img.shields.io/github/issues-raw/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                         | ![GitHub](https://img.shields.io/github/issues-raw/topgrade-rs/topgrade?label=%20&style=flat-square)                                        | ![GitHub](https://img.shields.io/github/issues-raw/rami3l/pacaptr?label=%20&style=flat-square)                                             | ![GitHub](https://img.shields.io/github/issues-raw/icy/pacapt?label=%20&style=flat-square)                                                   | ![GitHub](https://img.shields.io/github/issues-raw/emilengler/sysget?label=%20&style=flat-square)        |
| Open PRs                     | ![GitHub](https://img.shields.io/github/issues-pr-raw/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                      | ![GitHub](https://img.shields.io/github/issues-pr-raw/topgrade-rs/topgrade?label=%20&style=flat-square)                                     | ![GitHub](https://img.shields.io/github/issues-pr-raw/rami3l/pacaptr?label=%20&style=flat-square)                                          | ![GitHub](https://img.shields.io/github/issues-pr-raw/icy/pacapt?label=%20&style=flat-square)                                                | ![GitHub](https://img.shields.io/github/issues-pr-raw/emilengler/sysget?label=%20&style=flat-square)     |
| Forks                        | ![GitHub](https://img.shields.io/github/forks/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                              | ![GitHub](https://img.shields.io/github/forks/topgrade-rs/topgrade?label=%20&style=flat-square)                                             | ![GitHub](https://img.shields.io/github/forks/rami3l/pacaptr?label=%20&style=flat-square)                                                  | ![GitHub](https://img.shields.io/github/forks/icy/pacapt?label=%20&style=flat-square)                                                        | ![GitHub](https://img.shields.io/github/forks/emilengler/sysget?label=%20&style=flat-square)             |
| Dependencies freshness       | ![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/pypi/meta-package-manager?label=%20&style=flat-square) | ![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/cargo/topgrade?label=%20&style=flat-square) | ![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/cargo/pacaptr?label=%20&style=flat-square) | ![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/homebrew/pacapt?label=%20&style=flat-square) | -                                                                                                        |

## Popularity

[![Star History Chart](https://api.star-history.com/svg?repos=kdeldycke/meta-package-manager,topgrade-rs/topgrade,rami3l/pacaptr,icy/pacapt,emilengler/sysget&type=Date)](https://star-history.com/#kdeldycke/meta-package-manager&topgrade-rs/topgrade&rami3l/pacaptr&icy/pacapt&emilengler/sysget&Date)

| Metrics         | `mpm`                                                                                                                                           | `topgrade`[^1]                                                                                                                       | `pacaptr`[^2]                                                                                                                       | `pacapt`[^3]                                                                                                                          | `sysget`[^4]                                                                                 |
| --------------- | :---------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------- |
| Stars           | ![GitHub](https://img.shields.io/github/stars/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/stars/topgrade-rs/topgrade?label=%20&style=flat-square)                                      | ![GitHub](https://img.shields.io/github/stars/rami3l/pacaptr?label=%20&style=flat-square)                                           | ![GitHub](https://img.shields.io/github/stars/icy/pacapt?label=%20&style=flat-square)                                                 | ![GitHub](https://img.shields.io/github/stars/emilengler/sysget?label=%20&style=flat-square) |
| SourceRank      | ![Libraries.io SourceRank](https://img.shields.io/librariesio/sourcerank/pypi/meta-package-manager?label=%20&style=flat-square)                 | ![Libraries.io SourceRank](https://img.shields.io/librariesio/sourcerank/cargo/topgrade?label=%20&style=flat-square)                 | ![Libraries.io SourceRank](https://img.shields.io/librariesio/sourcerank/cargo/pacaptr?label=%20&style=flat-square)                 | ![Libraries.io SourceRank](https://img.shields.io/librariesio/sourcerank/homebrew/pacapt?label=%20&style=flat-square)                 | -                                                                                            |
| Dependent repos | ![Dependent repos (via libraries.io)](https://img.shields.io/librariesio/dependent-repos/pypi/meta-package-manager?label=%20&style=flat-square) | ![Dependent repos (via libraries.io)](https://img.shields.io/librariesio/dependent-repos/cargo/topgrade?label=%20&style=flat-square) | ![Dependent repos (via libraries.io)](https://img.shields.io/librariesio/dependent-repos/cargo/pacaptr?label=%20&style=flat-square) | ![Dependent repos (via libraries.io)](https://img.shields.io/librariesio/dependent-repos/homebrew/pacapt?label=%20&style=flat-square) | -                                                                                            |

## Metadata

| Metadata            | `mpm`                                                                                                                                             | `topgrade`[^1]                                                                                                                          | `pacaptr`[^2]                                                                                                                     | `pacapt`[^3]                                                                                                                  | `sysget`[^4]                                                                                                                         |
| ------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------- |
| License             | ![GitHub](https://img.shields.io/github/license/kdeldycke/meta-package-manager?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/license/topgrade-rs/topgrade?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/license/rami3l/pacaptr?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/license/icy/pacapt?label=%20&style=flat-square)                                       | ![GitHub](https://img.shields.io/github/license/emilengler/sysget?label=%20&style=flat-square)                                       |
| Main language       | ![GitHub](https://img.shields.io/github/languages/top/kdeldycke/meta-package-manager?style=flat-square)                                           | ![GitHub](https://img.shields.io/github/languages/top/topgrade-rs/topgrade?style=flat-square)                                           | ![GitHub](https://img.shields.io/github/languages/top/rami3l/pacaptr?style=flat-square)                                           | ![GitHub](https://img.shields.io/github/languages/top/icy/pacapt?style=flat-square)                                           | ![GitHub](https://img.shields.io/github/languages/top/emilengler/sysget?style=flat-square)                                           |
| Latest version      | ![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/kdeldycke/meta-package-manager?label=%20&sort=semver&style=flat-square) | ![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/topgrade-rs/topgrade?label=%20&sort=semver&style=flat-square) | ![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/rami3l/pacaptr?label=%20&sort=semver&style=flat-square) | ![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/icy/pacapt?label=%20&sort=semver&style=flat-square) | ![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/emilengler/sysget?label=%20&sort=semver&style=flat-square) |
| Version benchmarked | `5.15.0`                                                                                                                                          | `10.1.2`                                                                                                                                | `0.15.2`                                                                                                                          | `3.0.7`                                                                                                                       | `2.3`                                                                                                                                |
| Benchmark date      | 2024-02                                                                                                                                           | 2022-11                                                                                                                                 | 2022-04                                                                                                                           | 2022-04                                                                                                                       | 2022-04                                                                                                                              |

## Project's URL

[^1]: <https://github.com/topgrade-rs/topgrade>

[^2]: <https://github.com/rami3l/pacaptr>

[^3]: <https://github.com/icy/pacapt>

[^4]: <https://github.com/emilengler/sysget>

[^bsd_without_macos]: BSD: FreeBSD, NetBSD, OpenBSD, SunOS.

[^linux]: Linux: Linux, Windows Subsystem for Linux v2.

[^unix]: Unix: AIX, Cygwin, GNU/Hurd, Solaris, Windows Subsystem for Linux v1.
