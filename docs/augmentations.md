# {octicon}`plus-circle` Manager augmentations

Package managers are not comparable: some ship advanced features others lack. Rather than expose that unevenness, `mpm` backfills the missing pieces on top of the native tools, so every manager gains a consistent baseline.

## Managers gaining features

Each ✅ below is a capability `mpm` synthesizes for a manager that does not provide it natively. The rest of this page explains each column.

| Manager        | Full `upgrade --all` | Exact search | Extended search |
| :------------- | :------------------: | :----------: | :-------------: |
| `apk`          |                      |      ✅      |                 |
| `apm`          |                      |      ✅      |                 |
| `apt-mint`     |                      |              |       ✅        |
| `asdf`         |          ✅          |      ✅      |       ✅        |
| `cargo`        |                      |      ✅      |       ✅        |
| `composer`     |                      |      ✅      |                 |
| `conda`        |                      |      ✅      |       ✅        |
| `deb-get`      |                      |      ✅      |       ✅        |
| `dnf`          |                      |      ✅      |       ✅        |
| `dnf5`         |                      |      ✅      |       ✅        |
| `eopkg`        |                      |      ✅      |                 |
| `flatpak`      |                      |      ✅      |       ✅        |
| `gem`          |                      |              |       ✅        |
| `gh-ext`       |                      |      ✅      |       ✅        |
| `guix`         |                      |      ✅      |       ✅        |
| `mas`          |                      |      ✅      |       ✅        |
| `mise`         |                      |      ✅      |                 |
| `nix`          |                      |      ✅      |       ✅        |
| `npm`          |                      |      ✅      |                 |
| `opkg`         |                      |      ✅      |       ✅        |
| `pacaur`       |                      |              |       ✅        |
| `pacman`       |                      |              |       ✅        |
| `pacstall`     |                      |      ✅      |       ✅        |
| `paru`         |                      |              |       ✅        |
| `pip`          |          ✅          |              |                 |
| `pnpm`         |                      |      ✅      |                 |
| `pwsh-gallery` |                      |              |       ✅        |
| `scoop`        |                      |      ✅      |       ✅        |
| `sfsu`         |                      |      ✅      |       ✅        |
| `snap`         |                      |      ✅      |       ✅        |
| `soar`         |                      |      ✅      |       ✅        |
| `steamcmd`     |          ✅          |              |                 |
| `uv`           |          ✅          |              |                 |
| `xbps`         |                      |      ✅      |       ✅        |
| `yarn`         |                      |      ✅      |       ✅        |
| `yarn-berry`   |                      |      ✅      |       ✅        |
| `yay`          |                      |              |       ✅        |
| `yum`          |                      |      ✅      |       ✅        |

## Free `upgrade --all`

Some managers cannot upgrade every outdated package in a single command. [`pip`, for instance, has no full-upgrade subcommand](https://github.com/pypa/pip/issues/4551). When a manager only knows how to upgrade one package at a time, `mpm` synthesizes the bulk operation: it lists the outdated packages and upgrades them one by one, so `mpm upgrade --all` works everywhere.

```shell-session
$ mpm --pip upgrade --all
Updating all outdated packages from pip...
warning: pip doesn't seems to implement a full upgrade subcommand. Call
single-package upgrade CLI one by one.

Collecting boltons
  Using cached boltons-20.1.0-py2.py3-none-any.whl (169 kB)
Installing collected packages: boltons
Successfully installed boltons-20.1.0

Collecting graphviz
  Using cached graphviz-0.14-py2.py3-none-any.whl (18 kB)
Installing collected packages: graphviz
Successfully installed graphviz-0.14
(...)
```

Today this backfills `asdf`, `pip`, `steamcmd` and `uv` (the *Full `upgrade --all`* column above).

## Better search

`mpm` normalizes search across managers. Its `--exact` and `--extended` flags work against every manager, even those whose native search cannot filter that way: `mpm` runs the closest native query, then refilters the raw results itself to honor the flag. The *Exact search* and *Extended search* columns above list which managers rely on this.

It goes one step further for a manager that ships no search command at all. `opkg` is the modest example: a bare project used by a confidential audience, with only the basic primitives (`update`, `list`, ...). `mpm` gives it a `search` anyway, simulated by listing every available package and filtering the result:

```shell-session
$ mpm --opkg search nano
(...)
```

## Universal augmentations

The table above is *selective*: each ✅ backfills a capability only some managers lack. A second class of augmentation applies to **every** manager `mpm` drives, whether or not its native CLI cooperates.

### Safe `--dry-run` everywhere

`mpm` intercepts each state-changing call and logs it instead of running it, so any manager becomes previewable even when its own CLI has no dry-run mode:

```shell-session
$ mpm --dry-run --apt upgrade --all
warning: Dry-run: (...)
```

### Comparable versions across schemes

Package managers report versions in mutually incompatible schemes: semver, PEP 440, calendar versioning, Debian epochs, Gentoo suffixes, and more. Rather than a parser per format, `mpm` runs every version through a single tokenizer that yields a good-enough ordering, so `outdated` shows a meaningful installed-to-latest comparison even for managers whose native output never could.

### Standard package URLs (purl)

Every package `mpm` reports carries a [purl](https://github.com/package-url/purl-spec) identifier that the native tools do not emit. It is the same identifier that powers `mpm sbom`, giving every manager a portable, tool-agnostic package name.

### One sudo prompt, uniform policy

Managers disagree on whether an operation needs root. `mpm` applies a consistent policy: system managers (`apt`, `dnf`, `pacman`, …) escalate, user-level managers do not. On an interactive terminal it authenticates once up front instead of letting each manager prompt mid-run; off a terminal, managers that need root fail fast rather than hanging on a hidden prompt.
