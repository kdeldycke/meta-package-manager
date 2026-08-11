# {octicon}`circle-slash` Unsupported managers

`mpm` wraps [a long list of package managers](managers.md), but not everything that installs software. This page records the tools left out *by decision*, and why.

```{important}
Absence is usually not a decision. Most tools missing from `mpm` were never assessed at all. See [Not a decision, just unwritten](#not-a-decision-just-unwritten) before reading a gap as a refusal.
```

## Deliberate exclusions

Two reasons put a tool in the table below.

Its upstream is dead. The [stability policy](https://github.com/kdeldycke/meta-package-manager/blob/main/CLAUDE.md) flags an abandoned manager `unmaintained`, hides it from default selection and eventually drops it, so a wrapper for an already-retired tool would start at the end of that lifecycle. Ten of the fourteen entries are dead, audited on 2026-08-09: seven still appear in the [benchmark](benchmark.md) because a competitor drives them, and the other three (`pacapt`, `sysget`, `whohas`) were `mpm`'s own closest peers.

Or it owns no registry. A tool that only unifies syntax or declarations across other managers reaches no package `mpm` cannot already reach directly. The remaining four were excluded on that ground rather than for being unmaintained — three are actively developed — and audited on 2026-08-11 alongside the [benchmark](benchmark.md) columns for [`upt`](https://github.com/sigoden/upt) and [`metapac`](https://github.com/ripytide/metapac).

| Tool                                                       | Kind                                      | Why not wrapped                                                                                                                                                                                                                                                                          |
| :--------------------------------------------------------- | :---------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`antibody`](https://github.com/getantibody/antibody)      | Zsh plugin manager                        | Archived on 2022-05-27, superseded by [`antidote`](https://github.com/mattmc3/antidote).                                                                                                                                                                                                 |
| [`decman`](https://github.com/kiviktnm/decman)             | Arch declarative system manager           | No operation verbs at all, flags only: every run reconciles the whole declared state. Its packages come from pacman and its own in-house AUR builder, both already `mpm` territory. Also manages dotfiles, systemd units, users and PGP keys, outside [system scope](#what-mpm-manages). |
| [`declaro`](https://github.com/mantinhas/declaro)          | Single-manager declarative wrapper        | Snapshots one already-installed manager at a time into an editable package list. No unique registry, no license, and its own multi-manager request has sat unaddressed since December 2025 ([mantinhas/declaro#31](https://github.com/mantinhas/declaro/issues/31)).                     |
| [`dein`](https://github.com/Shougo/dein.vim)               | Vim and Neovim plugin manager             | Development stopped, superseded by [dpp.vim](https://github.com/Shougo/dpp.vim), last commit on 2025-09-13. Also fails [two of the three requirements](#what-a-manager-must-expose).                                                                                                     |
| [`fundle`](https://github.com/danhper/fundle)              | Fish plugin manager                       | No commit since 2023-01-05.                                                                                                                                                                                                                                                              |
| [`jetpack`](https://github.com/3ofcoins/jetpack)           | FreeBSD jail runtime                      | Self-described prototype, no commit since 2018-10-25. Not a package manager to begin with.                                                                                                                                                                                               |
| [`metapac`](https://github.com/ripytide/metapac)           | Declarative multi-backend package manager | Delegates to 21 backends `mpm` already wraps directly. No per-package `install`/`remove` verb: removed by design, see [ripytide/metapac#197](https://github.com/ripytide/metapac/issues/197). The successor to the archived `pacdef` below, and actively maintained.                     |
| [`neobundle`](https://github.com/Shougo/neobundle.vim)     | Vim plugin manager                        | No commit since 2018-07-26, superseded by `dein`, itself superseded by dpp.vim.                                                                                                                                                                                                          |
| [`pacapt`](https://github.com/icy/pacapt)                  | Cross-manager wrapper                     | Retired in 2022. All 19 of the package managers it drove are shipped by `mpm`.                                                                                                                                                                                                           |
| [`pacdef`](https://github.com/steven-omaha/pacdef)         | Arch meta package manager                 | Archived on 2025-08-05, README pointing to `metapac` above as its successor.                                                                                                                                                                                                             |
| [`packer-nvim`](https://github.com/wbthomason/packer.nvim) | Neovim plugin manager                     | README has declared it unmaintained since August 2023, pointing at [lazy.nvim](https://github.com/folke/lazy.nvim) and [pckr.nvim](https://github.com/lewis6991/pckr.nvim).                                                                                                              |
| [`sysget`](https://github.com/cvengler/sysget)             | Cross-manager wrapper                     | Retired in 2019. All 21 of the package managers it drove are shipped by `mpm`.                                                                                                                                                                                                           |
| [`upt`](https://github.com/sigoden/upt)                    | Universal package-management syntax shim  | Translates one CLI vocabulary onto whichever single OS-level manager is detected, never more than one per invocation, by the maintainer's own account: "*upt is just aliases, nothing more*" ([sigoden/upt#60](https://github.com/sigoden/upt/issues/60#issuecomment-2560419544)).       |
| [`whohas`](https://github.com/whohas/whohas)               | Cross-distribution search                 | Retired in 2015. All 16 of the distribution archives it queried have a manager in `mpm`.                                                                                                                                                                                                 |

Three lineages account for most of the plugin managers above, and `mpm` wraps the live end of each. Shougo's Vim managers run `neobundle` → `dein` → `dpp.vim`, and Neovim has since absorbed the job into core, which is what [`vim-pack`](managers/vim-pack.md) wraps. On the Zsh side `antibody` gave way to `antidote`, and `mpm` wraps [`zinit`](managers/zinit.md).

packer.nvim forks rather than runs in a line, its notice naming two successors, and `mpm` wraps neither. lazy.nvim has a non-interactive contract (`nvim --headless "+Lazy! sync" +qa`, [documented here](https://lazy.folke.io/usage)) and a JSON lockfile, which makes it a *not yet*: what is missing is a decision on which operations a plugin manager can support when it cannot install a plugin absent from the user's own Lua config. pckr.nvim has no such contract — no documented completion signal, a confirmation prompt that blocks by default, and a maintainer declining synchronous behavior ([lewis6991/pckr.nvim#12](https://github.com/lewis6991/pckr.nvim/issues/12)).

:::{admonition} Coming from `pacapt`, `sysget` or `whohas`?
:class: tip
`mpm` covers the same cross-manager operations these three offered — search, install, remove, upgrade, sync and cleanup — across every backend they drove and many more.
:::

`whohas` is the one partial match: it queried the *remote* archives of sixteen distributions at once, while `mpm` searches the managers installed on the host. The backends line up; that cross-distribution comparison does not.

A retired tool is not dropped from the [benchmark](benchmark.md): a competitor that still drives a dead tool is a fact about the competitor.

## Project-scoped dependency managers

Tools that resolve dependencies inside a working tree are out of scope today, per the [system scope](#what-mpm-manages) rule below. This covers Poetry, Bundler, Maven, Gradle, NuGet, CocoaPods, Conan, vcpkg, Cabal and Stack, along with the project side of ecosystems `mpm` already wraps globally.

This is a *not yet* rather than a *no*, like `lazy.nvim` [above](#deliberate-exclusions). {attr}`~meta_package_manager.manager.ManagerScope.PROJECT` reserves the concept, {meth}`~meta_package_manager.manager.PackageManager.discover_projects` reserves the extension point, and [issue #1725](https://github.com/kdeldycke/meta-package-manager/issues/1725) tracks the blocker: a manager is currently a singleton with exactly one CLI path and one implicit scope.

Where `mpm` already ships a system-scoped manager, that manager is the one that would grow a project mode; a `—` marks an ecosystem that would need a brand new one.

| Ecosystem             | Project files                                                                        | `mpm` manager         |
| :-------------------- | :----------------------------------------------------------------------------------- | :-------------------- |
| C/C++                 | `conanfile.txt` (Conan), `vcpkg.json` (vcpkg)                                        | —                     |
| Conda                 | `conda-lock.yml`                                                                     | `conda`               |
| Go                    | `go.mod`, `go.sum`                                                                   | —                     |
| Java                  | `pom.xml` (Maven), `build.gradle` (Gradle), `ivy.xml`                                | —                     |
| JavaScript            | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`                   | `npm`, `yarn`, `pnpm` |
| .NET                  | `*.csproj`, `packages.config` (NuGet)                                                | —                     |
| Perl                  | `cpanfile`                                                                           | `cpan`                |
| PHP                   | `composer.json`, `composer.lock`                                                     | `composer`            |
| Python                | `requirements.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`                       | `pip`, `uv`           |
| Ruby                  | `Gemfile`, `Gemfile.lock`                                                            | `gem`                 |
| Rust                  | `Cargo.toml`, `Cargo.lock`                                                           | `cargo`               |
| Swift and Objective-C | `Package.swift`, `Package.resolved` (SwiftPM), `Podfile`, `Podfile.lock` (CocoaPods) | —                     |

Microsoft's [Python Environment Tools](https://github.com/microsoft/python-environment-tools) covers the discovery half of the problem: it locates Python environments (venv, conda, pyenv, pipenv, Poetry, uv, ...) across a machine, without inventorying their packages.

## What `mpm` manages

Every manager `mpm` ships is *system-scoped*: it installs and queries software machine-wide, so a single inventory can cover a host and be compared across managers. That property is what the whole tool is built on, and what decides whether a candidate belongs.

A tool that resolves dependencies confined to a working tree answers a different question: not "what is installed on this machine" but "what does this project pin". Both are useful, and they do not merge into one table.

## What a manager must expose

Three requirements are enforced in code. A tool that cannot clear them cannot be wrapped in `mpm`'s current architecture.

| Requirement          | Enforced by                                                    | What it rules out                                                                                                      |
| :------------------- | :------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------- |
| An executable CLI    | {attr}`~meta_package_manager.execution.CLIExecutor.executable` | A tool shipped only as a file meant to be *sourced*, with no binary anywhere and no interpreter to key the manager on. |
| A reportable version | {attr}`~meta_package_manager.manager.PackageManager.fresh`     | A tool that reports no version through any binary: without one the manager is never considered available.              |
| System scope         | {attr}`~meta_package_manager.manager.ManagerScope.SYSTEM`      | A tool whose packages live inside one project tree rather than on the machine.                                         |

The first two have escape hatches worth knowing before declaring a tool impossible. A shell-function manager can key on the interpreter that runs it instead of on its own sources: [`zinit`](managers/zinit.md) is wrapped that way, with Zsh as its CLI and its version probe doubling as the presence check. A manager whose own binaries expose no version can name a companion through {attr}`~meta_package_manager.execution.CLIExecutor.version_cli`.

[dein.vim](https://github.com/Shougo/dein.vim) is the worked example of both hatches failing. It is Vimscript with no binary anywhere, so keying it on `nvim` or `vim` would mark it available on every machine that merely has an editor, and would collide with [`vim-pack`](managers/vim-pack.md), which legitimately keys on `nvim`. It reports no version either: `g:dein#_cache_version` is an internal state-format counter, and its releases are Git tags on a checkout the user places freely. Editor plugin managers are otherwise in scope — `vim-pack`, built into Neovim since `0.12`, covers dein's users.

## Not a decision, just unwritten

Everything else missing from `mpm` is unwritten, not rejected. No manager has ever been removed, no proposal declined, no request closed as not-planned.

The [benchmark](benchmark.md) maps that territory, and its `mpm` column separates the two cases: every tool listed above renders as a `❌` linking back here, so a *blank* cell is the real marker of a gap nobody has assessed.

Two groups of entries there are easy to misread:

- Tools that are not package managers. Competitors like `topgrade` also drive system updaters, dotfile managers and single-application updaters, outside `mpm`'s domain by definition.
- Runtime and version managers. `mpm` wraps [`asdf`](managers/asdf.md), [`mise`](managers/mise.md) and [`volta`](managers/volta.md) for what they install globally; their per-project pinning is the project-scope question above.

If a manager you want is absent, it is likely available for the writing: the [add a new manager](add-new-manager.md) guide covers both the declarative and the Python paths, and many managers need only a short TOML file.

## Supported but at risk

A manager can be *supported* and still on notice, which is a different axis from this page. An `unmaintained` flag keeps a manager wrapped and usable but hidden from default selection, out of the test matrices, and droppable in any release; a merely slowing upstream carries an informational maintenance note instead. Both render on the manager's own page in the [manager index](managers.md).
