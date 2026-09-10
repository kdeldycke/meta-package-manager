<p align="center">
  <a href="https://mpm.run">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-dark.png">
      <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-light.png">
      <img src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/logo-banner-light.png" alt="Meta Package Manager">
    </picture>
  </a>
</p>

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

## Features

- [Snapshot installed packages](https://mpm.run/cli-parameters/#mpm-dump) to a TOML manifest or a Brewfile, across every manager at once, with `mpm dump packages.toml`:
  ![Every installed package written to a single TOML manifest](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-dump-cli.svg)
- [Restore that manifest](https://mpm.run/cli-parameters/#mpm-restore) on the next machine with `mpm restore packages.toml`, and get the same set of packages back.
- Inventory and list all [package managers](https://mpm.run/cli-parameters/#mpm-managers) available on the system:
  ![Package managers detected on the system](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-managers-cli.svg)
- Runs on macOS, Linux, Windows, FreeBSD, NetBSD and OpenBSD, with [standalone executables](#executables) for the first three.
- [List installed packages](https://mpm.run/cli-parameters/#mpm-installed):
  ![Every package installed on the system](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-installed-cli.svg)
- [List duplicate installed packages](https://mpm.run/duplicates/).
- [Search for packages](https://mpm.run/cli-parameters/#mpm-search).
- [Install a package](https://mpm.run/cli-parameters/#mpm-install).
- [Remove a package](https://mpm.run/cli-parameters/#mpm-remove).
- [List outdated packages](https://mpm.run/cli-parameters/#mpm-outdated), with the differing part of each version picked out in color, so a patch bump reads apart from a major one at a glance:
  ![Packages an upgrade is available for](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-outdated-cli.svg)
- [List orphaned packages](https://mpm.run/cli-parameters/#mpm-orphans).
- [Sync local package infos](https://mpm.run/cli-parameters/#mpm-sync).
- [Diagnose the health of package managers](https://mpm.run/cli-parameters/#mpm-doctor).
- [Upgrade all outdated packages](https://mpm.run/cli-parameters/#mpm-upgrade) from every manager at once, the primary use case of `mpm` and the main reason I built it, since [70% of vulnerabilities lie in outdated libraries](https://developers.slashdot.org/story/20/05/23/2330244/open-source-security-report-finds-library-induced-flaws-in-70-of-applications). A manager that fails is marked `✘` and named in a closing summary, while the others carry on:
  ![Every manager upgraded, in one command](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-upgrade-cli.svg)
- [Mitigate supply-chain attacks](https://mpm.run/cooldown/) with a release-age cooldown that refuses any version published more recently than a threshold. A manager that cannot enforce the window is skipped, rather than run unguarded:
  ![Upgrading under a release-age cooldown](https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/assets/mpm-upgrade-cooldown-cli.svg)
- [Software Bill of Materials](https://mpm.run/cli-parameters/#mpm-sbom): export installed packages to [SPDX](https://spdx.dev) and [CycloneDX](https://cyclonedx.org) SBOM files.
- Pin-point commands to a [subset of package managers](https://mpm.run/configuration/#selecting-managers) (include/exclude selectors).
- Support plain, versioned and [purl](https://github.com/package-url/purl-spec) package specifiers.
- Export output to [JSON or user-friendly tables](https://mpm.run/cli-parameters/#mpm).
- [Shell auto-completion](https://mpm.run/install/) for Bash, Zsh and Fish.
- [Desktop menu bar integration](https://mpm.run/desktop-menus/): a SwiftBar/Xbar plugin on macOS, a GNOME Shell extension on Linux.
- Because `mpm` tries to wrap all other package managers, it became another pathological case of [XKCD #927: Standards](https://xkcd.com/927/)

## Supported package managers

One CLI to rule them all. Every manager below links to its own documentation page, and `mpm` [runs them concurrently](https://mpm.run/concurrency/) bar the few that queue on a shared backend.

<!-- mirror-src
from meta_package_manager._docs import manager_roster

print(manager_roster())
-->

[`am`](https://mpm.run/managers/am/) · [`antidote`](https://mpm.run/managers/antidote/) · [`antigen`](https://mpm.run/managers/antigen/) · [`apk`](https://mpm.run/managers/apk/) · [`apt`](https://mpm.run/managers/apt/) · [`apt-mint`](https://mpm.run/managers/apt-mint/) · [`aptitude`](https://mpm.run/managers/aptitude/) · [`asdf`](https://mpm.run/managers/asdf/) · [`aura`](https://mpm.run/managers/aura/) · [`basalt`](https://mpm.run/managers/basalt/) · [`bin`](https://mpm.run/managers/bin/) · [`bob`](https://mpm.run/managers/bob/) · [`bpkg`](https://mpm.run/managers/bpkg/) · [`brew`](https://mpm.run/managers/brew/) · [`bun`](https://mpm.run/managers/bun/) · [`cargo`](https://mpm.run/managers/cargo/) · [`cask`](https://mpm.run/managers/cask/) · [`cave`](https://mpm.run/managers/cave/) · [`choco`](https://mpm.run/managers/choco/) · [`choosenim`](https://mpm.run/managers/choosenim/) · [`chromebrew`](https://mpm.run/managers/chromebrew/) · [`claude-code-plugins`](https://mpm.run/managers/claude-code-plugins/) · [`clib`](https://mpm.run/managers/clib/) · [`composer`](https://mpm.run/managers/composer/) · [`conda`](https://mpm.run/managers/conda/) · [`cpan`](https://mpm.run/managers/cpan/) · [`deb-get`](https://mpm.run/managers/deb-get/) · [`dkp-pacman`](https://mpm.run/managers/dkp-pacman/) · [`dnf`](https://mpm.run/managers/dnf/) · [`dnf5`](https://mpm.run/managers/dnf5/) · [`dotnet`](https://mpm.run/managers/dotnet/) · [`elan`](https://mpm.run/managers/elan/) · [`emacs`](https://mpm.run/managers/emacs/) · [`emerge`](https://mpm.run/managers/emerge/) · [`eopkg`](https://mpm.run/managers/eopkg/) · [`fink`](https://mpm.run/managers/fink/) · [`fisher`](https://mpm.run/managers/fisher/) · [`flatpak`](https://mpm.run/managers/flatpak/) · [`fwupd`](https://mpm.run/managers/fwupd/) · [`gcloud`](https://mpm.run/managers/gcloud/) · [`gem`](https://mpm.run/managers/gem/) · [`getnf`](https://mpm.run/managers/getnf/) · [`gext`](https://mpm.run/managers/gext/) · [`gh-ext`](https://mpm.run/managers/gh-ext/) · [`ghcup`](https://mpm.run/managers/ghcup/) · [`go`](https://mpm.run/managers/go/) · [`guix`](https://mpm.run/managers/guix/) · [`gup`](https://mpm.run/managers/gup/) · [`haxelib`](https://mpm.run/managers/haxelib/) · [`hyprpm`](https://mpm.run/managers/hyprpm/) · [`ips`](https://mpm.run/managers/ips/) · [`jpm`](https://mpm.run/managers/jpm/) · [`julia`](https://mpm.run/managers/julia/) · [`juliaup`](https://mpm.run/managers/juliaup/) · [`krew`](https://mpm.run/managers/krew/) · [`lazy`](https://mpm.run/managers/lazy/) · [`luarocks`](https://mpm.run/managers/luarocks/) · [`lure`](https://mpm.run/managers/lure/) · [`macports`](https://mpm.run/managers/macports/) · [`mamba`](https://mpm.run/managers/mamba/) · [`mas`](https://mpm.run/managers/mas/) · [`mason`](https://mpm.run/managers/mason/) · [`micro`](https://mpm.run/managers/micro/) · [`micromamba`](https://mpm.run/managers/micromamba/) · [`miktex`](https://mpm.run/managers/miktex/) · [`mise`](https://mpm.run/managers/mise/) · [`nala`](https://mpm.run/managers/nala/) · [`nimble`](https://mpm.run/managers/nimble/) · [`nix`](https://mpm.run/managers/nix/) · [`npm`](https://mpm.run/managers/npm/) · [`oh-my-fish`](https://mpm.run/managers/oh-my-fish/) · [`ollama`](https://mpm.run/managers/ollama/) · [`opam`](https://mpm.run/managers/opam/) · [`opkg`](https://mpm.run/managers/opkg/) · [`pacman`](https://mpm.run/managers/pacman/) · [`pacstall`](https://mpm.run/managers/pacstall/) · [`pamac`](https://mpm.run/managers/pamac/) · [`paru`](https://mpm.run/managers/paru/) · [`pear`](https://mpm.run/managers/pear/) · [`pearl`](https://mpm.run/managers/pearl/) · [`pi`](https://mpm.run/managers/pi/) · [`pikaur`](https://mpm.run/managers/pikaur/) · [`pip`](https://mpm.run/managers/pip/) · [`pipx`](https://mpm.run/managers/pipx/) · [`pipxu`](https://mpm.run/managers/pipxu/) · [`pixi`](https://mpm.run/managers/pixi/) · [`pkcon`](https://mpm.run/managers/pkcon/) · [`pkg`](https://mpm.run/managers/pkg/) · [`pkg-tools`](https://mpm.run/managers/pkg-tools/) · [`pkgin`](https://mpm.run/managers/pkgin/) · [`pkgit`](https://mpm.run/managers/pkgit/) · [`pkgm`](https://mpm.run/managers/pkgm/) · [`platformio-core`](https://mpm.run/managers/platformio-core/) · [`pnpm`](https://mpm.run/managers/pnpm/) · [`ports`](https://mpm.run/managers/ports/) · [`prt-get`](https://mpm.run/managers/prt-get/) · [`pwsh-gallery`](https://mpm.run/managers/pwsh-gallery/) · [`pyenv`](https://mpm.run/managers/pyenv/) · [`raco`](https://mpm.run/managers/raco/) · [`roswell`](https://mpm.run/managers/roswell/) · [`rustup`](https://mpm.run/managers/rustup/) · [`scoop`](https://mpm.run/managers/scoop/) · [`sdkman`](https://mpm.run/managers/sdkman/) · [`sfsu`](https://mpm.run/managers/sfsu/) · [`sheldon`](https://mpm.run/managers/sheldon/) · [`shelly`](https://mpm.run/managers/shelly/) · [`skills`](https://mpm.run/managers/skills/) · [`slapt-get`](https://mpm.run/managers/slapt-get/) · [`snap`](https://mpm.run/managers/snap/) · [`soar`](https://mpm.run/managers/soar/) · [`sorcery`](https://mpm.run/managers/sorcery/) · [`spack`](https://mpm.run/managers/spack/) · [`steamcmd`](https://mpm.run/managers/steamcmd/) · [`stew`](https://mpm.run/managers/stew/) · [`sun-tools`](https://mpm.run/managers/sun-tools/) · [`tazpkg`](https://mpm.run/managers/tazpkg/) · [`tlmgr`](https://mpm.run/managers/tlmgr/) · [`topgrade`](https://mpm.run/managers/topgrade/) · [`trizen`](https://mpm.run/managers/trizen/) · [`urpmi`](https://mpm.run/managers/urpmi/) · [`uv`](https://mpm.run/managers/uv/) · [`uvx`](https://mpm.run/managers/uvx/) · [`vagrant`](https://mpm.run/managers/vagrant/) · [`vcpkg`](https://mpm.run/managers/vcpkg/) · [`vim-pack`](https://mpm.run/managers/vim-pack/) · [`vscode`](https://mpm.run/managers/vscode/) · [`vscodium`](https://mpm.run/managers/vscodium/) · [`winget`](https://mpm.run/managers/winget/) · [`xbps`](https://mpm.run/managers/xbps/) · [`xcodes`](https://mpm.run/managers/xcodes/) · [`yarn`](https://mpm.run/managers/yarn/) · [`yarn-berry`](https://mpm.run/managers/yarn-berry/) · [`yay`](https://mpm.run/managers/yay/) · [`yazi`](https://mpm.run/managers/yazi/) · [`yum`](https://mpm.run/managers/yum/) · [`zef`](https://mpm.run/managers/zef/) · [`zerobrew`](https://mpm.run/managers/zerobrew/) · [`zeroinstall`](https://mpm.run/managers/zeroinstall/) · [`zim`](https://mpm.run/managers/zim/) · [`zinit`](https://mpm.run/managers/zinit/) · [`zplug`](https://mpm.run/managers/zplug/) · [`zvm`](https://mpm.run/managers/zvm/) · [`zypper`](https://mpm.run/managers/zypper/)

<!-- mirror-src-end -->

`mpm` also drives the managers below, whose upstream projects are unmaintained. They still work, but any of them can be dropped in a future release, without notice:

<!-- mirror-src
from meta_package_manager._docs import manager_roster

print(manager_roster(unmaintained=True))
-->

[`apm`](https://mpm.run/managers/apm/) · [`apt-cyg`](https://mpm.run/managers/apt-cyg/) · [`pacaur`](https://mpm.run/managers/pacaur/) · [`swupd`](https://mpm.run/managers/swupd/) · [`volta`](https://mpm.run/managers/volta/)

<!-- mirror-src-end -->

`mpm` drives [`topgrade`](https://mpm.run/managers/topgrade/) for `upgrade --all` only, and topgrade in turn upgrades runtimes, shell plugins and OS updaters that `mpm` does not wrap: one `mpm upgrade --all` therefore reaches past the names above.

If your favorite manager is not supported yet, you can help! See the [contribution guide](https://mpm.run/contributing/). A handful of tools are deliberately left out, each with its rationale: they are catalogued in [unsupported managers](https://mpm.run/unsupported/).

## Installation

All [installation methods](https://mpm.run/install/) are available in the documentation. Below are the most popular ones:

### uv

`mpm` is [distributed on PyPI](https://pypi.org/project/meta-package-manager/), so [`uv`](https://docs.astral.sh/uv/) installs it on Linux, macOS and Windows alike:

```shell-session
$ uv tool install meta-package-manager
```

To try `mpm` without installing anything, run `uvx meta-package-manager` instead.

### Homebrew

`mpm` is part of the official [Homebrew](https://brew.sh) default tap, bottled for macOS and [Linux](https://docs.brew.sh/Homebrew-on-Linux), so you can install it with:

```shell-session
$ brew install meta-package-manager
```

### MacPorts

`mpm` is also [available on MacPorts](https://ports.macports.org/port/meta-package-manager/):

```shell-session
$ sudo port install meta-package-manager
```

### Scoop

`mpm` is available in the `main` repository of [Scoop](https://scoop.sh), so on Windows you just need to:

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

## Used in

Check these projects to get real-life examples of `mpm` usage:

- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/dotfiles?label=%E2%AD%90&style=flat-square) [Dotfiles](https://github.com/kdeldycke/dotfiles) - macOS dotfiles for Python developers, using `mpm` to manage system packages.

Feel free to send a PR to add your project in this list if you are relying on `mpm` in any way.

## Usage

Other subcommands and options are documented in:

- the [detailed help screens](https://mpm.run/cli-parameters/)
- the [manager augmentations](https://mpm.run/augmentations/) where you’ll find inspiration on how to leverage `mpm` power
