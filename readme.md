<p align="center">
  <a href="https://mpm.run">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-dark.png">
      <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-light.png">
      <img src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-light.png" alt="Meta Package Manager">
    </picture>
  </a>
</p>

<a href="https://xkcd.com/1654/" alt="XKCD #1654: Universal Install Script">
<img align="right" width="20%" height="20%" src="http://imgs.xkcd.com/comics/universal_install_script.png"/>
</a>

[![Last release](https://img.shields.io/pypi/v/meta-package-manager.svg)](https://pypi.org/project/meta-package-manager)
[![Python versions](https://img.shields.io/pypi/pyversions/meta-package-manager.svg)](https://pypi.org/project/meta-package-manager)
[![Downloads](https://static.pepy.tech/badge/meta_package_manager/month)](https://pepy.tech/projects/meta_package_manager)
[![Unittests status](https://img.shields.io/github/actions/workflow/status/kdeldycke/meta-package-manager/tests.yaml?branch=main&label=%F0%9F%94%AC%20Tests)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain)
[![Documentation status](https://img.shields.io/github/actions/workflow/status/kdeldycke/meta-package-manager/docs.yaml?branch=main&label=%F0%9F%93%9A%20Docs)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/docs.yaml?query=branch%3Amain)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.6809571.svg)](https://doi.org/10.5281/zenodo.6809571)

**What is Meta Package Manager?**

- snapshots every package on your machine to one file, and restores it on a new one
- provides the `mpm` CLI, a wrapper around all package managers
- `mpm` is like [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), but for package managers instead of videos
- `mpm` solves [XKCD #1654 - *Universal Install Script*](https://xkcd.com/1654/)

---

## Quick start

Thanks to [`uv`](https://docs.astral.sh/uv/getting-started/installation/), you can run `mpm` on any platform in one command, without installation or venv:

```shell-session
$ uvx meta-package-manager
```

Take everything installed on this machine, whichever package manager put it there, and write it to a single file:

```shell-session
$ mpm dump packages.toml
```

On the next machine, put it all back:

```shell-session
$ mpm restore packages.toml
```

## Features

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-outdated-cli.png"/>

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-managers-cli.png"/>

- [Snapshot installed packages](https://mpm.run/cli-parameters/#mpm-dump) to a TOML manifest or a Brewfile, across every manager at once.
- [Restore that manifest](https://mpm.run/cli-parameters/#mpm-restore) on another machine, and get the same set of packages back.
- Inventory and list all [package managers](https://mpm.run/cli-parameters/#mpm-managers) available on the system.
- Supports macOS, Linux and Windows.
- [Standalone executables](#executables) for Linux, macOS and Windows.
- [List installed packages](https://mpm.run/cli-parameters/#mpm-installed).
- [List duplicate installed packages](https://mpm.run/duplicates/).
- [Search for packages](https://mpm.run/cli-parameters/#mpm-search).
- [Install a package](https://mpm.run/cli-parameters/#mpm-install).
- [Remove a package](https://mpm.run/cli-parameters/#mpm-remove).
- [List outdated packages](https://mpm.run/cli-parameters/#mpm-outdated).
- [List orphaned packages](https://mpm.run/cli-parameters/#mpm-orphans).
- [Sync local package infos](https://mpm.run/cli-parameters/#mpm-sync).
- [Diagnose the health of package managers](https://mpm.run/cli-parameters/#mpm-doctor).
- [Upgrade all outdated packages](https://mpm.run/cli-parameters/#mpm-upgrade).
- [Mitigate supply-chain attacks](https://mpm.run/cooldown/) with a release-age cooldown that refuses too-recent versions: `mpm --cooldown "7 days" upgrade --all`.
- [Software Bill of Materials](https://mpm.run/cli-parameters/#mpm-sbom): export installed packages to [SPDX](https://spdx.dev) and [CycloneDX](https://cyclonedx.org) SBOM files.
- Pin-point commands to a [subset of package managers](https://mpm.run/configuration/#selecting-managers) (include/exclude selectors).
- Support plain, versioned and [purl](https://github.com/package-url/purl-spec) package specifiers.
- Export output to [JSON or user-friendly tables](https://mpm.run/cli-parameters/#mpm).
- [Shell auto-completion](https://mpm.run/install/) for Bash, Zsh and Fish.
- Provides a [SwiftBar/Xbar plugin](https://mpm.run/bar-plugin/) for
  friendly macOS integration.
- Provides a [GNOME Shell extension](https://mpm.run/gnome-shell/) for
  friendly Linux desktop integration.
- Because `mpm` tries to wrap all other package managers, it became another pathological case of [XKCD #927: Standards](https://xkcd.com/927/)

## Supported package managers

One CLI to rule them all. Every manager below links to its own documentation page, and `mpm` [runs them concurrently](https://mpm.run/concurrency/) bar the few that queue on a shared backend.

<!-- mirror-src
from meta_package_manager._docs import operation_matrix

print(operation_matrix()[0])
-->

| Package manager                                                                        | Version         | Cooldown |   Platforms   | `installed` | `outdated` | `orphans` | `search` | `install` | `upgrade` | `upgrade_all` | `remove` | `sync` | `cleanup` | `doctor` |
| :------------------------------------------------------------------------------------- | :-------------- | :------: | :-----------: | :---------: | :--------: | :-------: | :------: | :-------: | :-------: | :-----------: | :------: | :----: | :-------: | :------: |
| [`am`](https://mpm.run/managers/am/)                                                   | >= 10.4         |          |      🐧       |      ✓      |            |           |          |           |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`antidote`](https://mpm.run/managers/antidote/)                                       | >= 2.2          |          |     🐧 🍎     |      ✓      |     ✓      |           |          |     ✓     |           |       ✓       |    ✓     |        |           |          |
| [`antigen`](https://mpm.run/managers/antigen/)                                         | >= 2            |          |     🐧 🍎     |      ✓      |            |           |          |           |           |       ✓       |    ✓     |        |           |          |
| [`apk`](https://mpm.run/managers/apk/)                                                 | >= 2.10         |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`apm`](https://mpm.run/managers/apm/) [⚠️](https://mpm.run/managers/apm/)             | >= 1            |          |  🅱️ 🐧 🍎 🪟  |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`apt`](https://mpm.run/managers/apt/)                                                 | >= 1            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`apt-cyg`](https://mpm.run/managers/apt-cyg/) [⚠️](https://mpm.run/managers/apt-cyg/) |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |   ✓    |           |          |
| [`apt-mint`](https://mpm.run/managers/apt-mint/)                                       | >= 1            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`aptitude`](https://mpm.run/managers/aptitude/)                                       | >= 0.4.11.4     |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`asdf`](https://mpm.run/managers/asdf/)                                               | >= 0.16         |          |     🐧 🍎     |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`basalt`](https://mpm.run/managers/basalt/)                                           | >= 0.10         |          |     🐧 🍎     |      ✓      |            |           |          |     ✓     |           |               |    ✓     |        |           |          |
| [`bin`](https://mpm.run/managers/bin/)                                                 | >= 0.27         |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |           |     ✓     |       ✓       |    ✓     |        |           |          |
| [`bob`](https://mpm.run/managers/bob/)                                                 |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`bpkg`](https://mpm.run/managers/bpkg/)                                               |                 |          |     🐧 🍎     |             |            |           |          |     ✓     |           |               |          |        |           |          |
| [`brew`](https://mpm.run/managers/brew/)                                               | >= 6            |          |     🐧 🍎     |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`bun`](https://mpm.run/managers/bun/)                                                 | >= 1.2          |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`cargo`](https://mpm.run/managers/cargo/)                                             | >= 1            |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |        |           |          |
| [`cask`](https://mpm.run/managers/cask/)                                               | >= 6            |          |      🍎       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`cave`](https://mpm.run/managers/cave/)                                               |                 |          |               |      ✓      |            |     ✓     |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`choco`](https://mpm.run/managers/choco/)                                             | >= 2            |          |      🪟       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`choosenim`](https://mpm.run/managers/choosenim/)                                     | >= 0.8.4        |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |     ✓     |               |    ✓     |        |           |          |
| [`chromebrew`](https://mpm.run/managers/chromebrew/)                                   |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`claude-code-plugins`](https://mpm.run/managers/claude-code-plugins/)                 |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |               |    ✓     |   ✓    |     ✓     |          |
| [`clib`](https://mpm.run/managers/clib/)                                               |                 |          |     🐧 🍎     |             |            |           |    ✓     |     ✓     |           |               |    ✓     |        |           |          |
| [`composer`](https://mpm.run/managers/composer/)                                       | >= 1.4          |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |    ✓     |
| [`conda`](https://mpm.run/managers/conda/)                                             | >= 4.6          |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`cpan`](https://mpm.run/managers/cpan/)                                               | >= 1.64         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |          |        |           |          |
| [`deb-get`](https://mpm.run/managers/deb-get/)                                         |                 |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`dkp-pacman`](https://mpm.run/managers/dkp-pacman/)                                   | >= 6            |          |     🐧 🍎     |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`dnf`](https://mpm.run/managers/dnf/)                                                 | >= 4            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`dnf5`](https://mpm.run/managers/dnf5/)                                               | >= 5            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`dotnet`](https://mpm.run/managers/dotnet/)                                           | >= 8.0.400      |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`elan`](https://mpm.run/managers/elan/)                                               | >= 4            |          |   🐧 🍎 🪟    |      ✓      |            |     ✓     |          |     ✓     |           |               |    ✓     |        |     ✓     |          |
| [`emacs`](https://mpm.run/managers/emacs/)                                             |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |           |               |    ✓     |   ✓    |           |          |
| [`emerge`](https://mpm.run/managers/emerge/)                                           | >= 3            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`eopkg`](https://mpm.run/managers/eopkg/)                                             | >= 3.2          |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`fink`](https://mpm.run/managers/fink/)                                               |                 |          |      🍎       |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`fisher`](https://mpm.run/managers/fisher/)                                           | >= 4            |          |     🐧 🍎     |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`flatpak`](https://mpm.run/managers/flatpak/)                                         | >= 1.2          |    ✓     |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |    ✓     |
| [`fwupd`](https://mpm.run/managers/fwupd/)                                             | >= 1.9.5        |          |      🐧       |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |          |   ✓    |           |          |
| [`gcloud`](https://mpm.run/managers/gcloud/)                                           | >= 170          |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |     ✓     |           |       ✓       |    ✓     |        |           |          |
| [`gem`](https://mpm.run/managers/gem/)                                                 | >= 2.5          |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`getnf`](https://mpm.run/managers/getnf/)                                             |                 |          |     🐧 🍎     |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`gext`](https://mpm.run/managers/gext/)                                               | >= 0.11         |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`gh-ext`](https://mpm.run/managers/gh-ext/)                                           | >= 2            |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`ghcup`](https://mpm.run/managers/ghcup/)                                             | >= 0.2.1        |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |   ✓    |     ✓     |          |
| [`go`](https://mpm.run/managers/go/)                                                   | >= 1.16         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |           |               |          |        |           |          |
| [`guix`](https://mpm.run/managers/guix/)                                               |                 |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`gup`](https://mpm.run/managers/gup/)                                                 | >= 1.3.1        |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |           |     ✓     |       ✓       |    ✓     |        |           |          |
| [`haxelib`](https://mpm.run/managers/haxelib/)                                         | >= 4            |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`jpm`](https://mpm.run/managers/jpm/)                                                 |                 |          |   🐧 🍎 🪟    |             |            |           |          |     ✓     |           |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`julia`](https://mpm.run/managers/julia/)                                             |                 |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`juliaup`](https://mpm.run/managers/juliaup/)                                         | >= 1.21         |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`krew`](https://mpm.run/managers/krew/)                                               | >= 0.4          |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`lazy`](https://mpm.run/managers/lazy/)                                               | >= 11           |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |           |           |       ✓       |          |        |           |          |
| [`luarocks`](https://mpm.run/managers/luarocks/)                                       | >= 3.9.1        |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`lure`](https://mpm.run/managers/lure/)                                               | >= 0.1.3        |          |      🐧       |      ✓      |            |           |    ✓     |     ✓     |           |               |          |   ✓    |           |          |
| [`macports`](https://mpm.run/managers/macports/)                                       | >= 2            |          |      🍎       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`mamba`](https://mpm.run/managers/mamba/)                                             | >= 2            |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`mas`](https://mpm.run/managers/mas/)                                                 | >= 7            |    ✓     |      🍎       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`mason`](https://mpm.run/managers/mason/)                                             | >= 2            |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |     ✓     |               |    ✓     |   ✓    |           |          |
| [`micro`](https://mpm.run/managers/micro/)                                             | >= 2            |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`micromamba`](https://mpm.run/managers/micromamba/)                                   | >= 2            |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`miktex`](https://mpm.run/managers/miktex/)                                           | >= 22.3         |          |     🐧 🪟     |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`mise`](https://mpm.run/managers/mise/)                                               | >= 2025.5.10    |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`nala`](https://mpm.run/managers/nala/)                                               | >= 0.12.2       |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`nimble`](https://mpm.run/managers/nimble/)                                           | >= 0.22         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |   ✓    |           |          |
| [`nix`](https://mpm.run/managers/nix/)                                                 | >= 2            |          |     🐧 🍎     |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`npm`](https://mpm.run/managers/npm/)                                                 | >= 11.10        |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |    ✓     |
| [`oh-my-fish`](https://mpm.run/managers/oh-my-fish/)                                   | >= 6            |          |     🐧 🍎     |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`ollama`](https://mpm.run/managers/ollama/)                                           | >= 0.5          |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |               |    ✓     |        |           |          |
| [`opam`](https://mpm.run/managers/opam/)                                               | >= 2            |          |   🅱️ 🐧 🍎    |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`opkg`](https://mpm.run/managers/opkg/)                                               | >= 0.2          |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`pacaur`](https://mpm.run/managers/pacaur/) [⚠️](https://mpm.run/managers/pacaur/)    | >= 4            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`pacman`](https://mpm.run/managers/pacman/)                                           | >= 5            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`pacstall`](https://mpm.run/managers/pacstall/)                                       | >= 6            |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`pamac`](https://mpm.run/managers/pamac/)                                             | >= 11           |          |      🐧       |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`paru`](https://mpm.run/managers/paru/)                                               | >= 1.9.3        |    ✓     |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`pear`](https://mpm.run/managers/pear/)                                               | >= 1.10         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`pearl`](https://mpm.run/managers/pearl/)                                             |                 |          |     🐧 🍎     |      ✓      |            |           |    ✓     |     ✓     |     ✓     |               |    ✓     |        |           |          |
| [`pi`](https://mpm.run/managers/pi/)                                                   |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`pikaur`](https://mpm.run/managers/pikaur/)                                           | >= 1            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`pip`](https://mpm.run/managers/pip/)                                                 | >= 26.1         |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |    ✓     |
| [`pipx`](https://mpm.run/managers/pipx/)                                               | >= 1            |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`pipxu`](https://mpm.run/managers/pipxu/)                                             |                 |          |     🐧 🍎     |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`pixi`](https://mpm.run/managers/pixi/)                                               | >= 0.65         |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`pkcon`](https://mpm.run/managers/pkcon/)                                             | >= 0.7          |          |      🐧       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`pkg`](https://mpm.run/managers/pkg/)                                                 | >= 1.11         |          |               |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`pkg-tools`](https://mpm.run/managers/pkg-tools/)                                     |                 |          |               |      ✓      |            |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`pkgin`](https://mpm.run/managers/pkgin/)                                             |                 |          |               |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`pkgit`](https://mpm.run/managers/pkgit/)                                             | >= 1.2          |          |      🐧       |      ✓      |            |           |    ✓     |     ✓     |           |       ✓       |          |        |           |          |
| [`pkgm`](https://mpm.run/managers/pkgm/)                                               |                 |          |     🐧 🍎     |      ✓      |     ✓      |           |          |     ✓     |           |       ✓       |    ✓     |        |           |          |
| [`platformio-core`](https://mpm.run/managers/platformio-core/)                         |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |           |           |       ✓       |          |        |           |          |
| [`pnpm`](https://mpm.run/managers/pnpm/)                                               | >= 11           |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`ports`](https://mpm.run/managers/ports/)                                             |                 |          |               |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`pwsh-gallery`](https://mpm.run/managers/pwsh-gallery/)                               | >= 7.4          |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`pyenv`](https://mpm.run/managers/pyenv/)                                             | >= 2.3.13       |          |     🐧 🍎     |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |        |           |          |
| [`raco`](https://mpm.run/managers/raco/)                                               |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`roswell`](https://mpm.run/managers/roswell/)                                         | >= 22.12.14.113 |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |           |               |          |        |           |          |
| [`rustup`](https://mpm.run/managers/rustup/)                                           | >= 1.28         |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`scoop`](https://mpm.run/managers/scoop/)                                             | >= 0.2.4        |          |      🪟       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`sdkman`](https://mpm.run/managers/sdkman/)                                           | >= 5            |          |     🐧 🍎     |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`sfsu`](https://mpm.run/managers/sfsu/)                                               | >= 1.16         |          |      🪟       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`sheldon`](https://mpm.run/managers/sheldon/)                                         | >= 0.6          |          |     🐧 🍎     |             |            |           |          |           |           |       ✓       |    ✓     |        |           |          |
| [`skills`](https://mpm.run/managers/skills/)                                           |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |          |           |           |       ✓       |    ✓     |        |           |          |
| [`slapt-get`](https://mpm.run/managers/slapt-get/)                                     |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`snap`](https://mpm.run/managers/snap/)                                               | >= 2            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`soar`](https://mpm.run/managers/soar/)                                               | >= 0.12         |          |      🐧       |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`sorcery`](https://mpm.run/managers/sorcery/)                                         |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`spack`](https://mpm.run/managers/spack/)                                             | >= 1            |          |     🐧 🍎     |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |   ✓    |     ✓     |          |
| [`steamcmd`](https://mpm.run/managers/steamcmd/)                                       |                 |          | 🅱️ 🐧 🍎 ⨂ 🪟 |             |            |           |          |     ✓     |           |               |          |        |           |          |
| [`stew`](https://mpm.run/managers/stew/)                                               | >= 0.3          |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`sun-tools`](https://mpm.run/managers/sun-tools/)                                     |                 |          |               |      ✓      |            |           |          |           |           |               |    ✓     |        |           |          |
| [`swupd`](https://mpm.run/managers/swupd/) [⚠️](https://mpm.run/managers/swupd/)       |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |           |       ✓       |    ✓     |        |     ✓     |          |
| [`tazpkg`](https://mpm.run/managers/tazpkg/)                                           |                 |          |               |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`tlmgr`](https://mpm.run/managers/tlmgr/)                                             | >= 2018         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`topgrade`](https://mpm.run/managers/topgrade/)                                       | >= 17           |          |  🅱️ 🐧 🍎 🪟  |             |            |           |          |           |           |       ✓       |          |        |           |          |
| [`trizen`](https://mpm.run/managers/trizen/)                                           | >= 1            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`urpmi`](https://mpm.run/managers/urpmi/)                                             |                 |          |               |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |
| [`uv`](https://mpm.run/managers/uv/)                                                   | >= 0.5          |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`uvx`](https://mpm.run/managers/uvx/)                                                 | >= 0.10.10      |    ✓     | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`vagrant`](https://mpm.run/managers/vagrant/)                                         | >= 2.4          |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`vcpkg`](https://mpm.run/managers/vcpkg/)                                             |                 |          |   🐧 🍎 🪟    |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`vim-pack`](https://mpm.run/managers/vim-pack/)                                       | >= 0.12         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`volta`](https://mpm.run/managers/volta/) [⚠️](https://mpm.run/managers/volta/)       | >= 1.0.2        |          |   🐧 🍎 🪟    |      ✓      |            |           |          |     ✓     |     ✓     |               |    ✓     |        |           |          |
| [`vscode`](https://mpm.run/managers/vscode/)                                           | >= 1.60         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |           |               |    ✓     |        |           |          |
| [`vscodium`](https://mpm.run/managers/vscodium/)                                       | >= 1.60         |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |           |               |    ✓     |        |           |          |
| [`winget`](https://mpm.run/managers/winget/)                                           | >= 1.28.190     |          |      🪟       |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`xbps`](https://mpm.run/managers/xbps/)                                               | >= 0.59         |          |      🐧       |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`xcodes`](https://mpm.run/managers/xcodes/)                                           | >= 1            |          |      🍎       |      ✓      |            |           |          |           |           |               |    ✓     |   ✓    |           |          |
| [`yarn`](https://mpm.run/managers/yarn/)                                               | >= 1.20, < 2    |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |     ✓      |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |          |
| [`yarn-berry`](https://mpm.run/managers/yarn-berry/)                                   | >= 2            |          | 🅱️ 🐧 🍎 ⨂ 🪟 |             |            |           |    ✓     |           |           |               |          |        |     ✓     |          |
| [`yay`](https://mpm.run/managers/yay/)                                                 | >= 11           |    ✓     |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`yazi`](https://mpm.run/managers/yazi/)                                               | >= 25.2.7       |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`yum`](https://mpm.run/managers/yum/)                                                 | >= 4            |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |    ✓     |
| [`zef`](https://mpm.run/managers/zef/)                                                 |                 |          | 🅱️ 🐧 🍎 ⨂ 🪟 |      ✓      |            |           |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |           |          |
| [`zerobrew`](https://mpm.run/managers/zerobrew/)                                       | >= 0.3          |          |     🐧 🍎     |      ✓      |     ✓      |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`zeroinstall`](https://mpm.run/managers/zeroinstall/)                                 |                 |          | 🅱️ 🐧 🍎 ⨂ 🪟 |             |            |           |    ✓     |           |           |               |    ✓     |        |     ✓     |          |
| [`zim`](https://mpm.run/managers/zim/)                                                 | >= 1            |          |     🐧 🍎     |      ✓      |            |           |          |           |           |       ✓       |          |        |           |          |
| [`zinit`](https://mpm.run/managers/zinit/)                                             | >= 3.10         |          |     🐧 🍎     |      ✓      |            |           |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |          |
| [`zplug`](https://mpm.run/managers/zplug/)                                             | >= 2            |          |     🐧 🍎     |      ✓      |            |           |          |           |     ✓     |       ✓       |          |        |           |          |
| [`zvm`](https://mpm.run/managers/zvm/)                                                 |                 |          |   🐧 🍎 🪟    |      ✓      |            |           |    ✓     |     ✓     |           |               |    ✓     |        |     ✓     |          |
| [`zypper`](https://mpm.run/managers/zypper/)                                           | >= 1.14         |          |    🅱️ 🐧 ⨂    |      ✓      |     ✓      |     ✓     |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |          |

Platforms: 🅱️ BSD[^bsd] · 🐧 Linux[^linux] · 🍎 macOS · ⨂ Unix[^unix] · 🪟 Windows

<!-- mirror-src-end -->

> [!NOTE]
> If your favorite manager is missing or does not support an operation, you can influence its implementation: [open a ticket to document its output](https://github.com/kdeldycke/meta-package-manager/issues/new?assignees=&labels=%F0%9F%8E%81+feature+request&template=new-package-manager.yaml) or [read the contribution guide](https://mpm.run/contributing/) and submit a pull request.
>
> You can help if you [purchase business support 🤝](https://github.com/sponsors/kdeldycke) or [sponsor the project 🫶](https://github.com/sponsors/kdeldycke).

## Installation

All [installation methods](https://mpm.run/install/) are available in the documentation. Below are the most popular ones:

### Homebrew

`mpm` is part of the official [Homebrew](https://brew.sh) default tap, bottled for macOS and [Linux](https://docs.brew.sh/Homebrew-on-Linux), so you can install it with:

```shell-session
$ brew install meta-package-manager
```

### macOS

`mpm` is also [available on MacPorts](https://ports.macports.org/port/meta-package-manager/):

```shell-session
$ sudo port install meta-package-manager
```

### Windows

`mpm` is available in the `main` repository of [Scoop](https://scoop.sh), so you just need to:

```pwsh-session
> scoop install main/meta-package-manager
```

### Executables

Standalone binaries of `mpm` latest version are available as direct downloads for several platforms and architectures:

| Platform    | `arm64`                                                                                                                                                                | `x86_64`                                                                                                                                                           |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Linux**   | [Download `meta-package-manager-linux-arm64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-linux-arm64.bin)     | [Download `meta-package-manager-linux-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-linux-x64.bin)     |
| **macOS**   | [Download `meta-package-manager-macos-arm64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-macos-arm64.bin)     | [Download `meta-package-manager-macos-x64.bin`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-macos-x64.bin)     |
| **Windows** | [Download `meta-package-manager-windows-arm64.exe`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-windows-arm64.exe) | [Download `meta-package-manager-windows-x64.exe`](https://github.com/kdeldycke/meta-package-manager/releases/latest/download/meta-package-manager-windows-x64.exe) |

No need to install Python or `uv`. Useful for CI/CD pipelines running on minimal images, or old platforms where dependency management is painful.

## Quickstart

### List installed packages

List all packages installed on current system:

```shell-session
$ mpm installed
╭──────────────────────────────────────────────┬─────────┬──────────┬──────────────────────────────────────────╮
│ Package ID                                   │ Name    │ Manager  │ Installed version                        │
├──────────────────────────────────────────────┼─────────┼──────────┼──────────────────────────────────────────┤
│ curl                                         │         │ brew     │ 8.21.0                                   │
│ git                                          │         │ brew     │ 2.55.0                                   │
│ aerial                                       │         │ cask     │ 3.6.3                                    │
│ amethyst                                     │         │ cask     │ 0.24.3                                   │
│ bigdecimal                                   │         │ gem      │ 3.1.4                                    │
│ bundler                                      │         │ gem      │ 2.4.22                                   │
│ 361285480                                    │ Keynote │ mas      │ 15.3.1                                   │
│ 408981434                                    │ iMovie  │ mas      │ 10.4.4                                   │
│ @mermaid-js/mermaid-cli                      │         │ npm      │ 11.12.0                                  │
│ npm                                          │         │ npm      │ 11.19.0                                  │
│ cyclonedx-python-lib                         │         │ uv       │ 11.11.0                                  │
│ packageurl-python                            │         │ uv       │ 0.17.6                                   │
│ https://github.com/nvim-lualine/lualine.nvim │         │ vim-pack │ 221ce6b2d999187044529f49da6554a92f740a96 │
│ charliermarsh.ruff                           │         │ vscode   │ 2026.70.0                                │
│ ms-python.python                             │         │ vscode   │ 2026.4.0                                 │
│ zsh-users/zsh-autosuggestions                │         │ zinit    │ ?                                        │
│ zsh-users/zsh-completions                    │         │ zinit    │ ?                                        │
│ (...)                                        │         │          │                                          │
╰──────────────────────────────────────────────┴─────────┴──────────┴──────────────────────────────────────────╯
483 packages total (brew: 246, uv: 75, gem: 62, cask: 52, vscode: 16, vim-pack: 9, zinit: 9, mas: 7, npm: 6, cargo: 1, gh-ext: 0, pnpm: 0, uvx: 0, yarn: 0).
```

Narrow the listing to packages whose ID or name matches a query by passing it as an argument. The match is fuzzy by default (case-insensitive and tokenized); add `--exact` to require a verbatim match on the package ID or name:

```shell-session
$ mpm installed sphinx
$ mpm installed --exact Sphinx
```

### List outdated packages

List all packages installed for which an upgrade is available:

```shell-session
$ mpm outdated
╭──────────────┬─────────────┬─────────┬───────────────────┬────────────────╮
│ Package name │ ID          │ Manager │ Installed version │ Latest version │
├──────────────┼─────────────┼─────────┼───────────────────┼────────────────┤
│ curl         │ curl        │ brew    │ 7.79.1            │ 7.79.1_1       │
│ git          │ git         │ brew    │ 2.33.0            │ 2.33.0_1       │
│ openssl@1.1  │ openssl@1.1 │ brew    │ 1.1.1l            │ 1.1.1l_1       │
│ rake         │ rake        │ gem     │ 13.0.3            │ 13.0.6         │
│ Telegram     │ 747648890   │ mas     │ 8.1               │ 8.1.3          │
│ npm          │ npm@8.0.0   │ npm     │ 7.24.0            │ 8.0.0          │
│ pip          │ pip         │ pip     │ 21.2.4            │ 21.3           │
│ regex        │ regex       │ pip     │ 2021.9.30         │ 2021.10.8      │
╰──────────────┴─────────────┴─────────┴───────────────────┴────────────────╯
8 packages total (brew: 3, pip: 2, gem: 1, mas: 1, npm: 1, apm: 0, cask: 0, composer: 0).
```

The same query argument restricts the listing to outdated packages whose ID or name matches, again fuzzy by default and exact with `--exact`:

```shell-session
$ mpm outdated git
```

### Upgrade outdated packages

[A recent study shows that 70% of vulnerabilities lie in outdated libraries](https://developers.slashdot.org/story/20/05/23/2330244/open-source-security-report-finds-library-induced-flaws-in-70-of-applications), so keeping every piece of software up to date is one of the key habits of security professionals. `mpm` upgrades all packages from all managers with a one-liner:

```shell-session
$ mpm upgrade --all
Updating all outdated packages from brew...
==> Upgrading 4 outdated packages:
gnu-getopt 2.35.1 -> 2.35.2
rclone 1.51.0 -> 1.52.0
fd 8.1.0 -> 8.1.1
youtube-dl 2020.05.08 -> 2020.05.29
(...)
Updating all outdated packages from cask...
==> Upgrading 4 outdated packages:
balenaetcher 1.5.89 -> 1.5.94, libreoffice 6.4.3 -> 6.4.4
(...)
Updating all outdated packages from gem...
Updating openssl
(...)
Updating all outdated packages from npm...
+ npm@6.14.5
(...)
Updating all outdated packages from pip...
Successfully installed dephell-argparse-0.1.3
Successfully installed dephell-pythons-0.1.15
```

This is the primary use case of `mpm`, and the main reason I built it.

### Upgrade with a supply-chain cooldown

There is a counter-argument to the advice above. Chasing the newest release the moment it ships is exactly how supply-chain attacks reach you: a compromised version is usually detected and pulled within days of publication, but an immediate upgrade installs it before that happens. Blindly staying on the bleeding edge trades one risk (outdated, vulnerable libraries) for another (freshly poisoned releases).

`mpm` reconciles the two with a release-age cooldown, refusing any version published more recently than a threshold:

```shell-session
$ mpm --cooldown "7 days" upgrade --all
```

You still pick up older security fixes promptly, while sitting out the risky first days of a brand-new release. See [the cooldown guide](https://mpm.run/cooldown/) for the full mechanism and which managers enforce it natively.

### List managers

`mpm` reports the package managers it detected on your system, and the version each one self-reports:

```shell-session
$ mpm managers
╭────────────┬───────────────────────┬────────────────────────────────────────────────────────────────────────┬──────────────────────╮
│ Manager ID │ Name                  │ CLI                                                                    │ Version              │
├────────────┼───────────────────────┼────────────────────────────────────────────────────────────────────────┼──────────────────────┤
│ brew       │ Homebrew Formulae     │ ✓ /opt/homebrew/bin/brew                                               │ ✓ 6.0.17-69-g38ee325 │
│ cargo      │ Rust cargo            │ ✓ /opt/homebrew/bin/cargo                                              │ ✓ 1.97.1             │
│ cask       │ Homebrew Cask         │ ✓ /opt/homebrew/bin/brew                                               │ ✓ 6.0.17-69-g38ee325 │
│ cpan       │ Perl CPAN             │ ✓ /usr/bin/cpan                                                        │ ✓ 2.28               │
│ gem        │ RubyGems              │ ✓ /usr/bin/gem                                                         │ ✓ 3.4.5              │
│ gh-ext     │ GitHub CLI extensions │ ✓ /opt/homebrew/bin/gh                                                 │ ✓ 2.97.0             │
│ mas        │ Mac App Store         │ ✓ /opt/homebrew/bin/mas                                                │ ✓ 7.0.0              │
│ npm        │ Node npm              │ ✓ /opt/homebrew/bin/npm                                                │ ✓ 11.19.0            │
│ pnpm       │ Node pnpm             │ ✓ /opt/homebrew/bin/pnpm                                               │ ✓ 11.20.0            │
│ topgrade   │ Topgrade              │ ✓ /opt/homebrew/bin/topgrade                                           │ ✓ 17.9.0             │
│ uv         │ Python uv             │ ✓ /opt/homebrew/bin/uv                                                 │ ✓ 0.12.3             │
│ uvx        │ Python uvx            │ ✓ /opt/homebrew/bin/uv                                                 │ ✓ 0.12.3             │
│ vim-pack   │ Neovim vim-pack       │ ✓ /opt/homebrew/bin/nvim                                               │ ✓ 0.12.4             │
│ vscode     │ Visual Studio Code    │ ✓ /Applications/Visual Studio Code.app/Contents/Resources/app/bin/code │ ✓ 1.133.0            │
│ yarn       │ Yarn Classic          │ ✓ /opt/homebrew/bin/yarn                                               │ ✓ 1.22.22            │
│ zinit      │ Zinit                 │ ✓ /opt/homebrew/bin/zsh                                                │ ✓ 3.15.0             │
╰────────────┴───────────────────────┴────────────────────────────────────────────────────────────────────────┴──────────────────────╯
```

If you wonder why one of your package managers is not in that list, name it: a manager you select explicitly is always reported, and the extra columns spell out what `mpm` could not resolve.

```shell-session
$ mpm --composer --volta --choco --yarn-berry managers
╭────────────┬──────────────┬──────────────────┬──────────────────────────┬────────────┬───────────────────╮
│ Manager ID │ Name         │ Supported        │ CLI                      │ Executable │ Version           │
├────────────┼──────────────┼──────────────────┼──────────────────────────┼────────────┼───────────────────┤
│ choco      │ Chocolatey   │ ✘ Windows        │ ✘ choco not found        │            │                   │
│ composer   │ PHP Composer │ ✓                │ ✘ composer not found     │            │                   │
│ volta      │ Volta        │ ✓ (unmaintained) │ ✘ volta not found        │            │                   │
│ yarn-berry │ Yarn Berry   │ ✓                │ ✓ /opt/homebrew/bin/yarn │ ✓          │ ✘ 1.22.22 >=2.0.0 │
╰────────────┴──────────────┴──────────────────┴──────────────────────────┴────────────┴───────────────────╯
```

Four different reasons, one per row. `choco` only runs on Windows. `composer` is supported here but its CLI is nowhere on the `PATH`. `volta` is missing too, and is flagged unmaintained upstream, which is also why selecting it prints a deprecation notice on `stderr`. And `yarn-berry` is the interesting one: its CLI was found and is executable, but the `yarn` on this machine is a `1.x` that does not satisfy the `>=2.0.0` its wrapper requires, so `mpm` will not drive it.

To browse the whole catalog instead, widen the view: `mpm managers --view supported` lists every manager your platform can run, found or not, and `mpm managers --view all` adds those `mpm` implements for other platforms and the unmaintained ones. The global `--all-managers` flag is a synonym for the widest of the three.

If your favorite manager is not supported yet, you can help! See the [contribution guide](https://mpm.run/contributing/). A handful of tools are deliberately left out, each with its rationale: they are catalogued in [unsupported managers](https://mpm.run/unsupported/).

## Used in

Check these projects to get real-life examples of `mpm` usage:

- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/dotfiles?label=%E2%AD%90&style=flat-square) [Dotfiles](https://github.com/kdeldycke/dotfiles) - macOS dotfiles for Python developers, using `mpm` to manage system packages.

Feel free to send a PR to add your project in this list if you are relying on `mpm` in any way.

## Usage

Other subcommands and options are documented in:

- the [detailed help screens](https://mpm.run/cli-parameters/)
- the [manager augmentations](https://mpm.run/augmentations/) where you’ll find inspiration on how to leverage `mpm` power

<!-- operation-footnotes-start -->

[^bsd]: BSD: DragonFly BSD, FreeBSD, MidnightBSD, NetBSD, OpenBSD, SunOS.

[^linux]: Linux: AlmaLinux, Alpine Linux, ALT Linux, Amazon Linux, Android, Arch Linux, Buildroot, CachyOS, CentOS, ChromeOS, Clear Linux OS, CloudLinux OS, Debian, EndeavourOS, Exherbo Linux, Fedora, Generic Linux, Gentoo Linux, Guix System, IBM PowerKVM, Kali Linux, KVM for IBM z Systems, Linux Mint, Mageia, Mandriva Linux, Manjaro Linux, NixOS, Nobara, openSUSE, OpenWrt, Oracle Linux, Parallels, Pidora, PikaOS, Raspbian, RedHat Enterprise Linux, Rocky Linux, Scientific Linux, Slackware, SliTaz GNU/Linux, Source Mage GNU/Linux, SUSE Linux Enterprise Server, Tuxedo OS, Ubuntu, Ultramarine, Void Linux, Windows Subsystem for Linux v1, Windows Subsystem for Linux v2, XenServer.

[^unix]: Unix: Cygwin, GNU/Hurd, Haiku, IBM AIX, IBM i, illumos, Solaris.<!-- operation-footnotes-end -->
