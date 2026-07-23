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
from typing import ClassVar

from extra_platforms import SLITAZ

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Tazpkg(PackageManager):
    """SliTaz GNU/Linux's package manager.

    Documentation:

    - https://doc.slitaz.org/en:handbook:tazpkg
    - https://github.com/SliTaz-official/tazpkg

    ```{note}
    tazpkg decorates every listing with localized, colorized titles, separators
    and count footers, with no terminal detection: `LC_ALL=C` pins the text to
    English, `--output=raw` switches the decorations to plain text, and any
    remaining ANSI sequence is stripped before parsing. Data rows are then
    matched by their digit-led version column, which no decoration line carries.
    ```

    ```{note}
    No `outdated` operation: `tazpkg up --check` requires root and recharges
    the package lists from the mirror even when only listing, so there is no
    cleanly read-only upgradable listing.
    ```
    """

    name = "TazPkg"

    homepage_url = "https://slitaz.org"

    platforms = SLITAZ

    default_sudo = True

    # Keep gettext-localized headers and prompts in English.
    extra_env: ClassVar = {"LC_ALL": "C"}

    # Render titles, separators and markers as plain text instead of ANSI-decorated.
    post_args = ("--output=raw",)

    version_cli = "awk"
    """tazpkg has no version command at all: its own version only exists as the
    `tazpkg` row of the installed-packages database. This probe mirrors, verbatim,
    how tazpkg resolves its `VERSION` variable for itself::

        export VERSION=$(awk -F$'\\t' '$1=="tazpkg"{print $2}' \\
            "$PKGS_DB/installed.info")
    """

    version_cli_options = (
        "-F\t",
        '$1=="tazpkg"{print $2}',
        "/var/lib/tazpkg/installed.info",
    )

    version_regexes = (r"^(?P<version>[\d.]+)$",)
    """A bare integer Mercurial revision on cooking releases (`944`) or a dotted
    version on stable ones (`4.9.2`)."""

    _ANSI_REGEXP = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    _PACKAGE_LINE_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<version>\d\S*)\s+\S+\s*$",
    )
    """Data rows are "name version category" triples whose version starts with a
    digit: titles, `===`/`---` separators and "N packages ..." footers all fail
    that shape."""

    def _parse_listing(self, output: str) -> Iterator[tuple[str, str]]:
        """Yield `(package_id, version)` from a decorated tazpkg listing."""
        for line in self._ANSI_REGEXP.sub("", output).splitlines():
            match = self._PACKAGE_LINE_REGEXP.match(line)
            if match:
                yield match.group("package_id"), match.group("version")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ tazpkg list --output=raw
        List of all installed packages
        ================================================================================
        busybox                            1.36.0            base-system
        nano                               6.2               editors
        ================================================================================
        2 packages installed.
        ```
        """
        output = self.run_cli("list")

        for package_id, version in self._parse_listing(output):
            yield self.package(id=package_id, installed_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        tazpkg matches the query as a case-insensitive substring of
        `name-version`, over installed then mirrored packages.

        ```{code-block} shell-session

        $ tazpkg search nano --output=raw
        Installed packages
        --------------------------------------------------------------------------------
        nano                    6.2               editors
        --------------------------------------------------------------------------------
        1 installed package found for: nano
        ```
        """
        output = self.run_cli("search", query)

        for package_id, version in self._parse_listing(output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package from the mirror.

        `--forced` skips the already-installed guard, keeping the call
        non-interactive.

        ```{code-block} shell-session

        $ sudo tazpkg get-install nano --forced --output=raw
        ```
        """
        return self.run_cli("get-install", package_id, "--forced", sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `-i` (no long form) auto-confirms, upgrading every outdated package; the
        command recharges the package lists first.

        ```{code-block} shell-session

        $ sudo tazpkg up -i --output=raw
        ```
        """
        return self.build_cli("up", "-i", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        tazpkg has no per-package upgrade verb: its own upgrade loop re-runs
        `get-install --forced` on each outdated package.

        ```{code-block} shell-session

        $ sudo tazpkg get-install nano --forced --output=raw
        ```
        """
        return self.build_cli("get-install", package_id, "--forced", sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        No `--auto` on purpose: it would also auto-confirm the "remove
        dependents?" follow-up and cascade. On a non-terminal stdout (mpm's
        subprocess pipe) the `(y/N)` prompt is skipped and only the target
        package is removed.

        ```{code-block} shell-session

        $ sudo tazpkg remove nano --output=raw
        ```
        """
        return self.run_cli("remove", package_id, sudo=True)

    def sync(self) -> None:
        """Recharge the package lists from the mirror.

        ```{code-block} shell-session

        $ sudo tazpkg recharge --output=raw
        ```
        """
        self.run_cli("recharge", sudo=True)

    def cleanup_cache(self) -> None:
        """Delete every downloaded package from the cache.

        ```{code-block} shell-session

        $ sudo tazpkg clean-cache --output=raw
        ```
        """
        self.run_cli("clean-cache", sudo=True)
