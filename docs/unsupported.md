# {octicon}`circle-slash` Unsupported managers

`mpm` wraps [a long list of package managers](managers.md), but not everything that installs software onto a machine. This page is the canonical home for the tools deliberately left out, and for the reason each one is out. When a manager is missing from `mpm` *by decision*, that decision is recorded here rather than in a code comment, an issue thread or a commit message.

```{important}
Absence is usually not a decision. Most tools missing from `mpm` were never assessed at all: they are unwritten, not refused. See [Not a decision, just unwritten](#not-a-decision-just-unwritten) before reading a gap as a refusal.
```

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

## Deliberate exclusions

### `dein.vim`

[dein.vim](https://github.com/Shougo/dein.vim) is a Vim and Neovim plugin manager. Editor plugin managers are in scope, and `mpm` ships two of them ([`vim-pack`](managers/vim-pack.md) and [`zinit`](managers/zinit.md) for the Zsh side), so the exclusion is specific to dein rather than to its category.

It fails two of the three requirements above at once:

- **No executable CLI.** dein is Vimscript. It ships `autoload/*.vim` files, mode `644`, and no binary at all, so nothing resolves as an executable `cli_path`. The interpreter escape hatch that rescues `zinit` does not apply either: keying dein on `nvim` or `vim` would mark it available on every machine that merely has an editor installed, and would collide with `vim-pack`, which legitimately keys on `nvim`.
- **No reportable version.** dein exposes no version at runtime. The only version-shaped value in its source is `g:dein#_cache_version`, an internal state-format counter, not a release number. Its releases are Git tags on a checkout whose location the user picks freely.

Two further limits would remain even if those were solved. `dein#get_updated_plugins()` only works once the user sets `g:dein#install_github_api_token`, so `outdated` is unavailable by default. And dein has no per-plugin uninstall: plugins are declared in the user's `vimrc`, and `dein#check_clean()` merely reports orphaned directories.

Upstream is also frozen. The README states that *"Active developement on dein.vim has stopped. The only future changes will be bug fixes"*, the project is superseded by [dpp.vim](https://github.com/Shougo/dpp.vim), and the last commit landed on 2025-09-13. Under the [stability policy](https://github.com/kdeldycke/meta-package-manager/blob/main/CLAUDE.md) that makes it `unmaintained` on arrival: hidden from default selection and kept out of the test matrices. Wrapping it would mean shipping a manager that misdetects, misreports its version, and is invisible by default.

Neovim users are covered by [`vim-pack`](managers/vim-pack.md), the plugin manager built into Neovim since `0.12`.

### Retired upstreams

A tool whose upstream is already dead is not a candidate. The [stability policy](https://github.com/kdeldycke/meta-package-manager/blob/main/CLAUDE.md) treats an abandoned upstream as grounds for flagging a manager `unmaintained`, hiding it from default selection, dropping it from the test matrices and eventually removing it altogether. A wrapper written for a tool that is already retired starts at the end of that lifecycle, so it is not written.

The [benchmark](benchmark.md) tracks these tools because a competitor still drives them. Their upstream status was audited on 2026-08-09:

| Tool                                                       | Kind                          | Upstream status                                                                                                                                                             |
| :--------------------------------------------------------- | :---------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`antibody`](https://github.com/getantibody/antibody)      | Zsh plugin manager            | Archived on 2022-05-27, superseded by [`antidote`](https://github.com/mattmc3/antidote).                                                                                    |
| [`dein`](https://github.com/Shougo/dein.vim)               | Vim and Neovim plugin manager | Development stopped, superseded by [dpp.vim](https://github.com/Shougo/dpp.vim). See [above](#dein-vim).                                                                    |
| [`fundle`](https://github.com/danhper/fundle)              | Fish plugin manager           | No commit since 2023-01-05.                                                                                                                                                 |
| [`jetpack`](https://github.com/3ofcoins/jetpack)           | FreeBSD jail runtime          | Self-described prototype, no commit since 2018-10-25. Not a package manager to begin with.                                                                                  |
| [`neobundle`](https://github.com/Shougo/neobundle.vim)     | Vim plugin manager            | No commit since 2018-07-26, superseded by `dein`, itself superseded by dpp.vim.                                                                                             |
| [`packer-nvim`](https://github.com/wbthomason/packer.nvim) | Neovim plugin manager         | README has declared it unmaintained since August 2023, pointing at [lazy.nvim](https://github.com/folke/lazy.nvim) and [pckr.nvim](https://github.com/lewis6991/pckr.nvim). |
| [`pacdef`](https://github.com/steven-omaha/pacdef)         | Arch meta package manager     | Archived on 2025-08-05.                                                                                                                                                     |

Two lineages are worth reading as a whole, because `mpm` wraps their live end and skips the dead one. Shougo's Vim managers run `neobundle` → `dein` → `dpp.vim`, and Neovim has since absorbed the job into core, which is what [`vim-pack`](managers/vim-pack.md) wraps. On the Zsh side `antibody` gave way to `antidote`, and `mpm` wraps [`zinit`](managers/zinit.md).

A retired tool is not automatically removed from the [benchmark](benchmark.md): the comparison is a map of the territory, and a competitor that still drives a dead tool is a fact about the competitor.

### Retired peers

`pacapt`, `sysget` and `whohas` were `mpm`'s closest peers: single-command wrappers that ran search, install, remove and upgrade across whatever package manager was on the host. All three are retired, so the rule above applies to them too and `mpm` does not wrap them.

Their backend coverage was surveyed on 2026-08-09 against the manager pool, and every backend the three drove is a manager `mpm` ships today:

| Peer                                           | Retired since | Backends                 | Shipped by `mpm` |
| :--------------------------------------------- | :------------ | :----------------------- | ---------------: |
| [`pacapt`](https://github.com/icy/pacapt)      | 2022          | 19 package managers      |         19 of 19 |
| [`sysget`](https://github.com/cvengler/sysget) | 2019          | 21 package managers      |         21 of 21 |
| [`whohas`](https://github.com/whohas/whohas)   | 2015          | 16 distribution archives |         16 of 16 |

:::\{admonition} Coming from `pacapt`, `sysget` or `whohas`?
:class: tip
`mpm` covers the same cross-manager operations these three offered — search, install, remove, upgrade, sync and cleanup — across every backend they drove and many more, so their users can retire them and switch to `mpm`.
:::

One caveat for `whohas` users, since it worked differently from the other two: it queried the *remote* package archives of sixteen distributions at once, to answer "how does every other distribution package this?". `mpm` ships a manager for each of those distributions, but it searches the managers installed on the host, not the archives of distributions you do not run. The backends line up; that particular cross-distribution comparison does not.

### Project-scoped dependency managers

Tools that resolve dependencies inside a working tree are out of scope today, per the system-scope rule above. This covers Poetry, Bundler, Maven, Gradle, NuGet, CocoaPods, Conan, vcpkg, Cabal and Stack, along with the project side of ecosystems `mpm` already wraps globally.

This is the one exclusion on this page that is a *not yet* rather than a *no*. {attr}`~meta_package_manager.manager.ManagerScope.PROJECT` reserves the concept, {meth}`~meta_package_manager.manager.PackageManager.discover_projects` reserves the extension point, and [issue #1725](https://github.com/kdeldycke/meta-package-manager/issues/1725) tracks the architectural work that would have to land first: a manager is currently a singleton with exactly one CLI path and one implicit scope.

Candidate ecosystems are catalogued below with the project files that signal each, split by whether `mpm` already ships a system-scoped manager that could grow a project mode or a brand new manager would be needed.

Ecosystems that would extend an existing manager:

| Ecosystem  | Manager               | Project files                                                      |
| :--------- | :-------------------- | :----------------------------------------------------------------- |
| JavaScript | `npm`, `yarn`, `pnpm` | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| PHP        | `composer`            | `composer.json`, `composer.lock`                                   |
| Perl       | `cpan`                | `cpanfile`                                                         |
| Python     | `pip`, `uv`           | `requirements.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`     |
| Ruby       | `gem`                 | `Gemfile`, `Gemfile.lock`                                          |
| Rust       | `cargo`               | `Cargo.toml`, `Cargo.lock`                                         |

Ecosystems that would need a new manager:

| Ecosystem | Project files                                         |
| :-------- | :---------------------------------------------------- |
| C/C++     | `conanfile.txt` (Conan), `vcpkg.json` (vcpkg)         |
| Conda     | `conda-lock.yml`                                      |
| Go        | `go.mod`, `go.sum`                                    |
| Java      | `pom.xml` (Maven), `build.gradle` (Gradle), `ivy.xml` |
| .NET      | `*.csproj`, `packages.config` (NuGet)                 |
| CocoaPods | `Podfile`, `Podfile.lock`                             |
| Swift     | `Package.swift`, `Package.resolved`                   |

Microsoft's [Python Environment Tools](https://github.com/microsoft/python-environment-tools) is a useful reference for the discovery half of the problem: it locates Python environments (venv, conda, pyenv, pipenv, Poetry, uv, ...) across a machine, though it does not inventory their packages.

## Not a decision, just unwritten

Everything else missing from `mpm` is missing because nobody has written it, not because it was weighed and rejected. No manager has ever been removed from `mpm`, no manager proposal has been declined, and no manager request has been closed as not-planned.

The [benchmark](benchmark.md) table is the honest map of that territory: it lists every manager `mpm` or one of its peers supports, so a blank in the `mpm` column marks a gap rather than a refusal. Of the 113 tools it tracks that `mpm` does not wrap, the 2026-08-09 audit found only the seven [retired upstreams](#retired-upstreams) above to be dead: the rest are alive and simply unwrapped.

Two large groups of entries there are worth reading correctly:

- **Tools that are not package managers.** Competitors like `topgrade` also drive system updaters, dotfile managers and single-application updaters. Those are outside `mpm`'s domain by definition, not by decision.
- **Runtime and version managers.** `mpm` wraps [`asdf`](managers/asdf.md), [`mise`](managers/mise.md) and [`volta`](managers/volta.md) for the tools they install globally. Their per-project pinning is the project-scope question above.

If a manager you want is absent, it is very likely available for the writing: the [add a new manager](add-new-manager.md) guide walks through both the declarative and the Python paths, and many managers need only a short TOML file.

## Supported but at risk

A manager can also be *supported* and still be on notice, which is a different axis from this page. Managers whose upstream is retired or abandoned carry an `unmaintained` flag: they stay wrapped and usable, but are hidden from default selection, kept out of the test matrices, and may be dropped in any release. Managers whose upstream is merely slowing down carry an informational maintenance note instead. Both render on the manager's own page in the [manager index](managers.md).
