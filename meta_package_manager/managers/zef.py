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

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ..package import Package


class Zef(PackageManager):
    """Zef, the module manager of the Raku language.

    A package is a Raku distribution, identified by the bare name its identity
    string opens with. Raku names are colon-separated (`JSON::Fast`) and the
    identity appends its own colon-prefixed fields to them
    (`JSON::Fast:ver<0.20>:auth<zef:timo>`), so every pattern here matches the
    name lazily up to the literal `:ver<` rather than splitting on colons.

    ```{note}
    Two distributions may share a name and differ only by the `auth` field, and
    several versions of one may be installed side by side. mpm keys a package on
    its id alone, so both listings are reduced here to one entry per name,
    keeping the highest version. That reduction is what makes this a class
    rather than a bundled definition.
    ```

    ```{note}
    Search compounds the same problem rather than avoiding it: it answers with a
    pipe-delimited table carrying one row per *(distribution, version)* pair, so
    a single module comes back once per release it has ever published.
    ```

    ```{note}
    No `outdated`: zef reports no staleness of its own. `upgrade` covers both the
    bulk and the single-package cases natively, so neither is synthesized.
    ```

    Documentation: [zef README](https://github.com/ugexe/zef#readme).
    """

    name = "Zef"

    homepage_url = "https://github.com/ugexe/zef"

    platforms = ALL_PLATFORMS

    version_regexes = (r"^(?P<version>\d+\.\d+\.\d+)",)
    r"""Search the bare version zef prints on its own.

    ```{code-block} shell-session

    $ zef --version
    1.1.3
    ```
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>.+?):ver<(?P<installed_version>[^>]+)>",
    )
    """One installed distribution, as its identity string. The `===> Found via`
    banner opening the listing carries no `:ver<` and so cannot match.
    """

    _SEARCH_REGEXP = re.compile(
        r"^\d+[ \t]*\|[^|]*\|[ \t]*(?P<package_id>.+?):ver<(?P<latest_version>[^>]+)>"
        r"[^|]*\|[ \t]*(?P<description>.*?)[ \t]*$",
    )
    """One search hit: the leading row number, the repository it came from, the
    identity, then the description. Anchoring on the row number skips the two
    rule lines and the column header, none of which open with a digit.
    """

    def _newest_per_name(
        self,
        rows: Iterable[tuple[str, str, str | None]],
        installed: bool,
    ) -> Iterator[Package]:
        """Reduce rows to one package per name, keeping the highest version."""
        best: dict[str, tuple[str, str | None]] = {}
        for package_id, version, description in rows:
            held = best.get(package_id)
            if held is None or parse_version(version) > parse_version(held[0]):
                best[package_id] = (version, description)
        for package_id, (version, description) in best.items():
            yield self.package(
                id=package_id,
                description=description,
                **{"installed_version" if installed else "latest_version": version},
            )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ zef list --installed
        ===> Found via inst#/opt/homebrew/Cellar/rakudo-star/2026.07/share/perl6/site
        App::Prove6:ver<0.0.18>:auth<zef:leont>
        Config::TOML:ver<0.1.3>:auth<zef:raku-community-modules>
        Config:ver<3.0.4>:auth<cpan:TYIL>:api<3>
        Crane:ver<0.1.2>:auth<zef:raku-community-modules>
        Digest:ver<1.1.0>:auth<zef:grondilu>
        ```
        """
        output = self.run_cli("list", "--installed")
        rows = (
            (match.group("package_id"), match.group("installed_version"), None)
            for match in map(self._INSTALLED_REGEXP.match, output.splitlines())
            if match
        )
        yield from self._newest_per_name(rows, installed=True)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ zef search JSON::Fast
        ===> Found 50 results
        -------------------------------------------------------------------------------
        ID|From                            |Package                              |Description
        -------------------------------------------------------------------------------
        0 |Zef::Repository::Ecosystems<fez>|JSON::Fast:ver<0.20>:auth<zef:timo>  |A naive, fast json parser and serializer
        1 |Zef::Repository::Ecosystems<fez>|JSON::Fast:ver<0.20.1>:auth<zef:timo>|A naive, fast json parser and serializer
        ```
        """
        output = self.run_cli("search", query)
        rows = (
            (
                match.group("package_id"),
                match.group("latest_version"),
                match.group("description") or None,
            )
            for match in map(self._SEARCH_REGEXP.match, output.splitlines())
            if match
        )
        yield from self._newest_per_name(rows, installed=False)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ zef install JSON::Fast::Hyper
        ===> Testing: hyperize:ver<0.0.4>:auth<zef:lizmat>
        ===> Testing [OK] for hyperize:ver<0.0.4>:auth<zef:lizmat>
        ===> Testing: JSON::Fast::Hyper:ver<0.0.11>:auth<zef:lizmat>
        ===> Testing [OK] for JSON::Fast::Hyper:ver<0.0.11>:auth<zef:lizmat>
        ===> Installing: hyperize:ver<0.0.4>:auth<zef:lizmat>
        ===> Installing: JSON::Fast::Hyper:ver<0.0.11>:auth<zef:lizmat>
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generate the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ zef upgrade
        ```
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generate the CLI to upgrade one package.

        ```{code-block} shell-session

        $ zef upgrade JSON::Fast
        ```
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ zef uninstall JSON::Fast::Hyper
        ===> Uninstalled from inst#/opt/homebrew/Cellar/rakudo-star/2026.07/share/perl6/site
        JSON::Fast::Hyper:ver<0.0.11>:auth<zef:lizmat>
        ```
        """
        return self.run_cli("uninstall", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ zef update
        ```
        """
        self.run_cli("update")
