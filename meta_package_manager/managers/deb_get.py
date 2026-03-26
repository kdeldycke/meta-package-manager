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

from extra_platforms import LINUX_LIKE

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class Deb_Get(PackageManager):
    """``deb-get`` installs third-party software on Debian and Ubuntu via ``.deb``
    packages sourced from GitHub releases, direct URLs, and PPAs.

    .. note::
        ``deb-get`` wraps ``apt`` under the hood for actual package installation
        and removal, so all operations that modify the system require ``sudo``.
    """

    name = "Deb Get"

    homepage_url = "https://github.com/wimpysworld/deb-get"

    platforms = LINUX_LIKE

    version_cli_options = ("version",)
    """
    .. code-block:: shell-session

        $ deb-get version
        0.4.5
    """

    version_regexes = (r"(?P<version>\d+\.\d+\.\d+)",)

    _OUTDATED_REGEXP = re.compile(
        r"\[\+\] (?P<package_id>\S+)"
        r" \((?P<installed_version>\S+)\)"
        r" has an update pending\."
        r" (?P<latest_version>\S+) is available\.",
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ deb-get list --installed
            activitywatch
            anydesk
            bitwarden
            deb-get
            freeplane
            google-chrome-stable
            ipscan
            protonvpn
            zoom

        .. note::
            ``deb-get list --installed`` only outputs bare package names without
            version information.
        """
        output = self.run_cli("list", "--installed")
        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ sudo deb-get update
            (...)
              [+] ipscan (3.9.2) has an update pending. 3.9.3 is available.

        .. note::
            Outdated detection piggybacks on ``deb-get update`` which also
            refreshes the package index.
        """
        output = self.run_cli("update", sudo=True)
        for match in self._OUTDATED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching, and does not
            provide version information. Returns the best subset of results and
            lets
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`
            refine them.

        .. code-block:: shell-session

            $ deb-get search zoom
            zoom
        """
        output = self.run_cli("search", query)
        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo deb-get install ipscan
        """
        return self.run_cli("install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ sudo deb-get upgrade
        """
        return self.build_cli("upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package by reinstalling it.

        .. code-block:: shell-session

            $ sudo deb-get install ipscan
        """
        return self.build_cli("install", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ sudo deb-get remove ipscan
        """
        return self.run_cli("remove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ sudo deb-get update
        """
        self.run_cli("update", sudo=True)

    def cleanup(self) -> None:
        """Remove cached downloads.

        .. code-block:: shell-session

            $ sudo deb-get clean
        """
        self.run_cli("clean", sudo=True)
