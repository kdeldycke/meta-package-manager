# {octicon}`cross-reference` Upstream

`mpm` sits on a large ecosystem: the package managers it wraps, the menu-bar frontends hosting its plugin, the libraries it imports, and the toolchain compiling its binaries. This page records what the project sends back to those upstreams: merged fixes, bug reports, and the workarounds it carries where an upstream declined or has not moved yet.

Two neighboring inventories live elsewhere:

- Contributions to Click, `python-tabulate`, Pygments, Sphinx and the rest of the CLI and documentation toolchain are tracked on [Click Extra's own upstream page](https://kdeldycke.github.io/click-extra/upstream.html).
- Submissions of `mpm` itself to distribution channels are catalogued in [the packaging page](packaging.md).

## Code contributed upstream

### [Nuitka](https://github.com/Nuitka/Nuitka)

Every release ships standalone binaries compiled by Nuitka, and that lane keeps returning fixes for the packages `mpm` bundles:

- [Nuitka/Nuitka#3578](https://github.com/Nuitka/Nuitka/pull/3578): Add missing data file for `rfc3987_syntax` package.
- [Nuitka/Nuitka#3446](https://github.com/Nuitka/Nuitka/pull/3446): Add missing data file for `cyclonedx` package.
- [Nuitka/Nuitka#3037](https://github.com/Nuitka/Nuitka/pull/3037): Typo in `license_expression` package ID.
- [Nuitka/Nuitka#3033](https://github.com/Nuitka/Nuitka/pull/3033): Add data file for `license-expression` package.
- [Nuitka/Nuitka#2021](https://github.com/Nuitka/Nuitka/pull/2021): Standalone: Add invisible `md__mypyc` dependency for `charset_normalizer`.
- [Nuitka/Nuitka#1918](https://github.com/Nuitka/Nuitka/pull/1918): Standalone: Added data file for `lark` package.

### [xbar plugin repository](https://github.com/matryer/xbar-plugins)

The [bar plugin](bar-plugin.md) started its life inside the central plugin repository of BitBar, the project since reborn as Xbar:

- [matryer/xbar-plugins#466](https://github.com/matryer/xbar-plugins/pull/466) is the initial submission of a generic package manager plugin, and [matryer/xbar-plugins#469](https://github.com/matryer/xbar-plugins/pull/469) extended it to Python packages. Thirteen further release-upgrade pull requests were merged after those two.
- When the repository went dormant, two upgrades ([matryer/xbar-plugins#1459](https://github.com/matryer/xbar-plugins/pull/1459), [matryer/xbar-plugins#1479](https://github.com/matryer/xbar-plugins/pull/1479)) sat unreviewed until they were obsolete, so [matryer/xbar-plugins#525](https://github.com/matryer/xbar-plugins/issues/525) moved the plugin into this repository, where it now ships with each `mpm` release.
- The copy in the plugin repository is still refreshed from here, most recently by [matryer/xbar-plugins#2018](https://github.com/matryer/xbar-plugins/pull/2018).

### [boltons](https://github.com/mahmoud/boltons)

`mpm` strips ANSI sequences out of manager output before parsing it, through `boltons.strutils.strip_ansi`:

- [mahmoud/boltons#257](https://github.com/mahmoud/boltons/issues/257) reported the function eating characters that were not ANSI codes, and [mahmoud/boltons#258](https://github.com/mahmoud/boltons/pull/258) rewrote the stripping with a regex and tests.

### [Poetry](https://github.com/python-poetry/poetry)

Poetry was the project's build backend before uv:

- [python-poetry/poetry#2579](https://github.com/python-poetry/poetry/issues/2579) asked for Trove classifiers to be sourced from the canonical PyPA definitions, and [python-poetry/poetry#2881](https://github.com/python-poetry/poetry/pull/2881) implemented the validation.
- The `main()` indirection of `meta_package_manager/__main__.py`, required to reconcile Poetry's script entry points ([python-poetry/poetry#5981](https://github.com/python-poetry/poetry/issues/5981)), is still in place.

### Project listings

- [awesomeSBOM/awesome-sbom#37](https://github.com/awesomeSBOM/awesome-sbom/pull/37) and [CycloneDX/cyclonedx.org-archived#319](https://github.com/CycloneDX/cyclonedx.org-archived/pull/319) list `mpm` among SBOM producers.
- [ripytide/metapac#239](https://github.com/ripytide/metapac/pull/239) adds `mpm` to the reference list of a fellow meta manager.

## Upstreamed from meta-package-manager

Problems this project hit first and reported upstream, since fixed there.

### [SwiftBar](https://github.com/swiftbar/SwiftBar)

- [swiftbar/SwiftBar#445](https://github.com/swiftbar/SwiftBar/issues/445): environment variable defaults were mangled by escaping. The plugin still quotes its defaults, so it keeps working on the SwiftBar releases from before the fix.
- [swiftbar/SwiftBar#308](https://github.com/swiftbar/SwiftBar/issues/308): shell parameters were over-escaped.
- [swiftbar/SwiftBar#306](https://github.com/swiftbar/SwiftBar/issues/306): a `font=` parameter blocked execution of the menu entry carrying it.

### `mas`

- [mas-cli/mas#1248](https://github.com/mas-cli/mas/issues/1248): `--json` output contained unescaped control characters. The permissive decoding in [`mas`](managers/mas.md)'s wrapper stays, for the releases still in the wild.

### `uv`

- [astral-sh/uv#19089](https://github.com/astral-sh/uv/issues/19089): a span-shaped `exclude-newer-package` value resolved to a no-op timestamp.
- [astral-sh/uv#18010](https://github.com/astral-sh/uv/issues/18010): `uv` failed to install `Nuitka>=4` while `pip` could.
- [astral-sh/uv#16312](https://github.com/astral-sh/uv/issues/16312) and [astral-sh/uv#11234](https://github.com/astral-sh/uv/issues/11234): binaries built from a `uv`-installed Python broke on macOS `arm64` and Ubuntu runners. Both were also chased from the other side of the fence, as [Nuitka/Nuitka#3637](https://github.com/Nuitka/Nuitka/issues/3637) and [Nuitka/Nuitka#3325](https://github.com/Nuitka/Nuitka/issues/3325).

### [Nuitka](https://github.com/Nuitka/Nuitka)

- [Nuitka/Nuitka#3909](https://github.com/Nuitka/Nuitka/issues/3909): `--project` ignored the `[tool.nuitka]` section of `pyproject.toml`.
- [Nuitka/Nuitka#3750](https://github.com/Nuitka/Nuitka/issues/3750): `--project` did not recognize the `uv_build` build backend.
- [Nuitka/Nuitka#3173](https://github.com/Nuitka/Nuitka/issues/3173): the `nuitka` CLI was not found on Windows when installed with `uv`.
- [Nuitka/Nuitka#2020](https://github.com/Nuitka/Nuitka/issues/2020): compiled binaries missed `charset_normalizer` data files, fixed by the matching pull request above.

## Addressed by meta-package-manager

The user-facing inventory of what `mpm` backfills on top of native tools is [the augmentations page](augmentations.md). The entries below link each backfill to the upstream decision or gap behind it.

### Search

[`yarn`](managers/yarn.md) closed the request for a search command without shipping one ([yarnpkg/yarn#778](https://github.com/yarnpkg/yarn/issues/778)). `mpm` simulates exact-match search through `yarn info`.

### Full upgrade

[`pip`](managers/pip.md) never grew an upgrade-all command ([pypa/pip#59](https://github.com/pypa/pip/issues/59)). `mpm` synthesizes it by upgrading each outdated package one by one.

### Outdated queries

[`dotnet`](managers/dotnet.md) never implemented `dotnet tool list --outdated`: an SDK maintainer wrote the spec in [dotnet/sdk#22853](https://github.com/dotnet/sdk/issues/22853), which was then closed as not planned. `mpm` checks the installed tools against NuGet itself, without mutating them.

[`brew`](managers/brew.md) rejects `--formula` next to `--greedy` ever since [Homebrew/brew#8229](https://github.com/Homebrew/brew/pull/8229) added the selector to `brew upgrade`, and tolerating the pair as a no-op was declined in [Homebrew/brew#16135](https://github.com/Homebrew/brew/issues/16135). `mpm` shapes its formula and cask outdated queries around the conflict.

### Version detection

[`scoop`](managers/scoop.md) does not always report a clean version of itself ([ScoopInstaller/Scoop#6457](https://github.com/ScoopInstaller/Scoop/issues/6457), still open). `mpm` recovers the version from a `tag: vX.Y.Z` ref or a `Bump to version` commit subject.

### Concurrency

Parallel conda transactions corrupt packages and caches rather than block on a lock, and upstream closed the report as not planned ([conda/conda#13037](https://github.com/conda/conda/issues/13037)). `mpm` folds [`conda`](managers/conda.md), [`mamba`](managers/mamba.md) and [`micromamba`](managers/micromamba.md) into one serial lane instead: see [the concurrency page](concurrency.md).

### Cooldown

[`yay`](managers/yay.md) exposes no hook for a release-age gate, so `mpm` injects one through an `init.lua` hook. The request for a less invasive injection point is open at [Jguer/yay#2883](https://github.com/Jguer/yay/issues/2883). The full per-manager inventory of cooldown support is on [the cooldown page](cooldown.md).

### Privilege escalation

Microsoft's Windows `sudo` caches no credentials, so each escalation raises its own UAC dialog: the cache request is open at [microsoft/sudo#7](https://github.com/microsoft/sudo/issues/7), and `gsudo` has the same gap at [gerardog/gsudo#378](https://github.com/gerardog/gsudo/issues/378) for its password path. `mpm` ranks `gsudo` first and warms whichever escalator can be primed: see [the privilege elevation page](sudo.md).

### Bar plugin

Xbar mangles quoted version specifiers in dependency metadata ([matryer/xbar#831](https://github.com/matryer/xbar/issues/831)) and truncates a variable default at its first `=` character ([matryer/xbar#832](https://github.com/matryer/xbar/issues/832)). The plugin therefore pins no version in its metadata and declares its font variables SwiftBar-only. SwiftBar closed the request for plugin input parameters as not planned ([swiftbar/SwiftBar#160](https://github.com/swiftbar/SwiftBar/issues/160)), so configuration goes through plugin variables instead.

### GNOME Shell extension

GNOME Shell raises a `TypeError` when a submenu opens or closes in a `PopupMenuSection` that no menu registered with `addMenuItem()` ([GNOME/gnome-shell#9424](https://gitlab.gnome.org/GNOME/gnome-shell/-/work_items/9424)). The [extension](gnome-shell.md) holds its scrollable report in such a section. It therefore gives that section its own `_setOpenedSubMenu` method.

`shexli`, the static analyzer extensions.gnome.org runs on each upload, segfaults with `tree-sitter` `0.26.0` ([Infrastructure/extensions-web#398](https://gitlab.gnome.org/Infrastructure/extensions-web/-/work_items/398)). Its `tree-sitter>=0.25.0` requirement allows that version, so the extension's `shexli` CI job pins `tree-sitter==0.25.2`.

## Declined by upstream

### [Homebrew](https://github.com/Homebrew/brew)

The SPDX documents `brew` generates point their `documentNamespace` at `https://formulae.brew.sh/spdx/...` URLs that 404, and publishing the missing files was declined ([Homebrew/brew#22741](https://github.com/Homebrew/brew/issues/22741)). `mpm`'s SPDX aggregation copies the value through verbatim, keeping the merged document consistent with its sources.

## Open upstream

### [Nuitka](https://github.com/Nuitka/Nuitka)

- [Nuitka/Nuitka#4025](https://github.com/Nuitka/Nuitka/issues/4025): `--project` refuses to build over a `py.typed` and over a dependency's package data.
- [Nuitka/Nuitka#4024](https://github.com/Nuitka/Nuitka/issues/4024): `--main-entry-point` whose CLI name matches its package builds a binary failing at startup.
- [Nuitka/Nuitka#3998](https://github.com/Nuitka/Nuitka/issues/3998): `enableCcache` overwrites a user-set `CCACHE_SLOPPINESS`.
- [Nuitka/Nuitka#3997](https://github.com/Nuitka/Nuitka/issues/3997): tool downloads are fetched and executed without integrity verification.
- [Nuitka/Nuitka#3996](https://github.com/Nuitka/Nuitka/issues/3996): `ccache` never hits across CI machines.
- [Nuitka/Nuitka#3994](https://github.com/Nuitka/Nuitka/issues/3994): dangling symlinks in `--include-data-dir` are silently skipped on Linux and break macOS signing.
- [Nuitka/Nuitka#3879](https://github.com/Nuitka/Nuitka/issues/3879): `--main-entry-point` does not populate the `_main_module` internal state.
- [Nuitka/Nuitka-website#125](https://github.com/Nuitka/Nuitka-website/issues/125): document how extras, wheel, onefile and standalone modes combine.

### `uv`

- [astral-sh/uv#18792](https://github.com/astral-sh/uv/issues/18792): prune stale `exclude-newer-package` entries on `uv lock`.

### [packageurl-python](https://github.com/package-url/packageurl-python)

- [package-url/packageurl-python#188](https://github.com/package-url/packageurl-python/pull/188): add `PURL_TYPES` and enforce validation of purl types. Until it lands, `mpm` ships its own purl-type mapping in `meta_package_manager/specifier.py`.

### [license-expression](https://github.com/aboutcode-org/license-expression)

- [aboutcode-org/license-expression#99](https://github.com/aboutcode-org/license-expression/issues/99): the `data` subfolder is missing from the package manifest. Its bundling side was patched in the Nuitka pull request above.

### [SwiftBar](https://github.com/swiftbar/SwiftBar)

- [swiftbar/SwiftBar#557](https://github.com/swiftbar/SwiftBar/issues/557): the badge count on a `fold=true` row sits right of its pill's center.
- [swiftbar/SwiftBar#555](https://github.com/swiftbar/SwiftBar/issues/555): nothing shows that plugin settings continue below the window edge, and the preferences window cannot be resized.

### Candidate managers

Reports filed while vetting tools for the [benchmark's queue](benchmark.md):

- [marwanhawari/stew#91](https://github.com/marwanhawari/stew/issues/91): a non-interactive mode is the blocker for wrapping `stew`.
- [lucasgelfond/zerobrew#404](https://github.com/lucasgelfond/zerobrew/issues/404): the `openssl@3` build breaks. An earlier report of Python package install failures ([lucasgelfond/zerobrew#336](https://github.com/lucasgelfond/zerobrew/issues/336)) was fixed within days.

### CI infrastructure

- [Cyberboss/install-winget#12](https://github.com/Cyberboss/install-winget/issues/12): runner compatibility for the action installing [`winget`](managers/winget.md) on `mpm`'s Windows test lane.

### Project listings

- [spdx/sbom-landscape#32](https://github.com/spdx/sbom-landscape/issues/32): add `mpm` to the SPDX landscape.
- [universalinstallscript/universalinstallscript#2](https://github.com/universalinstallscript/universalinstallscript/issues/2): `mpm install` as an implementation of [XKCD #1654](https://xkcd.com/1654/).
- [jakob-pennington/awesome-devsecops#83](https://github.com/jakob-pennington/awesome-devsecops/pull/83): add `mpm` to the DevSecOps list.
