# Use-cases

A collection of user’s problems and how `mpm` solves them.

## Keep system up-to-date

A recent
[study shows that 70% of vulnerabilities lies in outdated libraries](https://developers.slashdot.org/story/20/05/23/2330244/open-source-security-report-finds-library-induced-flaws-in-70-of-applications).
One of the key habits of security professionals is to keep a system secure
by keeping all software up to date.

`mpm` upgrade all packages from all managers with a one-liner CLI:

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

This is the primary use case of `mpm` and the main reason I built it.

## Solve XKCD

I then wasted 6 years to implement [XKCD #1654 - *Universal Install Script*](https://xkcd.com/1654/):

![XKCD #1654 - Universal Install Script](http://imgs.xkcd.com/comics/universal_install_script.png)

So that you can:

```shell-session
$ mpm --xkcd install markdown
Installation priority: pip > brew > npm > dnf > apt > steamcmd
warning: pip does not implement search operation.
markdown existence unconfirmed, try to directly install it...
Install markdown package with pip...
(...)
```

## Extra features for your package managers

Package managers are not comparable. Some have advanced features other lacks. `mpm` is filling the
gap between managers and implement some of these missing features.

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

You just learned about a new cool app you did not known about (`broot` in this example).
You want to try it but don't known where to get it. Back to your terminal, you can search for it
across all package repositories:

```shell-session
$ mpm search broot --exact
╭────────────┬──────┬─────────┬────────────────╮
│ Package ID │ Name │ Manager │ Latest version │
├────────────┼──────┼─────────┼────────────────┤
│ broot      │      │ brew    │ 1.16.2         │
│ broot      │      │ cargo   │ 0.13.6         │
╰────────────┴──────┴─────────┴────────────────╯
2 packages total (brew: 1, pip: 1, cask: 0, gem: 0, mas: 0, npm: 0).
```

Then choose your preferred package manager to install it:

```shell-session
$ mpm --brew install broot
Package manager order: brew
Install broot package from brew...
(...)
🍺  /usr/local/Cellar/broot/1.16.2: 8 files, 3.5MB
```

Thanks to `mpm` we were able to identify the best source for
`broot` to get the latest version.

## Deduplicate packages

`mpm` can list all the installed packages on your machine sharing the same ID:

```shell-session
$ mpm list --duplicates
╭────────────┬──────┬─────────┬───────────────────╮
│ Package ID │ Name │ Manager │ Installed version │
├────────────┼──────┼─────────┼───────────────────┤
│ blah       │      │ cargo   │ 0.0.0             │
│ blah       │      │ gem     │ 0.0.2             │
│ blah       │      │ npm     │ 5.2.1             │
│ coverage   │      │ pip     │ 6.4.1             │
│ coverage   │      │ pipx    │ 6.4.1             │
│ six        │      │ brew    │ 1.16.0_2          │
│ six        │      │ pip     │ 1.16.0            │
╰────────────┴──────┴─────────┴───────────────────╯
7 packages total (pip: 2, brew: 1, cargo: 1, gem: 1, npm: 1, pipx: 1, cask: 0).
```

Now you can easily remove all of them:

```shell-session
$ mpm remove blah
Remove blah with cargo, gem, npm
(...)
Successfully uninstalled blah-0.0.0
(...)
Successfully uninstalled blah-0.0.2
(...)
Successfully uninstalled blah-5.2.1
```

Or a target specific duplicates:

```shell-session
$ mpm --pip uninstall six
(...)
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

## Speculative use-cases

A list of ideas and concepts `mpm` could support in the future

### SBOM: Software Bill of Materials

```{admonition} Context
The [Log4Shell vulnerability](https://en.wikipedia.org/wiki/Log4Shell) debacle was a wake-up call for the industry. This dependency was deeply embedded in the legacy stack of companies and administrations. They all had huge difficulty to identify its presence, writing custom detection scripts and scanning their software artifacts.

As a response to this crisis, [SBOM tools have now became a category of their own](https://en.wikipedia.org/wiki/Software_supply_chain). To the point that [a US executive order has also been released](https://www.whitehouse.gov/briefing-room/presidential-actions/2021/05/12/executive-order-on-improving-the-nations-cybersecurity/) to modernize cybersecurity practices and enforce the production of SBOM to track the software supply chain.
```

```{todo}
`mpm` doesn't implement SBOM features yet. This work is tracked by {issue}`936`.
```

````{tip}
In the mean time, you can export the list of installed packages in JSON:

```shell-session
$ mpm --output-format json installed > installed_package.json
```
```json
{
    "pip": {
        "errors": [],
        "id": "pip",
        "name": "Pip",
        "packages": [
            {
                "id": "arrow",
                "installed_version": "1.2.3",
                "name": null
            },
            {
                "id": "boltons",
                "installed_version": "21.0.0",
                "name": null
            }
        ]
    },
    "vscode": {
        "errors": [],
        "id": "vscode",
        "name": "Visual Studio Code",
        "packages": [
            {
                "id": "charliermarsh.ruff",
                "installed_version": "2023.6.0",
                "name": null
            },
            {
                "id": "ExecutableBookProject.myst-highlight",
                "installed_version": "0.11.0",
                "name": null
            },
            {
                "id": "GitHub.copilot",
                "installed_version": "1.73.8685",
                "name": null
            }
        ]
    },
}
```

Or in CSV:
```shell-session
$ mpm --output-format csv installed > installed_package.csv
```
```csv
Package ID,Name,Manager,Installed version
arrow,,pip,1.2.3
boltons,,pip,21.0.0
charliermarsh.ruff,,vscode,2023.6.0
ExecutableBookProject.myst-highlight,,vscode,0.11.0
GitHub.copilot,,vscode,1.73.8685
```

There's probably a tool somewhere that will allow you to transform these machine-readable exports to a proper SBOM file format.
````

### List vulnerabilities

```{todo}
`mpm` doesn't identify CVEs yet.

This feature might be solved with SBOM implementation, as I think there is some tools available around that can check an SBOM export and cross reference it with a CVE database.
```

### List dependencies

```{todo}
`mpm` doesn't collect dependencies yet. Once it does these dependencies can augment the SBOM export.
```

### Get rid of Docker for lambda?

Some developers have a hard-time reproducing environment for lambda execution
onto their local machine. Most of devs use Docker to abstract their runtime
requirements. But Docker might be too big for some people.

`mpm` can be a lightweight alternative to Docker, to abstract the runtime
from their execution environment.

### Support and fund open-source?

One future development direction might be to add a way to inventory all
components your using on your system and track down their preferred funding
platform like [GitHub Sponsors](https://github.com/sponsors),
[Liberapay](https://liberapay.com) or [Patreon](https://patreon.com). Then have
a way to fund all those.

Homebrew is already featuring
[some commands in that direction](https://github.com/Homebrew/brew/pull/7900).