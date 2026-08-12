# {octicon}`circle-slash` Unsupported managers

`mpm` wraps [a long list of package managers](managers.md), but not everything that installs software.

Two reasons put a tool in the table below:
- ☠️ Its upstream is dead.
- ❌ Or it lacks critical features required by `mpm`.

| Tool | Status | Kind | Why? |
| :--- | :---: | :--- | :--- |
| [`antibody`](https://github.com/getantibody/antibody) | ☠️ | Zsh plugin manager | Archived on 2022-05-27, superseded by [`antidote`](managers/antidote.md), which `mpm` wraps. |
| [`declaro`](https://github.com/mantinhas/declaro) | ❌ | Single-manager declarative wrapper | Snapshots one already-installed manager at a time into an editable package list. No unique registry, no license, and its own multi-manager request has sat unaddressed since December 2025 ([mantinhas/declaro#31](https://github.com/mantinhas/declaro/issues/31)). |
| [`decman`](https://github.com/kiviktnm/decman) | ❌ | Arch declarative system manager | No operation verbs at all, flags only: every run reconciles the whole declared state. Its packages come from pacman and its own in-house AUR builder, both already `mpm` territory. Also manages dotfiles, systemd units, users and PGP keys, outside the system scope every `mpm` manager holds to. |
| [`dein`](https://github.com/Shougo/dein.vim) | ☠️ | Vim and Neovim plugin manager | Development stopped, superseded by [`dpp`](https://github.com/Shougo/dpp.vim) below, last commit on 2025-09-13. Pure Vimscript, so it also exposes neither a binary to run nor a version to report. |
| [`dpp`](https://github.com/Shougo/dpp.vim) | ❌ | Vim and Neovim plugin manager | Live successor to `dein` above, but drivable only from inside the editor: its work happens in a Deno process ([denops.vim](https://github.com/vim-denops/denops.vim)) that Vim starts, and it documents no headless entry point. It reports no version and ships no binary of its own either, so it fails the same two requirements `dein` does, with nothing left to key the manager on. |
| [`fundle`](https://github.com/danhper/fundle) | ☠️ | Fish plugin manager | No commit since 2023-01-05. |
| [`jetpack`](https://github.com/3ofcoins/jetpack) | ☠️ | FreeBSD jail runtime | Self-described prototype, no commit since 2018-10-25. Not a package manager to begin with. |
| [`metapac`](https://github.com/ripytide/metapac) | ❌ | Declarative multi-backend package manager | Delegates to 21 backends `mpm` already wraps directly. No per-package `install`/`remove` verb: removed by design, see [ripytide/metapac#197](https://github.com/ripytide/metapac/issues/197). The successor to the archived `pacdef` below, and actively maintained. |
| [`neobundle`](https://github.com/Shougo/neobundle.vim) | ☠️ | Vim plugin manager | No commit since 2018-07-26, superseded by `dein`, itself superseded by `dpp`, both above. |
| [`pacapt`](https://github.com/icy/pacapt) | ☠️ | Cross-manager wrapper | Retired in 2022. All 19 of the package managers it drove are shipped by `mpm`. |
| [`pacdef`](https://github.com/steven-omaha/pacdef) | ☠️ | Arch meta package manager | Archived on 2025-08-05, README pointing to `metapac` above as its successor. |
| [`packer-aur`](https://github.com/keenerd/packer) | ☠️ | Arch AUR helper | No commit since 2016-03-25. Superseded by the same AUR helpers as `yaourt` below; the bare `packer` name belongs to HashiCorp's tool and to `packer-nvim` above, hence the suffix. |
| [`packer-nvim`](https://github.com/wbthomason/packer.nvim) | ☠️ | Neovim plugin manager | README has declared it unmaintained since August 2023, pointing at [`lazy`](managers/lazy.md), which `mpm` wraps, and at `pckr-nvim` below. |
| [`pathogen`](https://github.com/tpope/vim-pathogen) | ☠️ | Vim plugin manager | No commit since 2022-08-24. Its whole job, splicing plugin directories into `runtimepath`, became a Vim 8 and Neovim built-in, which is what [`vim-pack`](managers/vim-pack.md) wraps. |
| [`pckr-nvim`](https://github.com/lewis6991/pckr.nvim) | ❌ | Neovim plugin manager | Successor to `packer-nvim` above and actively developed, but drivable only from inside Neovim: no documented completion signal, and a confirmation prompt that blocks an unattended run by default ([lewis6991/pckr.nvim#12](https://github.com/lewis6991/pckr.nvim/issues/12)). |
| [`smart`](https://github.com/smartpm/smart) | ☠️ | Cross-manager wrapper | No commit since 2016-10-27. An early cross-distribution package manager over the RPM and dpkg archives among others, chasing the same goal as `mpm`; every archive it drove has a manager today. |
| [`sysget`](https://github.com/cvengler/sysget) | ☠️ | Cross-manager wrapper | Retired in 2019. All 21 of the package managers it drove are shipped by `mpm`. |
| [`upt`](https://github.com/sigoden/upt) | ❌ | Universal package-management syntax shim | Translates one CLI vocabulary onto whichever single OS-level manager is detected, never more than one per invocation, by the maintainer's own account: "*upt is just aliases, nothing more*" ([sigoden/upt#60](https://github.com/sigoden/upt/issues/60#issuecomment-2560419544)). |
| [`whohas`](https://github.com/whohas/whohas) | ☠️ | Cross-distribution search | Retired in 2015. All 16 of the distribution archives it queried have a manager in `mpm`. |
| [`yaourt`](https://github.com/archlinuxfr/yaourt) | ☠️ | Arch AUR helper | Archived, and self-described `[unmaintained]` in its own repository description, with no commit since 2018-12. The dominant AUR helper before `yay`; `mpm` wraps its successors [`yay`](managers/yay.md) and [`paru`](managers/paru.md). |
| [`zgenom`](https://github.com/jandamm/zgenom) | ❌ | Zsh plugin manager | Reports no version through any binary: its whole function set runs from `zgenom-api` to `zgenom-update` with no version command anywhere, so the probe that establishes a shell-function manager's presence has nothing to read and `mpm` could never consider it available. Its `list` compounds that by `cat`-ing the generated `init.zsh` verbatim rather than reporting an inventory. Actively maintained otherwise, and the successor to the retired `zgen`. |

```{hint}
None of these verdicts are permanent. If a tool here looks misjudged, make the case in a [new manager request](https://github.com/kdeldycke/meta-package-manager/issues/new?template=new-package-manager.yml) and the entry will be reassessed.
```

## Project-scoped dependency managers

Tools that resolve dependencies inside a working tree are out of scope today.

This is a big feature for the future, but is already delimited by the {attr}`~meta_package_manager.manager.ManagerScope.PROJECT` concept, the {meth}`~meta_package_manager.manager.PackageManager.discover_projects` extension point, and [issue #1725](https://github.com/kdeldycke/meta-package-manager/issues/1725).

`mpm` already covers the system-scoped part of these managers:

| Ecosystem             | Project files                                                                        | `mpm` manager                                                                    |
| :-------------------- | :----------------------------------------------------------------------------------- | :------------------------------------------------------------------------------- |
| C/C++                 | `conanfile.txt` (Conan), `vcpkg.json` (vcpkg)                                        | —                                                                                |
| Conda                 | `conda-lock.yml`                                                                     | [`conda`](managers/conda.md)                                                     |
| Go                    | `go.mod`, `go.sum`                                                                   | —                                                                                |
| Java                  | `pom.xml` (Maven), `build.gradle` (Gradle), `ivy.xml`                                | —                                                                                |
| JavaScript            | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`                   | [`npm`](managers/npm.md), [`yarn`](managers/yarn.md), [`pnpm`](managers/pnpm.md) |
| .NET                  | `*.csproj`, `packages.config` (NuGet)                                                | —                                                                                |
| Perl                  | `cpanfile`                                                                           | [`cpan`](managers/cpan.md)                                                       |
| PHP                   | `composer.json`, `composer.lock`                                                     | [`composer`](managers/composer.md)                                               |
| Python                | `requirements.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`                       | [`pip`](managers/pip.md), [`uv`](managers/uv.md)                                 |
| Ruby                  | `Gemfile`, `Gemfile.lock`                                                            | [`gem`](managers/gem.md)                                                         |
| Rust                  | `Cargo.toml`, `Cargo.lock`                                                           | [`cargo`](managers/cargo.md)                                                     |
| Swift and Objective-C | `Package.swift`, `Package.resolved` (SwiftPM), `Podfile`, `Podfile.lock` (CocoaPods) | —                                                                                |
