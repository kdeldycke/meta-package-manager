# {octicon}`circle-slash` Unsupported managers

`mpm` wraps [a long list of package managers](managers.md), but not everything that installs software onto a machine. This page is the canonical home for the tools deliberately left out, and for the reason each one is out. When a manager is missing from `mpm` *by decision*, that decision is recorded here rather than in a code comment, an issue thread or a commit message.

```{important}
Absence is usually not a decision. Most tools missing from `mpm` were never assessed at all: they are unwritten, not refused. See [Not a decision, just unwritten](#not-a-decision-just-unwritten) before reading a gap as a refusal.
```

## Deliberate exclusions

### Retired tools

A tool whose upstream is already dead is not a candidate. The [stability policy](https://github.com/kdeldycke/meta-package-manager/blob/main/CLAUDE.md) treats an abandoned upstream as grounds for flagging a manager `unmaintained`, hiding it from default selection, dropping it from the test matrices and eventually removing it altogether. A wrapper written for a tool that is already retired starts at the end of that lifecycle, so it is not written.

Seven of the tools below are tracked by the [benchmark](benchmark.md) because a competitor still drives them. The other three (`pacapt`, `sysget` and `whohas`) are `mpm`'s own closest peers: single-command wrappers that ran search, install, remove and upgrade across whatever package manager was on the host. All ten were audited on 2026-08-09:

| Tool                                                       | Kind                          | Upstream status                                                                                                                                                                      |
| :--------------------------------------------------------- | :---------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`antibody`](https://github.com/getantibody/antibody)      | Zsh plugin manager            | Archived on 2022-05-27, superseded by [`antidote`](https://github.com/mattmc3/antidote).                                                                                             |
| [`dein`](https://github.com/Shougo/dein.vim)               | Vim and Neovim plugin manager | Development stopped, superseded by [dpp.vim](https://github.com/Shougo/dpp.vim), last commit on 2025-09-13. Also fails [two of the three requirements](#what-a-manager-must-expose). |
| [`fundle`](https://github.com/danhper/fundle)              | Fish plugin manager           | No commit since 2023-01-05.                                                                                                                                                          |
| [`jetpack`](https://github.com/3ofcoins/jetpack)           | FreeBSD jail runtime          | Self-described prototype, no commit since 2018-10-25. Not a package manager to begin with.                                                                                           |
| [`neobundle`](https://github.com/Shougo/neobundle.vim)     | Vim plugin manager            | No commit since 2018-07-26, superseded by `dein`, itself superseded by dpp.vim.                                                                                                      |
| [`pacapt`](https://github.com/icy/pacapt)                  | Cross-manager wrapper         | Retired in 2022. All 19 of the package managers it drove are shipped by `mpm`.                                                                                                       |
| [`pacdef`](https://github.com/steven-omaha/pacdef)         | Arch meta package manager     | Archived on 2025-08-05.                                                                                                                                                              |
| [`packer-nvim`](https://github.com/wbthomason/packer.nvim) | Neovim plugin manager         | README has declared it unmaintained since August 2023, pointing at [lazy.nvim](https://github.com/folke/lazy.nvim) and [pckr.nvim](https://github.com/lewis6991/pckr.nvim).          |
| [`sysget`](https://github.com/cvengler/sysget)             | Cross-manager wrapper         | Retired in 2019. All 21 of the package managers it drove are shipped by `mpm`.                                                                                                       |
| [`whohas`](https://github.com/whohas/whohas)               | Cross-distribution search     | Retired in 2015. All 16 of the distribution archives it queried have a manager in `mpm`.                                                                                             |

Two lineages are worth reading as a whole, because `mpm` wraps their live end and skips the dead one. Shougo's Vim managers run `neobundle` → `dein` → `dpp.vim`, and Neovim has since absorbed the job into core, which is what [`vim-pack`](managers/vim-pack.md) wraps. On the Zsh side `antibody` gave way to `antidote`, and `mpm` wraps [`zinit`](managers/zinit.md).

:::{admonition} Coming from `pacapt`, `sysget` or `whohas`?
:class: tip
`mpm` covers the same cross-manager operations these three offered — search, install, remove, upgrade, sync and cleanup — across every backend they drove and many more, so their users can retire them and switch to `mpm`.
:::

One caveat for `whohas` users, since it worked differently from the other two: it queried the *remote* package archives of sixteen distributions at once, to answer "how does every other distribution package this?". `mpm` ships a manager for each of those distributions, but it searches the managers installed on the host, not the archives of distributions you do not run. The backends line up; that particular cross-distribution comparison does not.

A retired tool is not automatically removed from the [benchmark](benchmark.md): the comparison is a map of the territory, and a competitor that still drives a dead tool is a fact about the competitor.

### Project-scoped dependency managers

Tools that resolve dependencies inside a working tree are out of scope today, per the [system scope](#what-mpm-manages) rule below. This covers Poetry, Bundler, Maven, Gradle, NuGet, CocoaPods, Conan, vcpkg, Cabal and Stack, along with the project side of ecosystems `mpm` already wraps globally.

This is the one exclusion on this page that is a *not yet* rather than a *no*. {attr}`~meta_package_manager.manager.ManagerScope.PROJECT` reserves the concept, {meth}`~meta_package_manager.manager.PackageManager.discover_projects` reserves the extension point, and [issue #1725](https://github.com/kdeldycke/meta-package-manager/issues/1725) tracks the architectural work that would have to land first: a manager is currently a singleton with exactly one CLI path and one implicit scope.

Candidate ecosystems are catalogued below with the project files that signal each. Where `mpm` already ships a system-scoped manager, that manager is the one that would grow a project mode; a `—` marks an ecosystem that would need a brand new manager.

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

Microsoft's [Python Environment Tools](https://github.com/microsoft/python-environment-tools) is a useful reference for the discovery half of the problem: it locates Python environments (venv, conda, pyenv, pipenv, Poetry, uv, ...) across a machine, though it does not inventory their packages.

## What `mpm` manages

Every manager `mpm` ships is *system-scoped*: it installs and queries software machine-wide, so a single inventory can be taken of everything installed on a host and compared across managers. That is the property the whole tool is built on, and it is what decides whether a candidate belongs.

A tool that resolves dependencies confined to a working tree answers a different question: not "what is installed on this machine" but "what does this project pin". Both are useful, and they do not merge into one table.

## What a manager must expose

Three requirements are enforced in code. They are not preferences: a tool that cannot clear them cannot be wrapped in `mpm`'s current architecture, no matter how much work is thrown at it.

| Requirement          | Enforced by                                                    | What it rules out                                                                                                      |
| :------------------- | :------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------- |
| An executable CLI    | {attr}`~meta_package_manager.execution.CLIExecutor.executable` | A tool shipped only as a file meant to be *sourced*, with no binary anywhere and no interpreter to key the manager on. |
| A reportable version | {attr}`~meta_package_manager.manager.PackageManager.fresh`     | A tool that reports no version through any binary: without one the manager is never considered available.              |
| System scope         | {attr}`~meta_package_manager.manager.ManagerScope.SYSTEM`      | A tool whose packages live inside one project tree rather than on the machine.                                         |

The first two have an escape hatch worth knowing before declaring a tool impossible. A shell-function manager can be keyed on the interpreter that runs it instead of on its own sources: [`zinit`](managers/zinit.md) is wrapped that way, with Zsh as its CLI and its version probe doubling as the presence check. And a manager whose own binaries expose no version can name a companion binary through {attr}`~meta_package_manager.execution.CLIExecutor.version_cli`.

[dein.vim](https://github.com/Shougo/dein.vim) is the worked example of both escape hatches failing. It is Vimscript: `autoload/*.vim` files, mode `644`, no binary anywhere. Keying it on `nvim` or `vim` would mark it available on every machine that merely has an editor installed, and would collide with [`vim-pack`](managers/vim-pack.md), which legitimately keys on `nvim`. It reports no version either: the only version-shaped value in its source is `g:dein#_cache_version`, an internal state-format counter, and its releases are Git tags on a checkout whose location the user picks freely. Editor plugin managers are otherwise in scope: `vim-pack`, built into Neovim since `0.12`, covers dein's users.

## Not a decision, just unwritten

Everything else missing from `mpm` is missing because nobody has written it, not because it was weighed and rejected. No manager has ever been removed from `mpm`, no manager proposal has been declined, and no manager request has been closed as not-planned.

The [benchmark](benchmark.md) table is the honest map of that territory: it lists every manager `mpm` or one of its peers supports, so a blank in the `mpm` column marks a gap rather than a refusal. Of the 113 tools it tracks that `mpm` does not wrap, the 2026-08-09 audit found only seven to be dead: the plugin and meta managers listed under [retired tools](#retired-tools) above. The rest are alive and simply unwrapped.

Two large groups of entries there are worth reading correctly:

- **Tools that are not package managers.** Competitors like `topgrade` also drive system updaters, dotfile managers and single-application updaters. Those are outside `mpm`'s domain by definition, not by decision.
- **Runtime and version managers.** `mpm` wraps [`asdf`](managers/asdf.md), [`mise`](managers/mise.md) and [`volta`](managers/volta.md) for the tools they install globally. Their per-project pinning is the project-scope question above.

If a manager you want is absent, it is very likely available for the writing: the [add a new manager](add-new-manager.md) guide walks through both the declarative and the Python paths, and many managers need only a short TOML file.

## Supported but at risk

A manager can also be *supported* and still be on notice, which is a different axis from this page. Managers whose upstream is retired or abandoned carry an `unmaintained` flag: they stay wrapped and usable, but are hidden from default selection, kept out of the test matrices, and may be dropped in any release. Managers whose upstream is merely slowing down carry an informational maintenance note instead. Both render on the manager's own page in the [manager index](managers.md).
