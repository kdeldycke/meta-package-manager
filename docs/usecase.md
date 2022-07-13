# Use-cases

A collection of user’s problems and how `mpm` solves them.

## Keep system secure

A recent
[study shows that 70% of vulnerabilities lies in outdated libraries](https://developers.slashdot.org/story/20/05/23/2330244/open-source-security-report-finds-library-induced-flaws-in-70-of-applications).
One of the key habits of security professionnals to keep a system secure
consist in having all software up to date.

`mpm` helps you upgrade all packages from all managers of a system with
one-liner:

```shell-session
$ mpm upgrade --all
Updating all outdated packages from brew...
==> Upgrading 4 outdated packages:
gnu-getopt 2.35.1 -> 2.35.2
rclone 1.51.0 -> 1.52.0
fd 8.1.0 -> 8.1.1
youtube-dl 2020.05.08 -> 2020.05.29
(...)
Updating all outdated packages from cask...
==> Upgrading 4 outdated packages:
balenaetcher 1.5.89 -> 1.5.94, libreoffice 6.4.3 -> 6.4.4
(...)
Updating all outdated packages from gem...
Updating openssl
(...)
Updating all outdated packages from npm...
+ npm@6.14.5
(...)
Updating all outdated packages from pip...
Successfully installed dephell-argparse-0.1.3
Successfully installed dephell-pythons-0.1.15
```

This is the primary use case of `mpm` and the first reason I built it.

## Extra features for your package managers

All package managers are not on-par between themselves. `mpm` is filling the
gap between managers and implement some missing features.

For instance,
[`pip` can’t upgrade all outdated package](https://github.com/pypa/pip/issues/4551)
with a single command. `mpm` adds that missing feature:

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

Collecting tomlkit
  Using cached tomlkit-0.6.0-py2.py3-none-any.whl (31 kB)
Installing collected packages: tomlkit
Successfully installed tomlkit-0.6.0

Collecting urllib3
  Using cached urllib3-1.25.9-py2.py3-none-any.whl (126 kB)
Installing collected packages: urllib3
Successfully installed urllib3-1.25.9

Collecting zipp
  Using cached zipp-3.1.0-py3-none-any.whl (4.9 kB)
Installing collected packages: zipp
Successfully installed zipp-3.1.0
```

Another example is the modest `opkg` package manager, only used by a
confidential audience. It is a bare project with only the basic primitives
implemented (`update`, `list`, …). Thanks to `mpm` it gains a free `search`
feature.

## Same package, multiple sources

You just learned of a new CLI you did not known about (`broot`) from a friend.
Back to your terminal, you can easily search for it across all package
repositories, then choose your preferred package manager to install it:

```shell-session
$ mpm search broot --exact
╭────────────┬─────────┬────────────────╮
│ Package ID │ Manager │ Latest version │
├────────────┼─────────┼────────────────┤
│ broot      │ brew    │ 0.1.0          │
│ broot      │ cargo   │ 1.14.1         │
╰────────────┴─────────┴────────────────╯
2 packages total (brew: 1, pip: 1, cask: 0, gem: 0, mas: 0, npm: 0).
```

```shell-session
$ mpm --brew install broot
Package manager order: brew
Install broot package from brew...
(...)
🍺  /usr/local/Cellar/broot/0.13.6: 8 files, 3.5MB
```

Thanks to `mpm` we were able to choose quickly the origin from which we sourced
`broot` to get the latest version. No need to track down the CLI on Github and
read the documentation (if it even exists).

## Deduplicate packages

```shell-session
$ mpm list --duplicates
╭──────────────────────┬─────────┬───────────────────╮
│ Package ID           │ Manager │ Installed version │
├──────────────────────┼─────────┼───────────────────┤
│ blah                 │ cargo   │ 0.0.0             │
│ blah                 │ gem     │ 0.0.2             │
│ blah                 │ npm     │ 5.2.1             │
│ coverage             │ pip     │ 6.4.1             │
│ coverage             │ pipx    │ 6.4.1             │
│ six                  │ brew    │ 1.16.0_2          │
│ six                  │ pip     │ 1.16.0            │
╰──────────────────────┴─────────┴───────────────────╯
6 packages total (pip: 2, brew: 1, cargo: 1, gem: 1, npm: 1, cask: 0).
```

Now you can easily remove some of them, and no longer have to think hard about
which is which.

```shell-session
$ mpm --cargo uninstall blah
$ mpm --gem   uninstall blah
$ mpm --pip   uninstall blah

$ mpm --pip uninstall six
```

```{todo}
Add arguments to `installed` command, or an `--installed` boolean flag to `search` so we can reduce the searched packages to those installed.
```

## Dump installed packages

You maintain a repository of `dotfiles`. This helps you spawn up a highly
customized working environment in a couple of hours. New job? New machine?
Easy: run your dotfiles, get a coffe, come back with everything perfectly in
place to start an extremely productive hacking session. But maintaining
`dotfiles` is a pain.

`mpm` allows you to dump the whole list of packages installed on your machine:

```shell-session
$ mpm snapshot packages.toml
Dump all installed packages into packages.toml
Dumping packages from brew...
Dumping packages from cask...
Dumping packages from gem...
Dumping packages from mas...
Dumping packages from npm...
Dumping packages from pip...
1109 packages total (npm: 659, brew: 229, pip: 115, gem: 49, cask: 48, mas: 9).
```

```shell-session
$ cat packages.toml
# Generated by mpm 4.7.0.
# Timestamp: 2020-05-29T11:15:29.539863.

[brew]
ack = "3.3.1"
adns = "1.5.1"
aom = "1.0.0"
apr = "1.7.0"
apr-util = "1.6.1_3"
arss = "0.2.3"
(...)
```

## Maintain list of installed packages

To keep the list produced above up to date, you can resort to the `--update-version` option:

```shell-session
$ mpm snapshot --update-version packages.toml
(...)
```

And if your want to add the new packages you installed since your last snapshot, there is the `--merge` option for that:

```shell-session
$ mpm snapshot --merge packages.toml
(...)
```

Of course you can still call the backup

## Get rid of Docker for lambda?

Some developers have a hard-time reproducing environment for lambda execution
onto their local machine. Most of devs use Docker to abstract their runtime
requirements. But Docker might be too big for some people.

`mpm` can be a lightweight alternative to Docker here to abstract the runtime
from their execution environment.

## Switch systems

You used to work on macOS. Now you’d like to move to Linux. To reduce friction
during your migration, you can make an inventory of all your installed packages with `mpm`,
then reinstall them on your new distribution.

1. Backup a list of all installed packages on macOS:

   ```shell-session
   $ mpm backup packages.toml
   ```

1. On your brand new Linux distribution, restore all packages with:

   ```shell-session
   $ mpm restore packages.toml
   ```

```{todo}
Implement a best matchig strategy, across package managers of different kinds.
```

## Support and fund open-source?

One future development direction might be to add a way to inventory all
components your using on your system and track down their preferred funding
platform like [GitHub Sponsors](https://github.com/sponsors),
[Liberapay](https://liberapay.com) or [Patreon](https://patreon.com). Then have
a way to fund all those.

Homebrew is already featuring
[some commands in that direction](https://github.com/Homebrew/brew/pull/7900).
