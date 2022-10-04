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

import re
from typing import Iterator

from click_extra.platform import LINUX

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class Snap(PackageManager):

    homepage_url = "https://snapcraft.io"

    platforms = frozenset({LINUX})

    requirement = "2.0.0"

    post_args = ("--color=never",)

    version_regex = r"snap\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► snap --version
        snap       2.44.1
        snapd      2.44.1
        series     16
        linuxmint  19.3
        kernel     4.15.0-91-generic
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► snap list --color=never
            Name    Version    Rev   Aufzeichnung   Herausgeber     Hinweise
            core    16-2.44.1  8935  latest/stable  canonical✓      core
            wechat  2.0        7     latest/stable  ubuntu-dawndiy  -
            pdftk   2.02-4     9     latest/stable  smoser          -
        """
        output = self.run_cli("list")

        for package in output.splitlines()[1:]:
            package_id = package.split()[0]
            installed_version = package.split()[1]
            yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► snap refresh --list --color=never
            Name            Version  Rev  Herausgeber     Hinweise
            standard-notes  3.3.5    8    standardnotes✓  -
        """
        output = self.run_cli("refresh", "--list")

        for package in output.splitlines()[1:]:
            package_id = package.split()[0]
            latest_version = package.split()[1]
            installed_version = (
                self.run_cli("list", package_id).splitlines()[-1].split()[1]
            )
            yield self.package(
                id=package_id,
                latest_version=latest_version,
                installed_version=installed_version,
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search is extended by default. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. code-block:: shell-session

            ► snap find doc --color=never
            Name       Version      Herausgeber  Hinweise  Zusammenfassung
            journey    2.14.3       2appstudio   -         Your private diary.
            nextcloud  17.0.5snap1  nextcloud✓   -         Nextcloud Server
            skype      8.58.0.93    skype✓       classic   One Skype for all.
        """
        output = self.run_cli("find", query)
        headerless_table = None
        if output:
            table = output.split("\n", 1)
            if len(table) > 1:
                headerless_table = table[1]

        if headerless_table:
            regexp = re.compile(
                r"^(?P<package_id>\S+)\s+(?P<version>\S+)\s+\S+\s+\S+\s+(?P<description>.+)$",
                re.MULTILINE,
            )
            for package_id, version, description in regexp.findall(headerless_table):
                yield self.package(
                    id=package_id,
                    description=description,
                    latest_version=version,
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► snap install standard-notes --color=never
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► snap refresh --color=never
        """
        return self.build_cli("refresh")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► snap refresh standard-notes --color=never
        """
        return self.build_cli("refresh", package_id)
