# Alternatives

Attempting to unifying all package managers is a Sisyphean task.

But it seems I was not the only one trying to solve that problem so there might be a greater need
for such tools out there. Here is a list of some related projects I stumbled into.

## Benchmark

| Package manager | `mpm` | `topgrade`[^1] |`pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| --------------- | :---: | :-----------:| :-----------: | :----------: | :----------: |
| `0install`      |       |               |            |            |              |
| `antigen` |       |        ✓       |             |           |              |
| `antibody` |       |        ✓       |             |           |              |
| `apm`           |   ✓   |    ✓          |             |             |              |
| `apk`           |       |               |   ✓          |    ✓       |              |
| `apt`           |   ✓   |      ✓          |    ✓          |     ✓       |      ✓       |
| `apt-cyg`       |       |               |            |    ✓       |              |
| `apt-mint`      |   ✓   |              |             |             |              |
| `asdf`         |     |        ✓       |             |             |              |
| `bin`         |     |        ✓       |             |             |              |
| `brew`          |   ✓   |      ✓           |     ✓          |     ✓       |      ✓       |
| `cargo`          |     |      ✓           |            |            |             |
| `cask`          |   ✓   |      ✓           |     ✓          |     ✓       |      ✓       |
| `cave`          |       |               |            |    ✓       |              |
| `chezmoi`       |     |      ✓           |            |            |             |
| `chocolatey`    |   ✓   |    ✓          |    ✓           |             |              |
| `choosenim`|     |      ✓           |            |            |             |
| `chromebrew`    |       |               |            |            |      ✓       |
| `composer`      |   ✓   |        ✓      |             |             |              |
| `containers`|       |        ✓       |             |           |              |
| `conda`         |       |        ✓       |   ✓          |    ✓       |              |
| `dein`         |       |        ✓       |             |           |              |
| `deno` |       |        ✓       |             |           |              |
| `dnf`           |   ✓   |              |    ✓          |             |      ✓       |
| `dotnet` |       |        ✓       |             |           |              |
| `emacs` |       |        ✓       |             |           |              |
| `emerge`        |   ✓   |        ✓       |    ✓          |     ✓       |      ✓       |
| `eopkg`         |       |               |            |            |      ✓       |
| `etc-update` |       |        ✓       |             |           |              |
| `fwupdmgr` |       |        ✓       |             |           |              |
| `fisher` |       |        ✓       |             |           |              |
| `flatpak`       |   ✓   |   ✓           |             |             |      ✓       |
| `flutter` |       |        ✓       |             |           |              |
| `fossil` |       |        ✓       |             |           |              |
| `gem`           |   ✓   |    ✓           |             |             |      ✓       |
| `gcloud` |       |        ✓       |             |           |              |
| `git` |       |        ✓       |             |           |              |
| `gnome-shell` |       |        ✓       |             |           |              |
| `go` |       |        ✓       |             |           |              |
| `guix`          |       |               |            |            |      ✓       |
| `haxelib` |       |        ✓       |             |           |              |
| `home-manager` |       |        ✓       |             |           |              |
| `jetpack` |       |        ✓       |             |           |              |
| `kakoune` |       |        ✓       |             |           |              |
| `krew` |       |        ✓       |             |           |              |
| `macports`      |       |      ✓         |    ✓         |    ✓       |      ✓       |
| `mas`           |   ✓   |       ✓       |             |             |              |
| `macos`           |      |       ✓       |             |             |              |
| `micro` |       |        ✓       |             |           |              |
| `myrepos` |       |        ✓       |             |           |              |
| `neobundle`         |       |        ✓       |             |           |              |
| `nix`           |       |       ✓        |            |            |      ✓       |
| `npm`           |   ✓   |       ✓       |             |             |      ✓       |
| `oh-my-zsh` |       |        ✓       |             |           |              |
| `opam` |       |        ✓       |             |           |              |
| `opkg`          |   ✓   |              |             |     ✓       |              |
| `pacman`        |   ✓   |     ✓         |             |     ✓       |      ✓       |
| `pacstall` |       |        ✓       |             |           |              |
| `paru`         |       |        ✓       |             |           |              |
| `pearl` |       |        ✓       |             |           |              |
| `pikaur`         |       |        ✓       |             |           |              |
| `pihole`         |       |        ✓       |             |           |              |
| `pip`           |   ✓   |        ✓       |    ✓          |             |      ✓       |
| `pipx`           |     |        ✓       |              |             |            |
| `pkg`           |       |       ✓        |            |            |      ✓       |
| `pkg-mgr`       |       |               |            |            |      ✓       |
| `pkg-tools`     |       |               |            |    ✓       |              |
| `pkgin`           |       |       ✓        |            |            |             |
| `pkgng`         |       |               |            |    ✓       |              |
| `plug`         |       |        ✓       |             |           |              |
| `pnpm`           |     |        ✓       |              |             |            |
| `podman`           |     |        ✓       |              |             |            |
| `powershell`           |     |        ✓       |              |             |            |
| `raco`           |     |        ✓       |              |             |            |
| `rtcl`           |     |        ✓       |              |             |            |
| `rustup`           |     |        ✓       |              |             |            |
| `scoop`         |       |         ✓       |     ✓       |            |      ✓       |
| `sdkman`         |       |         ✓       |          |            |           |
| `sheldon`         |       |         ✓       |          |            |           |
| `silnite`         |       |         ✓       |          |            |           |
| `slapt-get`     |       |               |            |            |      ✓       |
| `snap`          |   ✓   |     ✓           |             |             |      ✓       |
| `spack`         |       |               |            |            |              |
| `spicetify`         |       |         ✓       |          |            |           |
| `steamcmd`      |   ✓   |              |             |             |              |
| `stack`         |       |         ✓       |          |            |           |
| `sun-tools`     |       |               |            |    ✓       |              |
| `swupd`         |       |               |            |    ✓       |              |
| `system`         |       |         ✓       |          |            |           |
| `tazpkg`        |       |               |            |    ✓       |              |
| `tldr`         |       |         ✓       |          |            |           |
| `tlmgr`         |       |        ✓       |     ✓        |    ✓       |              |
| `toolbx`         |       |        ✓       |             |           |              |
| `trizen`         |       |        ✓       |             |           |              |
| `vagrant`         |       |        ✓       |             |           |              |
| `vcpkg`         |       |        ✓       |             |           |              |
| `vundle`         |       |        ✓       |             |           |              |
| `nala`         |       |               |             |           |              |
| `voom`         |       |        ✓       |             |           |              |
| `vscode`        |   ✓   |              |             |             |              |
| `winget`        |      |       ✓         |           |             |              |
| `wsl`         |       |        ✓       |             |           |              |
| `xbps`          |       |               |   ✓          |    ✓       |      ✓       |
| `yadm`         |       |        ✓       |             |           |              |
| `yarn`          |   ✓   |       ✓        |             |             |              |
| `yay`         |       |        ✓       |             |           |              |
| `yum`           |   ✓   |              |             |     ✓       |      ✓       |
| `zim`         |       |        ✓       |             |           |              |
| `zinit`         |       |        ✓       |             |           |              |
| `zplug`         |       |        ✓       |             |           |              |
| `zr`         |       |        ✓       |             |           |              |
| `zypper`        |   ✓   |              |    ✓          |     ✓       |      ✓       |

| Operating system | `mpm` |  `topgrade`[^1] | `pacaptr`[^2] |`pacapt`[^3] | `sysget`[^4] |
| ---------------- | :---: | :----------:| :----------: |:----------: | :----------: |
| macOS            |   🍎   |     🍎         |  🍎   |           🍎       |      🍎       |
| Linux            |   🐧   |      🐧       |   🐧      |      🐧       |  🐧       |
| Windows          |   🪟   |        🪟      |  🪟   |            |              |

| Operations              | `mpm` |  `topgrade`[^1] |`pacaptr`[^2] |`pacapt`[^3] | `sysget`[^4] |
| ----------------------- | :---: | :----------:| :----------: |:----------: | :----------: |
| List available managers |   ✓   |              |           |            |              |
| List installed packages |   ✓   |              |     ✓      |            |      ✓       |
| List outdated packages  |   ✓   |              |     ✓      |            |      ✓       |
| Search packages         |   ✓   |              |      ✓     |    ✓       |      ✓       |
| Install a package       |   ✓   |              |       ✓    |    ✓       |      ✓       |
| Remove a package        |       |               |        ✓  |    ✓       |      ✓       |
| Upgrade single package  |   ✓   |              |       ✓    |            |      ✓       |
| Upgrade all packages    |   ✓   |       ✓          |       ✓    |    ✓       |      ✓       |
| Sync                    |   ✓   |              |       ✓    |    ✓       |      ✓       |
| Cleanup: caches         |   ✓   |        ✓         |     ✓      |    ✓       |      ✓       |
| Cleanup: orphans        |   ✓   |       ✓          |     ✓      |    ✓       |      ✓       |
| Backup                  |   ✓   |              |           |            |              |
| Restore                 |   ✓   |              |           |            |              |

| Features                              | `mpm` |  `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| ------------------------------------- | :---: | :----------:| :----------: | :----------: | :----------: |
| Package manager autodetection         |   ✓   |        ✓        |            |            |              |
| Unified CLI and options               |   ✓   |       ✓       |     ✓           |      ✓          |      ✓       |
| Multi-PM execution                    |   ✓   |       ✓        |            |            |              |
| Package manager priority              |   ✓   |              |            |            |              |
| Consolidated output                   |   ✓   |              |            |            |              |
| Configurable output                   |   ✓   |              |            |            |              |
| Sortable output                       |   ✓   |              |            |            |              |
| Colored output                        |   ✓   |      ✓          |            |            |              |
| JSON export                           |   ✓   |              |            |            |              |
| CSV export                            |   ✓   |              |            |            |              |
| Markup export                         |   ✓   |              |            |            |              |
| Configuration file                    |   ✓   |       ✓         |       ✓      |            |      ✓       |
| Non-interactive                       |   ✓   |       ✓        |     ✓         |            |              |
| Dry-run                               |   ✓   |       ✓          |     ✓         |            |              |
| Sudo elevation             |   ✓   |         ✓        |      ✓       |            |              |
| Desktop notifications                |      |        ✓      |             |            |              |
| Bash auto-completion                  |   ✓   |              |            |            |              |
| Zsh auto-completion                   |   ✓   |              |            |            |              |
| Fish auto-completion                  |   ✓   |              |            |            |              |
| [XKCD #1654](https://xkcd.com/1654/)  |   ✓   |              |            |            |              |
| [Xbar/SwiftBar plugin](bar-plugin.md) |   ✓   |              |            |            |              |

| Metadata            |  `mpm`  |   `topgrade`[^1] | `pacaptr`[^2] | `pacapt`[^3] | `sysget`[^4] |
| ------------------- | :----- | :---------- | :---------- |:---------- | :---------- |
| License             | GPL-2.0 |    GPL-3.0         |  GPL-3.0         |   Custom    |   GPL-3.0    |
| Implementation      | Python  |       Rust      |  Rust         |   Shell     |     C++      |
| Version benchmarked | `5.0.0` |    `8.3.1`        | `0.15.2`           |  `3.0.7`    |    `2.3`     |
| Benchmark date      | 2022-04 |      2022-04      |    2022-04       |  2022-04    |   2022-04    |


[^1]: <https://github.com/r-darwish/topgrade>

[^2]: <https://github.com/rami3l/pacaptr>

[^3]: <https://github.com/icy/pacapt>

[^4]: <https://github.com/emilengler/sysget>