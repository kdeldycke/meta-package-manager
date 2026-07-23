# {octicon}`plus-circle` Manager augmentations

Package managers are not comparable: some ship advanced features others lack. Rather than expose that unevenness, `mpm` backfills the missing pieces on top of the native tools, so every manager gains a consistent baseline.

## Managers gaining features

Each ✅ below is a capability `mpm` synthesizes for a manager that does not provide it natively. The table renders straight from the capability declarations in the manager implementations, so it never drifts from the code. The rest of this page explains each column.

```{python:render}
:mirror:
from docs_update import augmentations_table

print(augmentations_table())
```

<!-- mirror -->

| Manager                                    | Full `upgrade --all` | Orphan sweep | Exact search | Extended search |
| :----------------------------------------- | :------------------: | :----------: | :----------: | :-------------: |
| [`apk`](managers/apk.md)                   |                      |              |      ✅      |                 |
| [`apm`](managers/apm.md)                   |                      |              |      ✅      |                 |
| [`apt-cyg`](managers/apt-cyg.md)           |                      |              |      ✅      |       ✅        |
| [`apt-mint`](managers/apt-mint.md)         |                      |              |              |       ✅        |
| [`asdf`](managers/asdf.md)                 |          ✅          |              |      ✅      |       ✅        |
| [`cargo`](managers/cargo.md)               |                      |              |      ✅      |       ✅        |
| [`chromebrew`](managers/chromebrew.md)     |                      |              |      ✅      |       ✅        |
| [`composer`](managers/composer.md)         |                      |              |      ✅      |                 |
| [`conda`](managers/conda.md)               |                      |              |      ✅      |       ✅        |
| [`deb-get`](managers/deb-get.md)           |                      |              |      ✅      |       ✅        |
| [`dnf`](managers/dnf.md)                   |                      |              |      ✅      |       ✅        |
| [`dnf5`](managers/dnf5.md)                 |                      |              |      ✅      |       ✅        |
| [`eopkg`](managers/eopkg.md)               |                      |              |      ✅      |                 |
| [`fink`](managers/fink.md)                 |                      |              |      ✅      |       ✅        |
| [`flatpak`](managers/flatpak.md)           |                      |              |      ✅      |       ✅        |
| [`gem`](managers/gem.md)                   |                      |              |              |       ✅        |
| [`gh-ext`](managers/gh-ext.md)             |                      |              |      ✅      |       ✅        |
| [`guix`](managers/guix.md)                 |                      |              |      ✅      |       ✅        |
| [`mas`](managers/mas.md)                   |                      |              |      ✅      |       ✅        |
| [`mise`](managers/mise.md)                 |                      |              |      ✅      |                 |
| [`nix`](managers/nix.md)                   |                      |              |      ✅      |       ✅        |
| [`npm`](managers/npm.md)                   |                      |              |      ✅      |                 |
| [`opkg`](managers/opkg.md)                 |                      |              |      ✅      |       ✅        |
| [`pacaur`](managers/pacaur.md)             |                      |      ✅      |              |       ✅        |
| [`pacman`](managers/pacman.md)             |                      |      ✅      |              |       ✅        |
| [`pacstall`](managers/pacstall.md)         |                      |              |      ✅      |       ✅        |
| [`paru`](managers/paru.md)                 |                      |      ✅      |              |       ✅        |
| [`pip`](managers/pip.md)                   |          ✅          |              |              |                 |
| [`pkcon`](managers/pkcon.md)               |                      |              |      ✅      |       ✅        |
| [`pkg-tools`](managers/pkg-tools.md)       |                      |              |      ✅      |       ✅        |
| [`pkgin`](managers/pkgin.md)               |                      |              |      ✅      |       ✅        |
| [`pnpm`](managers/pnpm.md)                 |                      |              |      ✅      |                 |
| [`pwsh-gallery`](managers/pwsh-gallery.md) |                      |              |              |       ✅        |
| [`scoop`](managers/scoop.md)               |                      |              |      ✅      |       ✅        |
| [`sfsu`](managers/sfsu.md)                 |                      |              |      ✅      |       ✅        |
| [`slapt-get`](managers/slapt-get.md)       |                      |              |      ✅      |       ✅        |
| [`snap`](managers/snap.md)                 |                      |              |      ✅      |       ✅        |
| [`soar`](managers/soar.md)                 |                      |              |      ✅      |       ✅        |
| [`sorcery`](managers/sorcery.md)           |                      |              |      ✅      |       ✅        |
| [`swupd`](managers/swupd.md)               |                      |              |      ✅      |       ✅        |
| [`tazpkg`](managers/tazpkg.md)             |                      |              |      ✅      |       ✅        |
| [`tlmgr`](managers/tlmgr.md)               |                      |              |      ✅      |       ✅        |
| [`urpmi`](managers/urpmi.md)               |                      |              |      ✅      |       ✅        |
| [`uv`](managers/uv.md)                     |          ✅          |              |              |                 |
| [`xbps`](managers/xbps.md)                 |                      |              |      ✅      |       ✅        |
| [`yarn`](managers/yarn.md)                 |                      |              |      ✅      |       ✅        |
| [`yarn-berry`](managers/yarn-berry.md)     |                      |              |      ✅      |       ✅        |
| [`yay`](managers/yay.md)                   |                      |      ✅      |              |       ✅        |
| [`yum`](managers/yum.md)                   |                      |              |      ✅      |       ✅        |
| [`zypper`](managers/zypper.md)             |                      |      ✅      |              |                 |

