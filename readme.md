<p align="center">
  <a href="https://github.com/kdeldycke/meta-package-manager/">
    <img src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/images/logo-banner.svg" alt="Meta Package Manager">
  </a>
</p>

<a href="https://xkcd.com/1654/" alt="XKCD #1654: Universal Install Script">
<img align="right" width="20%" height="20%" src="http://imgs.xkcd.com/comics/universal_install_script.png"/>
</a>

[![Last release](https://img.shields.io/pypi/v/meta-package-manager.svg)](https://pypi.python.org/pypi/meta-package-manager)
[![Python versions](https://img.shields.io/pypi/pyversions/meta-package-manager.svg)](https://pypi.python.org/pypi/meta-package-manager)
[![Type checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Unittests status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/main)
[![Documentation status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/docs.yaml?query=branch%3Amain)
[![DOI](https://zenodo.org/badge/65922807.svg)](https://zenodo.org/badge/latestdoi/65922807)

**What is Meta Package Manager?**

- provides the `mpm` CLI, a wrapper around all package managers
- `mpm` is like [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), but for package
  managers instead of videos
- `mpm` solves [XKCD #1654 - *Universal Install Script*](https://xkcd.com/1654/)

______________________________________________________________________

## Features

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/images/mpm-outdated-cli.png"/>

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/main/docs/images/mpm-managers-cli.png"/>

- Inventory and list all package managers available on the system.
- Supports macOS, Linux and Windows.
- List installed packages.
- Search for packages.
- Install a package.
- Remove a package.
- List outdated packages.
- Sync local package infos.
- Upgrade all outdated packages.
- Backup list of installed packages to TOML file.
- Restore/install list of packages from TOML files.
- Pin-point commands to a subset of package managers (include/exclude
  selectors).
- Support plain, versionned and [purl](https://github.com/package-url/purl-spec) package specifiers.
- Export output to JSON or print user-friendly tables.
- Shell auto-completion for Bash, Zsh and Fish.
- Provides a
  [Xbar/SwiftBar plugin](https://kdeldycke.github.io/meta-package-manager/bar-plugin.html) for
  friendly macOS integration.
- Because `mpm` try to wrap all other package managers, it became another
  pathological case of [XKCD #927: Standards](https://xkcd.com/927/)

## Supported package managers and operations

| Package manager                                                           | Min. version | Linux | macOS | Windows | `installed` | `outdated` | `search` | `install` | `upgrade` | `upgrade_all` | `remove` | `sync` | `cleanup` |
| ------------------------------------------------------------------------- | ------------ | :---: | :---: | :-----: | :---------: | :--------: | :------: | :-------: | :-------: | :-----------: | :------: | :----: | :-------: |
| [`apm`](https://atom.io/packages)                                         | 1.0.0        |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |           |
| [`apt`](https://wiki.debian.org/AptCLI)                                   | 1.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |
| [`apt-mint`](https://github.com/kdeldycke/meta-package-manager/issues/52) | 1.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |
| [`brew`](https://brew.sh)                                                 | 2.7.0        |   🐧   |   🍎   |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`cargo`](https://doc.rust-lang.org/cargo/)                               | 1.0.0        |   🐧   |   🍎   |    🪟    |      ✓      |            |    ✓     |     ✓     |           |               |    ✓     |        |           |
| [`cask`](https://caskroom.github.io)                                      | 2.7.0        |       |   🍎   |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`choco`](https://chocolatey.org)                                         | 0.10.4       |       |       |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |           |
| [`composer`](https://getcomposer.org)                                     | 1.4.0        |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |     ✓     |
| [`dnf`](https://github.com/rpm-software-management/dnf)                   | 4.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |
| [`emerge`](https://wiki.gentoo.org/wiki/Portage#emerge)                   | 3.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |
| [`flatpak`](https://flatpak.org)                                          | 1.2.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |     ✓     |
| [`gem`](https://rubygems.org)                                             | 2.5.0        |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |
| [`mas`](https://github.com/argon/mas)                                     | 1.6.1        |       |   🍎   |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |           |
| [`npm`](https://www.npmjs.com)                                            | 4.0.0        |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |           |
| [`opkg`](https://git.yoctoproject.org/cgit/cgit.cgi/opkg/)                | 0.2.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |           |
| [`pacaur`](https://github.com/E5ten/pacaur)                               | 4.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`pacman`](https://wiki.archlinux.org/title/pacman)                       | 5.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`paru`](https://github.com/Morganamilo/paru)                             | 1.9.3        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`pip`](https://pip.pypa.io)                                              | 10.0.0       |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |
| [`pipx`](https://pypa.github.io/pipx/)                                    | 1.0.0        |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |          |     ✓     |     ✓     |       ✓       |    ✓     |        |           |
| [`scoop`](https://scoop.sh)                                               | 0.2.4        |       |       |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`snap`](https://snapcraft.io)                                            | 2.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |        |           |
| [`steamcmd`](https://developer.valvesoftware.com/wiki/SteamCMD)           | None         |   🐧   |   🍎   |    🪟    |             |            |          |     ✓     |           |               |          |        |           |
| [`vscode`](https://code.visualstudio.com)                                 | 1.60.0       |   🐧   |   🍎   |    🪟    |      ✓      |            |          |     ✓     |           |               |          |        |           |
| [`yarn`](https://yarnpkg.com)                                             | 1.20.0       |   🐧   |   🍎   |    🪟    |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |        |     ✓     |
| [`yay`](https://github.com/Jguer/yay)                                     | 11.0.0       |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |    ✓     |   ✓    |     ✓     |
| [`yum`](http://yum.baseurl.org)                                           | 4.0.0        |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |
| [`zypper`](https://en.opensuse.org/Portal:Zypper)                         | 1.14.0       |   🐧   |       |         |      ✓      |     ✓      |    ✓     |     ✓     |     ✓     |       ✓       |          |   ✓    |     ✓     |

## Quickstart

Easiest way is to install `mpm` with [`pipx`](https://pypa.github.io/pipx/):

```shell-session
$ pipx install meta-package-manager
```

Other
[alternatives installation methods](https://kdeldycke.github.io/meta-package-manager/install.html)
are available in the documentation.

## List managers

List all supported package managers and their status on current system (macOS
in this case):

```shell-session
$ mpm --all-managers managers
╭────────────┬────────────────────┬────────────────┬──────────────────────────────┬────────────┬───────────╮
│ Manager ID │ Name               │ Supported      │ CLI                          │ Executable │ Version   │
├────────────┼────────────────────┼────────────────┼──────────────────────────────┼────────────┼───────────┤
│ apm        │ Atom's apm         │ ✓              │ ✘ apm not found              │            │           │
│ apt        │ APT                │ ✘ Linux only   │ ✓ /usr/bin/apt               │ ✓          │ ✘         │
│ apt-mint   │ Linux Mint's apt   │ ✘ Linux only   │ ✓ /usr/bin/apt               │ ✓          │ ✘         │
│ brew       │ Homebrew Formulae  │ ✓              │ ✓ /opt/homebrew/bin/brew     │ ✓          │ ✓ 3.6.3   │
│ cargo      │ Rust's cargo       │ ✓              │ ✓ /opt/homebrew/bin/cargo    │ ✓          │ ✓ 1.64.0  │
│ cask       │ Homebrew Cask      │ ✓              │ ✓ /opt/homebrew/bin/brew     │ ✓          │ ✓ 3.6.3   │
│ choco      │ Chocolatey         │ ✘ Windows only │ ✘ choco not found            │            │           │
│ composer   │ PHP's Composer     │ ✓              │ ✓ /opt/homebrew/bin/composer │ ✓          │ ✓ 2.4.2   │
│ dnf        │ DNF                │ ✘ Linux only   │ ✘ dnf not found              │            │           │
│ emerge     │ Emerge             │ ✘ Linux only   │ ✘ emerge not found           │            │           │
│ flatpak    │ Flatpak            │ ✘ Linux only   │ ✘ flatpak not found          │            │           │
│ gem        │ Ruby Gems          │ ✓              │ ✓ /usr/bin/gem               │ ✓          │ ✓ 3.0.3.1 │
│ mas        │ Mac AppStore       │ ✓              │ ✓ /opt/homebrew/bin/mas      │ ✓          │ ✓ 1.8.6   │
│ npm        │ Node's npm         │ ✓              │ ✓ /opt/homebrew/bin/npm      │ ✓          │ ✓ 8.19.2  │
│ opkg       │ OPKG               │ ✘ Linux only   │ ✘ opkg not found             │            │           │
│ pacman     │ Pacman             │ ✘ Linux only   │ ✘ pacman not found           │            │           │
│ paru       │ Paru               │ ✘ Linux only   │ ✘ paru not found             │            │           │
│ pip        │ Pip                │ ✓              │ ✓ ~/.pyenv/shims/python3     │ ✓          │ ✓ 22.2.2  │
│ pipx       │ Pipx               │ ✓              │ ✓ /opt/homebrew/bin/pipx     │ ✓          │ ✓ 1.1.0   │
│ scoop      │ Scoop              │ ✘ Windows only │ ✘ scoop not found            │            │           │
│ snap       │ Snap               │ ✘ Linux only   │ ✘ snap not found             │            │           │
│ steamcmd   │ Valve Steam        │ ✓              │ ✘ steamcmd not found         │            │           │
│ vscode     │ Visual Studio Code │ ✓              │ ✓ /opt/homebrew/bin/code     │ ✓          │ ✓ 1.71.2  │
│ yarn       │ Node's yarn        │ ✓              │ ✓ /opt/homebrew/bin/yarn     │ ✓          │ ✓ 1.22.19 │
│ yay        │ Yay                │ ✘ Linux only   │ ✘ yay not found              │            │           │
│ yum        │ YUM                │ ✘ Linux only   │ ✘ yum not found              │            │           │
│ zypper     │ Zypper             │ ✘ Linux only   │ ✘ zypper not found           │            │           │
╰────────────┴────────────────────┴────────────────┴──────────────────────────────┴────────────┴───────────╯
```

If your favorite manager is not supported yet, you can help! See the [contibution guide](https://kdeldycke.github.io/meta-package-manager/contributing.html).

## List installed packages

List all packages installed on current system:

```shell-session
$ mpm installed
╭─────────────────────────────┬─────────────────────────────┬─────────┬────────────────────╮
│ Package name                │ ID                          │ Manager │ Installed version  │
├─────────────────────────────┼─────────────────────────────┼─────────┼────────────────────┤
│ github                      │ github                      │ apm     │ 0.36.9             │
│ update-package-dependencies │ update-package-dependencies │ apm     │ 0.13.1             │
│ rust                        │ rust                        │ brew    │ 1.55.0             │
│ x264                        │ x264                        │ brew    │ r3060              │
│ atom                        │ atom                        │ cask    │ 1.58.0             │
│ visual-studio-code          │ visual-studio-code          │ cask    │ 1.52.0             │
│ nokogiri                    │ nokogiri                    │ gem     │ x86_64-darwin      │
│ rake                        │ rake                        │ gem     │ 13.0.3             │
│ iMovie                      │ 408981434                   │ mas     │ 10.2.5             │
│ Telegram                    │ 747648890                   │ mas     │ 8.1                │
│ npm                         │ npm                         │ npm     │ 7.24.0             │
│ raven                       │ raven                       │ npm     │ 2.6.4              │
│ jupyterlab                  │ jupyterlab                  │ pip     │ 3.1.14             │
│ Sphinx                      │ Sphinx                      │ pip     │ 4.2.0              │
│ ms-python.python            │ ms-python.python            │ vscode  │ 2021.10.1317843341 │
│ ms-toolsai.jupyter          │ ms-toolsai.jupyter          │ vscode  │ 2021.9.1001312534  │
╰─────────────────────────────┴─────────────────────────────┴─────────┴────────────────────╯
16 packages total (brew: 2, pip: 2, apm: 2, gem: 2, cask: 2, mas: 2, vscode: 2, npm: 2, composer: 0).
```

## List outdated packages

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

## Usage

More documentation is available in:

- the
  [detailed help screens](https://kdeldycke.github.io/meta-package-manager/cli-help.html)
- the
  [list of use-cases](https://kdeldycke.github.io/meta-package-manager/usecase.html)
  where you’ll find inspiration on how to leverage `mpm` power
