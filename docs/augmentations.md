# {octicon}`plus-circle` Manager augmentations

Package managers are not comparable: some ship advanced features others lack. Rather than expose that unevenness, `mpm` backfills the missing pieces on top of the native tools, so every manager gains a consistent baseline.

## Managers gaining features

Each ✅ below is a capability `mpm` synthesizes for a manager that does not provide it natively. The rest of this page explains each column.

| Manager | Full `upgrade --all` | Exact search | Extended search |
| :--- | :---: | :---: | :---: |
| `apk` |  | ✅ |  |
| `apm` |  | ✅ |  |
| `apt-mint` |  |  | ✅ |
| `asdf` | ✅ | ✅ | ✅ |
| `cargo` |  | ✅ | ✅ |
| `composer` |  | ✅ |  |
| `conda` |  | ✅ | ✅ |
| `deb-get` |  | ✅ | ✅ |
| `dnf` |  | ✅ | ✅ |
| `dnf5` |  | ✅ | ✅ |
| `eopkg` |  | ✅ |  |
| `flatpak` |  | ✅ | ✅ |
| `gem` |  |  | ✅ |
| `guix` |  | ✅ | ✅ |
| `mas` |  | ✅ | ✅ |
| `mise` |  | ✅ |  |
| `nix` |  | ✅ | ✅ |
| `npm` |  | ✅ |  |
| `opkg` |  | ✅ | ✅ |
| `pacaur` |  |  | ✅ |
| `pacman` |  |  | ✅ |
| `pacstall` |  | ✅ | ✅ |
| `paru` |  |  | ✅ |
| `pip` | ✅ |  |  |
| `pnpm` |  | ✅ |  |
| `pwsh-gallery` |  |  | ✅ |
| `scoop` |  | ✅ | ✅ |
| `sfsu` |  | ✅ | ✅ |
| `snap` |  | ✅ | ✅ |
| `steamcmd` | ✅ |  |  |
| `uv` | ✅ |  |  |
| `xbps` |  | ✅ | ✅ |
| `yarn` |  | ✅ | ✅ |
| `yarn-berry` |  | ✅ | ✅ |
| `yay` |  |  | ✅ |
| `yum` |  | ✅ | ✅ |

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
