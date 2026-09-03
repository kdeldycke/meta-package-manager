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

from extra_platforms import ILLUMOS, SOLARIS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class IPS(PackageManager):
    """The Image Packaging System, the native `pkg` of Solaris and illumos.

    Documentation: [`pkg(1)` man page](https://docs.oracle.com/cd/E88353_01/html/E37839/pkg-1.html).

    The CLI is named `pkg`, which the FreeBSD {class}`PKG` manager also claims.
    The two never coexist, their `platforms` being disjoint, but the manager ID
    here is `ips` so the two stay addressable apart.

    ```{note}
    Only root may modify the image, so mutating operations escalate through
    `sudo`. `sync` escalates too: refreshing the catalog writes into the
    image's own metadata rather than a user cache.
    ```

    ```{caution}
    `installed` passes `--no-refresh` to keep the inventory a local read. Left
    off, `pkg list` contacts every configured publisher first, which turns a
    listing into a network round-trip and fails outright when the host is
    offline.
    ```

    ```{todo}
    `outdated` is not implemented. The operation needs a sample naming both the
    installed and the available version, and the only illumos host available
    reported `no packages have newer versions available`.

    That state cannot be manufactured on a consistent image, so do not spend
    time trying: installing a superseded build to force one is refused with
    ``did not match any allowable packages``, the release incorporations
    constraining an image to one allowable version per package. Inventing a
    fixture is not an option either, a sample having to parse through this
    manager's own parser and having to be real.

    Capture it on a host whose image has fallen behind its publisher, which is
    the only state that emits the output.
    ```
    """

    name = "Image Packaging System"

    homepage_url = "https://github.com/OpenIndiana/pkg5"

    # No `logo`, and there never will be: Oracle's marks were pulled from Simple
    # Icons, so do not file a request, and do not vendor one by hand:
    # https://github.com/simple-icons/simple-icons/issues/11441

    keywords = ("pkg5",)
    """The name the upstream project answers to, which the `ips` ID does not carry."""

    platforms = ILLUMOS, SOLARIS

    default_sudo = True

    cli_names = ("pkg",)

    version_cli_options = ("list", "-H", "--no-refresh", "package/pkg")
    """IPS reports no version of its own: `pkg --version` is answered with
    ``pkg: illegal global option -- version`` and exit `2`, while bare
    `pkg version` prints the build hash alone (`4e1d42c7`), which carries no
    ordering. IPS does package itself as `package/pkg` on every distribution,
    so its own inventory row is the version, and `--no-refresh` keeps the probe
    from reaching the network.
    """

    version_regexes = (r"package/pkg\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ pkg list -H --no-refresh package/pkg
    package/pkg                                       0.5.11-2025.0.0.5626       i--
    ```
    """

    _LIST_REGEXP = re.compile(
        r"^(?P<package_id>\S+)(?:\s+\([^)]+\))?\s+(?P<version>\S+)\s+[a-z-]{3}$",
        re.MULTILINE,
    )
    """Matches one `pkg list` row, anchored on the three-character `IFO` column.

    The anchor is what keeps prose out of the results: `pkg list -u` answers
    `no packages have newer versions available` on a zero exit, and a looser
    pattern would yield that sentence as a package.

    The optional parenthesized group absorbs the publisher, which the `NAME`
    column carries as `name (publisher)` whenever a package comes from other
    than the preferred publisher.
    """

    _SEARCH_REGEXP = re.compile(
        r"^pkg:/(?P<package_id>[^@\s]+)@(?P<version>\S+)\s+\S+$",
        re.MULTILINE,
    )
    """Matches one `pkg search -p` row: an FMRI and its publisher, tab-separated.

    Keyed on `\\s+` rather than a literal tab, so the pattern survives a
    docstring reindented by the formatter.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ pkg list -H --no-refresh
        SUNWcs                                            0.5.11-2026.0.0.23029      i--
        SUNWcsd                                           0.5.11-2026.0.0.23029      i--
        archiver/gnu-tar                                  1.35-2023.0.0.0            i--
        audio/audio-utilities                             0.5.11-2026.0.0.23029      i--
        audio/lame                                        3.100-2025.0.0.3           i--
        ```
        """
        output = self.run_cli("list", "-H", "--no-refresh")

        for match in self._LIST_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("version"),
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search packages.

        `-p` reports one row per matching package instead of one per matching
        action, which is what the bare form emits: a package whose summary and
        description both match is otherwise returned twice.

        IPS indexes the summary and description alongside the name, so a query
        always searches them. That is wider than `mpm`'s default, and neither
        capability is declared: `mpm` refilters the results itself, narrowing
        the plain case and leaving the extended one alone.

        ```{code-block} shell-session

        $ pkg search -H -p tar
        pkg:/SUNWcs@0.5.11-2026.0.0.23029	openindiana.org
        pkg:/archiver/gnu-tar@1.35-2023.0.0.0	openindiana.org
        pkg:/archiver/ofarc@1.5.1-2026.0.0.0	openindiana.org
        pkg:/developer/quilt@0.69-2026.0.0.2	openindiana.org
        pkg:/library/perl-5/archive-tar@3.4-2025.0.0.1	openindiana.org
        ```
        """
        output = self.run_cli("search", "-H", "-p", query)

        for match in self._SEARCH_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                latest_version=match.group("version"),
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `--accept` accepts the package licenses, which IPS would otherwise stop
        and prompt for, hanging the subprocess.

        ```{code-block} shell-session

        $ sudo pkg install --accept archiver/gnu-tar
        ```
        """
        return self.run_cli("install", "--accept", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Upgrade all packages.

        ```{code-block} shell-session

        $ sudo pkg update --accept
        ```
        """
        return self.build_cli("update", "--accept", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Upgrade one package.

        ```{code-block} shell-session

        $ sudo pkg update --accept archiver/gnu-tar
        ```
        """
        return self.build_cli("update", "--accept", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo pkg uninstall archiver/gnu-tar
        ```
        """
        return self.run_cli("uninstall", package_id, sudo=True)

    def sync(self) -> None:
        """Refresh the publishers' catalogs.

        ```{code-block} shell-session

        $ sudo pkg refresh
        ```
        """
        self.run_cli("refresh", sudo=True)

    def cleanup(self) -> None:
        """Purge the image's operation history.

        IPS caches nothing a user can reclaim: downloaded content lands straight
        in the image, so `purge-history` is the only space this manager frees.

        ```{code-block} shell-session

        $ sudo pkg purge-history
        ```
        """
        self.run_cli("purge-history", sudo=True)
