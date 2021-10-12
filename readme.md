# Meta Package Manager

<a href="https://xkcd.com/1654/" alt="XKCD #1654: Universal Install Script">
<img align="right" width="20%" height="20%" src="http://imgs.xkcd.com/comics/universal_install_script.png"/>
</a>

[![Last
release](https://img.shields.io/pypi/v/meta-package-manager.svg)](https://pypi.python.org/pypi/meta-package-manager)
[![Python
versions](https://img.shields.io/pypi/pyversions/meta-package-manager.svg)](https://pypi.python.org/pypi/meta-package-manager)
[![Unittests
status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml/badge.svg?branch=develop)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Adevelop)
[![Documentation
status](https://github.com/kdeldycke/meta-package-manager/actions/workflows/docs.yaml/badge.svg?branch=develop)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/docs.yaml?query=branch%3Adevelop)
[![Coverage
status](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop/graph/badge.svg)](https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop)

**What is Meta Package Manager?**

- It provides the `mpm` CLI
- `mpm` is like [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), but for package
  managers instead of videos
- `mpm` solves [XKCD #1654: Universal Install Script](https://xkcd.com/1654/)

## Features

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/develop/docs/mpm-outdated-cli.png"/>

<img align="right" width="30%" height="30%" src="https://raw.githubusercontent.com/kdeldycke/meta-package-manager/develop/docs/mpm-managers-cli.png"/>

- Inventory and list all package managers available on the system.
- Supports macOS, Linux and Windows.
- List installed packages.
- Search for packages.
- Install a package.
- List outdated packages.
- Sync local package infos.
- Upgrade all outdated packages.
- Backup list of installed packages to TOML file.
- Restore/install list of packages from TOML files.
- Pin-point commands to a subset of package managers (include/exclude
  selectors).
- Export results in JSON or user-friendly tables.
- Shell auto-completion for Bash, Zsh and Fish.
- Provides a [xbar
  plugin](https://kdeldycke.github.io/meta-package-manager/xbar.html) for
  friendly macOS integration.
- Because `mpm` try to wrap all other package managers, it became another
  pathological case of [XKCD #927: Standards](https://xkcd.com/927/)

## Supported package managers

| Package manager                                                           | Min. version | macOS | Linux | Windows | `sync` | `installed` |                               `search`                                | `install` | `outdated` | `upgrade` | `cleanup` |
|---------------------------------------------------------------------------|--------------|:-----:|:-----:|:-------:|:------:|:-----------:|:---------------------------------------------------------------------:|:---------:|:----------:|:---------:|:---------:|
| [`apm`](https://atom.io/packages)                                         | 1.0.0        |   ✓   |   ✓   |    ✓    |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |           |
| [`apt`](https://wiki.debian.org/Apt)                                      | 1.0.0        |       |   ✓   |         |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`apt-mint`](https://github.com/kdeldycke/meta-package-manager/issues/52) | 1.0.0        |       |   ✓   |         |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`brew`](https://brew.sh)                                                 | 2.7.0        |   ✓   |   ✓   |         |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`cask`](https://caskroom.github.io)                                      | 2.7.0        |   ✓   |       |         |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`choco`](https://chocolatey.org)                                         | 0.10.4       |       |       |    ✓    |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`composer`](https://getcomposer.org)                                     | 1.4.0        |   ✓   |   ✓   |    ✓    |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`flatpak`](https://flatpak.org)                                          | 1.2.0        |       |   ✓   |         |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`gem`](https://rubygems.org)                                             | 2.5.0        |   ✓   |   ✓   |    ✓    |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |
| [`mas`](https://github.com/argon/mas)                                     | 1.6.1        |   ✓   |       |         |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |           |
| [`npm`](https://www.npmjs.com)                                            | 4.0.0        |   ✓   |   ✓   |    ✓    |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |           |
| [`opkg`](https://git.yoctoproject.org/cgit/cgit.cgi/opkg/)                | 0.2.0        |       |   ✓   |         |   ✓    |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |           |
| [`pip`](https://pypi.org)                                                 | 10.0.0       |   ✓   |   ✓   |    ✓    |        |      ✓      | [✘\*](https://github.com/pypa/pip/issues/5216#issuecomment-744605466) |     ✓     |     ✓      |     ✓     |           |
| [`snap`](https://snapcraft.io)                                            | 2.0.0        |       |   ✓   |         |        |      ✓      |                                   ✓                                   |     ✓     |            |     ✓     |           |
| [`vscode`](https://code.visualstudio.com)                                 | 1.60.0       |   ✓   |   ✓   |    ✓    |        |      ✓      |                                   ✓                                   |     ✓     |            |     ✓     |           |
| [`yarn`](https://yarnpkg.com)                                             | 1.21.0       |   ✓   |   ✓   |    ✓    |        |      ✓      |                                   ✓                                   |     ✓     |     ✓      |     ✓     |     ✓     |

## Quickstart

1.  Install `mpm` with `pip`:

    ``` shell-session
    $ pip install meta-package-manager
    ```

Other [alternatives installation
methods](https://kdeldycke.github.io/meta-package-manager/install.html) are
available in the documentation.

## Usage

List all supported package managers and their status on current system (macOS
in this case):

``` shell-session
$ mpm -a managers
┌────────────────────┬──────────┬─────────────────┬────────────────────────────┬────────────┬───────────┐
│ Package manager    │ ID       │ Supported       │ CLI                        │ Executable │ Version   │
├────────────────────┼──────────┼─────────────────┼────────────────────────────┼────────────┼───────────┤
│ Atom's apm         │ apm      │ ✓               │ ✓  /usr/local/bin/apm      │ ✓          │ ✓  2.6.2  │
│ APT                │ apt      │ ✘  Linux only   │ ✓  /usr/bin/apt            │ ✓          │ ✘         │
│ Linux Mint's apt   │ apt-mint │ ✘  Linux only   │ ✓  /usr/bin/apt            │ ✓          │ ✘         │
│ Homebrew Formulae  │ brew     │ ✓               │ ✓  /usr/local/bin/brew     │ ✓          │ ✓  3.2.15 │
│ Homebrew Cask      │ cask     │ ✓               │ ✓  /usr/local/bin/brew     │ ✓          │ ✓  3.2.15 │
│ Chocolatey         │ choco    │ ✘  Windows only │ ✘  choco not found         │            │           │
│ PHP's Composer     │ composer │ ✓               │ ✓  /usr/local/bin/composer │ ✓          │ ✓  2.1.8  │
│ Flatpak            │ flatpak  │ ✘  Linux only   │ ✘  flatpak not found       │            │           │
│ Ruby Gems          │ gem      │ ✓               │ ✓  /usr/bin/gem            │ ✓          │ ✓  3.0.3  │
│ Mac AppStore       │ mas      │ ✓               │ ✓  /usr/local/bin/mas      │ ✓          │ ✓  1.8.3  │
│ Node's npm         │ npm      │ ✓               │ ✓  /usr/local/bin/npm      │ ✓          │ ✓  7.24.0 │
│ OPKG               │ opkg     │ ✘  Linux only   │ ✘  opkg not found          │            │           │
│ Pip                │ pip      │ ✓               │ ✓  /usr/local/bin/python3  │ ✓          │ ✓  21.2.4 │
│ Snap               │ snap     │ ✘  Linux only   │ ✘  snap not found          │            │           │
│ Visual Studio Code │ vscode   │ ✓               │ ✓  /usr/local/bin/code     │ ✓          │ ✓  1.60.2 │
│ Node's yarn        │ yarn     │ ✓               │ ✘  yarn not found          │            │           │
└────────────────────┴──────────┴─────────────────┴────────────────────────────┴────────────┴───────────┘
```

More documentation is available in:

- the [detailed help screens](https://kdeldycke.github.io/meta-package-manager/cli-help.html)
- the [list of use-cases](https://kdeldycke.github.io/meta-package-manager/usecase.html) where you'll find inspiration on how to leverage `mpm` power
