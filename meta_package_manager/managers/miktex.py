# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from __future__ import annotations

import re

from extra_platforms import LINUX_LIKE, WINDOWS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_LIST_TEMPLATE = "{isInstalled} {id} {version}"
"""Row format asked of MiKTeX's own listing.

MiKTeX has no listing restricted to installed packages: `list` walks its whole
catalog, several thousand entries. Prepending the installed flag is what lets
that dump be filtered back down to an inventory, and the version is asked for
in the same breath.

```{note}
This template is also why MiKTeX needs a class rather than a declarative
definition. A definition's arguments are scanned for mpm's own
``{placeholder}`` tokens and refuse any it does not recognize, and MiKTeX's
field names are lowercase, so `{id}` and `{version}` are read as mpm
placeholders and rejected. The uppercase query formats of other managers, like
rpm's ``%{NAME}``, slip past that check; these cannot.
```
"""


class MiKTeX(PackageManager):
    """TeX package manager of the MiKTeX distribution.

    Reaches MiKTeX's own package repositories, which are distinct from the
    catalog [`tlmgr`](tlmgr.md) reaches for TeX Live: two distributions, two
    managers, rather than one wrapped twice.

    ```{note}
    Linux and Windows only, and that follows the tool rather than a choice. The
    `packages` command arrived in MiKTeX `22.3`, while the newest macOS build
    MiKTeX publishes is `22.1`, which predates it. The only package surface on
    macOS is the standalone binary that happens to share this project's name,
    which is reason enough never to reach for it.
    ```

    ```{caution}
    `--admin` is deliberately never passed, and the reasoning inverts what its
    name suggests. Left alone, MiKTeX reports the packages installed for the
    user *and* those installed system-wide; the flag narrows that to the
    system-wide ones alone. The default is therefore already the wider listing,
    and passing it would drop rows rather than pin them. It is fatal outright
    on an installation that is not shared, and warns about privileges it may
    lack when run without them. The cost is that removing a system-wide package
    is out of reach, needing both that flag and administrator rights.
    ```

    ```{important}
    Queries pass `--disable-installer`. MiKTeX installs packages on the fly by
    default, so without it reading the inventory is not guaranteed to leave the
    system as it found it.
    ```

    ```{note}
    No `outdated`, though MiKTeX does have a non-mutating check: it prints bare
    package names and no version of any kind, where reporting something as
    outdated needs a version to report it against. The only route to one is
    asking after each package individually, thousands of invocations for a
    single answer. `upgrade --all` is unaffected.

    No `search`, MiKTeX having no such command, and no `cleanup`: nothing in
    the package surface purges a cache or sweeps orphans.
    ```

    ```{warning}
    The command that upgrades everything is `update`. MiKTeX's `upgrade` is a
    different thing entirely, taking a package *level* such as `basic` or
    `complete` and erroring without one, so it is never used here.
    ```

    Documentation: [MiKTeX packages](https://docs.miktex.org/manual/miktex-packages.html).
    """

    name = "MiKTeX"

    homepage_url = "https://miktex.org"
    logo = "latex"

    platforms = LINUX_LIKE, WINDOWS

    requirement = ">=22.3"
    """The release that introduced the `packages` command this drives."""

    version_regexes = (r"\(MiKTeX (?P<version>\d+(?:\.\d+)*)",)
    r"""Search the release named in parentheses.

    ```{code-block} console

    $ miktex --version
    One MiKTeX Utility 1.12.0 (MiKTeX 26.5)
    ```

    Two numbers share that line: the utility's own version first, then the
    MiKTeX release, which is the one that means anything here. The parenthesis
    is what tells them apart. A word such as the build's word size may follow
    the release, which the pattern stops before.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?:true|1) (?P<package_id>\S+) ?(?P<installed_version>.*)$",
    )
    """One installed package of the catalog listing.

    Rows for packages that are not installed carry the opposite flag and are
    skipped. The flag is matched permissively because MiKTeX renders it through
    a formatting library whose boolean output could not be observed, only
    derived. The version is free-form and often empty, in which case the
    package is reported without one rather than with a placeholder.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} console

        $ miktex --disable-installer packages list --template "{isInstalled} {id} {version}"
        true amsmath 2.17n
        false zwpagelayout
        true fancyhdr 4.0.3
        ```
        """
        output = self.run_cli(
            "--disable-installer",
            "packages",
            "list",
            "--template",
            _LIST_TEMPLATE,
        )
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ miktex packages install fancyhdr
        ```

        ```{caution}
        MiKTeX fails outright when the package is already installed, rather
        than treating it as a no-op.
        ```
        """
        return self.run_cli("packages", "install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ miktex packages update
        ```
        """
        return self.build_cli("packages", "update")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Naming packages genuinely restricts the run to them, the rest being
        reported as already up to date.

        ```{code-block} shell-session

        $ miktex packages update fancyhdr
        ```
        """
        return self.build_cli("packages", "update", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{code-block} shell-session

        $ miktex packages remove fancyhdr
        ```

        ```{caution}
        MiKTeX fails outright when the package is not installed.
        ```
        """
        return self.run_cli("packages", "remove", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ miktex packages update-package-database
        ```
        """
        self.run_cli("packages", "update-package-database")
