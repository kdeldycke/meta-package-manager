# Alternatives

Attempting to unifying all package managers is a Sisyphean task.

But it seems I was not the only one trying to solve that problem so there might be a greater need
for such tools out there. Here is a list of some related projects I stumbled into.

## Benchmark

| Package manager | `mpm` | `pacapt`[^1] | `sysget`[^2] |
| --------------- | :---: | :---------------------------------------: | :----------------------------------------------: |
| `0install`      |       |                                           |                                                  |
| `apm`           |   ✓   |                                           |                                                  |
| `apk`           |       |                     ✓                     |                                                  |
| `apt`           |   ✓   |                     ✓                     |                        ✓                         |
| `apt-cyg`       |       |                     ✓                     |                                                  |
| `apt-mint`      |   ✓   |                                           |                                                  |
| `brew`          |   ✓   |                     ✓                     |                        ✓                         |
| `cask`          |   ✓   |                     ✓                     |                        ✓                         |
| `cave`          |       |                     ✓                     |                                                  |
| `chocolatey`    |   ✓   |                                           |                                                  |
| `chromebrew`    |       |                                           |                        ✓                         |
| `composer`      |   ✓   |                                           |                                                  |
| `conda`         |       |                     ✓                     |                                                  |
| `dnf`           |   ✓   |                                           |                        ✓                         |
| `emerge`        |   ✓   |                     ✓                     |                        ✓                         |
| `eopkg`         |       |                                           |                        ✓                         |
| `flatpak`       |   ✓   |                                           |                        ✓                         |
| `gem`           |   ✓   |                                           |                        ✓                         |
| `guix`          |       |                                           |                        ✓                         |
| `macports`      |       |                     ✓                     |                        ✓                         |
| `mas`           |   ✓   |                                           |                                                  |
| `nix`           |       |                                           |                        ✓                         |
| `npm`           |   ✓   |                                           |                        ✓                         |
| `opkg`          |   ✓   |                     ✓                     |                                                  |
| `pacman`        |   ✓   |                     ✓                     |                        ✓                         |
| `pip`           |   ✓   |                                           |                        ✓                         |
| `pkg`           |       |                                           |                        ✓                         |
| `pkg_mgr`       |       |                                           |                        ✓                         |
| `pkg_tools`     |       |                     ✓                     |                                                  |
| `pkgng`         |       |                     ✓                     |                                                  |
| `slapt-get`     |       |                                           |                        ✓                         |
| `snap`          |   ✓   |                                           |                        ✓                         |
| `spack`         |       |                                           |                                                  |
| `steamcmd`      |   ✓   |                                           |                                                  |
| `sun_tools`     |       |                     ✓                     |                                                  |
| `swupd`         |       |                     ✓                     |                                                  |
| `tazpkg`        |       |                     ✓                     |                                                  |
| `tlmgr`         |       |                     ✓                     |                                                  |
| `vscode`        |   ✓   |                                           |                                                  |
| `xbps`          |       |                     ✓                     |                        ✓                         |
| `yarn`          |   ✓   |                                           |                                                  |
| `yum`           |   ✓   |                     ✓                     |                        ✓                         |
| `zypper`        |   ✓   |                     ✓                     |                        ✓                         |

| Operating system | `mpm` |`pacapt`[^1] | `sysget`[^2] |
| ---------------- | :---: | :---------------------------------------: | :----------------------------------------------: |
| macOS            |   🍎   |                     🍎                     |                        🍎                         |
| Linux            |   🐧   |                     🐧                     |                        🐧                         |
| Windows          |   🪟   |                                           |                                                  |

| Operations              | `mpm` | `pacapt`[^1] | `sysget`[^2] |
| ----------------------- | :---: | :---------------------------------------: | :----------------------------------------------: |
| List available managers |   ✓   |                                           |                                                  |
| List installed packages |   ✓   |                                           |                        ✓                         |
| List outdated packages  |   ✓   |                                           |                        ✓                         |
| Search packages         |   ✓   |                     ✓                     |                        ✓                         |
| Install a package       |   ✓   |                     ✓                     |                        ✓                         |
| Remove a package        |       |                     ✓                     |                        ✓                         |
| Upgrade single package  |   ✓   |                                           |                        ✓                         |
| Upgrade all packages    |   ✓   |                     ✓                     |                        ✓                         |
| Sync                    |   ✓   |                     ✓                     |                        ✓                         |
| Cleanup: caches         |   ✓   |                     ✓                     |                        ✓                         |
| Cleanup: orphans        |   ✓   |                     ✓                     |                        ✓                         |
| Backup                  |   ✓   |                                           |                                                  |
| Restore                 |   ✓   |                                           |                                                  |

| Features                              | `mpm` | `pacapt`[^1] | `sysget`[^2] |
| ------------------------------------- | :---: | :---------------------------------------: | :----------------------------------------------: |
| Package manager autodetection         |   ✓   |                                           |                                                  |
| Unified CLI and options               |   ✓   |                                           |                        ✓                         |
| Multi-PM execution                    |   ✓   |                                           |                                                  |
| Package manager priority              |   ✓   |                                           |                                                  |
| Consolidated output                   |   ✓   |                                           |                                                  |
| Configurable output                   |   ✓   |                                           |                                                  |
| Sortable output                       |   ✓   |                                           |                                                  |
| Colored output                        |   ✓   |                                           |                                                  |
| JSON export                           |   ✓   |                                           |                                                  |
| CSV export                            |   ✓   |                                           |                                                  |
| Markup export                         |   ✓   |                                           |                                                  |
| Configuration file                    |   ✓   |                                           |                        ✓                         |
| Dry-run                               |   ✓   |                                           |                                                  |
| Sudo                                  |   ✓   |                                           |                                                  |
| Bash auto-completion                  |   ✓   |                                           |                                                  |
| Zsh auto-completion                   |   ✓   |                                           |                                                  |
| Fish auto-completion                  |   ✓   |                                           |                                                  |
| [XKCD #1654](https://xkcd.com/1654/)  |   ✓   |                                           |                                                  |
| [Xbar/SwiftBar plugin](bar-plugin.md) |   ✓   |                                           |                                                  |

| Metadata            |  `mpm`  | `pacapt`[^1] | `sysget`[^2] |
| ------------------- | :-----: | :---------------------------------------: | :----------------------------------------------: |
| License             | GPL-2.0 |                  Custom                   |                     GPL-3.0                      |
| Implementation      | Python  |                   Shell                   |                       C++                        |
| Version benchmarked | `5.0.0` |                  `3.0.7`                  |                      `2.3`                       |
| Benchmark date      | 2022-04 |                  2022-04                  |                     2022-04                      |

[^1]: <https://github.com/icy/pacapt>
[^2]: <https://github.com/emilengler/sysget>