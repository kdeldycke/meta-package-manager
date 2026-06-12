# {octicon}`light-bulb` Use-cases

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

## Cross-manager duplicates

`mpm search` finds the best source for a new install, and `mpm list --duplicates` audits the same package installed through more than one manager. See {doc}`duplicates` for the full reference.

## Pipe-friendly output formats

`mpm --table-format json` and `--table-format csv` make the `installed`, `outdated`, and `search` results consumable by downstream tools. See {doc}`output-formats` for examples.

## Snapshot and export

`mpm` can capture the installed-package inventory in two complementary formats:

- a TOML manifest or a Brewfile through {doc}`mpm dump <dump>` for re-installation workflows;
- a Software Bill of Materials (SBOM) in SPDX or CycloneDX format through {doc}`mpm sbom <sbom>` for supply-chain inventory work.

## Speculative use-cases

A list of ideas and concepts `mpm` could support in the future

### List vulnerabilities

```{todo}
`mpm` doesn't identify CVEs yet.

This feature might be solved with SBOM implementation, as I think there is some tools available around that can check an SBOM export and cross reference it with a CVE database.

Take a look at: https://security.googleblog.com/2023/04/announcing-depsdev-api-critical.html
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

```{todo}
One future development direction might be to add a way to inventory all
components your using on your system and track down their preferred funding
platform like [GitHub Sponsors](https://github.com/sponsors),
[Liberapay](https://liberapay.com) or [Patreon](https://patreon.com). Then have
a way to fund all those.

Homebrew is already featuring
[some commands in that direction](https://github.com/Homebrew/brew/pull/7900).

And also see this article in which [someone algorithmically donated $5000+ to Open Source via GitHub Sponsors and PyPI data](https://kvinogradov.com/algo-sponsors/).

This is being discussed at {issue}`501`.
```