<!-- mirror-end -->

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

The *Full `upgrade --all`* column above lists the managers relying on this backfill.

## Free orphan sweep

Some managers can list their orphaned dependencies but have no verb to remove them all in one go. `pacman` is the canonical case: Arch users chain the two native primitives by hand, with the classic `pacman -Rns $(pacman -Qtdq)` idiom. When a manager implements the `orphans` listing and per-package removal but no native sweep, `mpm cleanup --orphans` synthesizes the sweep in-process: list the orphans, remove each one (recursively where the manager supports it, so every listed root takes its own now-orphaned subtree along), then re-query and repeat until the listing settles, since removing an orphan can orphan its own dependencies.

```shell-session
$ mpm --pacman cleanup --orphans
```

The *Orphan sweep* column above lists the managers relying on this backfill.

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

### Inspect the plan before running

`mpm --plan <operation>` prints the exact package-manager commands a state-changing operation would run, without running them. Unlike `--dry-run`, which simulates *every* call and so leaves `install`, `remove` and `upgrade --all` unable to resolve what they would do, plan mode still runs the read-only lookups those operations need, then captures only the mutations, one copy-pasteable line per command on stdout:

```shell-session
$ mpm --plan --brew upgrade --all
HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_ENV_HINTS=1 HOMEBREW_NO_AUTO_UPDATE=1 /opt/homebrew/bin/brew upgrade --quiet --yes --formula
```

Each line carries the resolved binary path and the forced environment, so the plan doubles as an audit trail and pipes straight into a shell.

### Comparable versions across schemes

Package managers report versions in mutually incompatible schemes: semver, PEP 440, calendar versioning, Debian epochs, Gentoo suffixes, and more. Rather than a parser per format, `mpm` runs every version through a single tokenizer that yields a good-enough ordering, so `outdated` shows a meaningful installed-to-latest comparison even for managers whose native output never could.

### Standard package URLs (purl)

Every package `mpm` reports carries a [purl](https://github.com/package-url/purl-spec) identifier that the native tools do not emit. It is the same identifier that powers `mpm sbom`, giving every manager a portable, tool-agnostic package name.

### One sudo prompt, uniform policy

Managers disagree on whether an operation needs root. `mpm` applies a consistent policy: system managers (`apt`, `dnf`, `pacman`, …) escalate, user-level managers do not. Before a state-changing command it probes the `sudo` credential cache and silently keeps a warm one alive; only a cold cache on an interactive terminal draws a single up-front password prompt, naming the escalating managers and branded `[mpm]`, instead of letting each manager prompt mid-run. Off a terminal, managers that need root fail fast rather than hanging on a hidden prompt.

Managers that run `sudo` from inside their own commands (`cask`, `fink`) reuse the warm cache too; on a cold one, a mutating call that goes silent on a terminal draws a warning pointing at the possibly hidden password prompt. See [privilege escalation](sudo.md) for the full story.
