# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import sys
from itertools import groupby
from operator import itemgetter
from typing import Iterator

if sys.version_info < (3, 8):
    from typing_extensions import TypedDict
else:
    from typing import TypedDict

import xmltodict
from click_extra.platform import LINUX

from ..base import Package, PackageManager
from ..capabilities import version_not_implemented
from ..version import TokenizedString, parse_version


class Zypper(PackageManager):
    """
    Documentation:
    - https://en.opensuse.org/Portal:Zypper
    - https://documentation.suse.com/smart/linux/html/concept-zypper/index.html
    - https://opensuse.github.io/openSUSE-docs-revamped-temp/zypper/

    See other command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta
    """

    homepage_url = "https://en.opensuse.org/Portal:Zypper"

    platforms = frozenset({LINUX})

    requirement = "1.14.0"

    pre_args = (
        "--no-color",
        "--no-abbrev",
        "--non-interactive",
        "--no-cd",
        "--no-refresh",
    )

    version_regex = r"zypper\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► zypper --version
        zypper 1.14.11
    """

    class SearchResult(TypedDict):
        id: str
        version: TokenizedString

    def _search(self, *args: str) -> Iterator[SearchResult]:
        """Utility method to parse and interpret results of the ``zypper search``
        command.

        This is reused by the ``installed`` and ``search`` operations.

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package [*args]
            <?xml version='1.0'?>
            <stream>
                <message type="info">Loading repository data...</message>
                <message type="info">Reading installed packages...</message>

                <search-result version="0.0">
                    <solvable-list>
                        <solvable status="installed" name="aaa_base" kind="package"
                            edition="12.12-bp12.3.1" arch="x86_64"/>

                        <solvable status="installed" name="adwaita-icon-theme" kind="package"
                            edition="1.0.3-bp153.1.1" arch="x86_64"/>
                        <solvable status="other-version" name="adwaita-icon-theme" kind="package"
                            edition="1.0.1-bp153.1.1" arch="x86_64"/>

                        <solvable status="not-installed" name="kopete-devel" kind="package"
                            edition="20.04.2-bp153.2.5.1" arch="x86_64" repository="Update"/>
                        <solvable status="not-installed" name="kopete-devel" kind="package"
                            edition="20.04.2-bp153.2.2.1" arch="x86_64" repository="Update"/>
                        <solvable status="not-installed" name="kopete-devel" kind="package"
                            edition="20.04.2-bp153.2.2.1" arch="x86_64" repository="Debug"/>
                        <solvable status="not-installed" name="kopete-devel" kind="package"
                            edition="20.04.2-bp153.2.5.1" arch="i586" repository="Update"/>
                        <solvable status="not-installed" name="kopete-devel" kind="package"
                            edition="20.04.2-bp153.2.2.1" arch="i586" repository="Update"/>

                        (...)
                    </solvable-list>
                </search-result>
            </stream>
        """
        output = self.run_cli(
            "--xmlout",
            "search",
            # --details is the only option that is providing the package's version...
            "--details",
            # ...but comes with duplicate results due to source packages, different arch and old releases.
            # So we filters them out to only keep proper packages.
            "--type",
            "package",
            # Additional search arguments.
            *args,
        )

        package_list = (
            xmltodict.parse(output)
            .get("stream", {})
            .get("search-result", {})
            .get("solvable-list", {})
            .get("solvable", [])
        )

        # Group packages by ID.
        key_func = itemgetter("@name")

        # Skip old packages reported in the results as 'other-version'.
        fresh_packages = sorted(
            (p for p in package_list if p.get("@status") != "other-version"),
            key=key_func,
        )

        # Returns the highest version for a package ID among all repositories and
        # arch variations.
        for key, group in groupby(fresh_packages, key_func):
            yield {
                "id": key,
                "version": max(parse_version(p["@edition"]) for p in group),
            }

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package --installed-only
        """
        for package in self._search("--installed-only"):
            yield self.package(id=package["id"], installed_version=package["version"])

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout list-updates
            <?xml version='1.0'?>
            <stream>
                <message type="info">Loading repository data...</message>
                <message type="info">Reading installed packages...</message>
                <update-status version="0.6">
                    <update-list>
                        <update name="git" kind="package"
                            edition="2.34.1-10.9.1" edition-old="2.26.2-3.34.1" arch="x86_64">
                            <summary>Fast, scalable revision control system</summary>
                            <description>
                                Blah blah blah...
                            </description>
                            <license/>
                            <source url="http://download.opensuse.org/updata/leap/15.3/sle" alias="repo-sle-update"/>
                        </update>
                        (...)
                    </update-list>
                </update-status>
            </stream>
        """
        output = self.run_cli("--xmlout", "list-updates")

        package_list = []
        update_list = (
            xmltodict.parse(output)
            .get("stream", {})
            .get("update-status", {})
            .get("update-list", {})
        )
        if update_list:
            package_list = update_list.get("update", [])

        for package in package_list:
            yield self.package(
                id=package["@name"],
                description=package.get("description"),
                latest_version=package["@edition"],
                installed_version=package["@edition-old"],
            )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package kopete

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package --search-description kopete

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package --match-exact kopete

        .. code-block:: shell-session

            ► zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh --xmlout search --details --type package --search-description --match-exact kopete
        """
        search_param = []
        if extended:
            search_param.append("--search-description")
        if exact:
            search_param.append("--match-exact")

        for package in self._search(*search_param, query):
            yield self.package(id=package["id"], installed_version=package["version"])

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► sudo zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh install kopete
        """
        return self.run_cli("install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh update
        """
        return self.build_cli("update", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh update kopete
        """
        return self.build_cli("update", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► sudo zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh refresh
        """
        self.run_cli("refresh", sudo=True)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► sudo zypper --no-color --no-abbrev --non-interactive --no-cd --no-refresh clean
        """
        self.run_cli("clean", sudo=True)
