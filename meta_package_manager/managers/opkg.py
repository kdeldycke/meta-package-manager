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


class OPKG(PackageManager):

    homepage_url = "https://git.yoctoproject.org/cgit/cgit.cgi/opkg/"

    platforms = frozenset({LINUX})

    requirement = "0.2.0"

    version_regex = r"opkg\s+version\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► opkg --version
        opkg version 0.3.6 (libsolv 0.7.5)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► opkg list-installed
            3rd-party-feed-configs - 1.1-r0
            aio-grab - 1.0+git71+c79e264-r0
            alsa-conf - 1.1.9-r0
            alsa-state - 0.2.0-r5
            alsa-states - 0.2.0-r5
            alsa-utils-alsactl - 1.1.9-r0
            avahi-daemon - 0.7-r0
            base-files - 3.0.14-r89
            base-files-dev - 3.0.14-r89
            base-passwd - 3.5.29-r0
            bash - 5.0-r0
            bash-completion - 2.9-r0
            bash-completion-dev - 2.9-r0
            bash-dev - 5.0-r0
            binutils - 2.32.0-r0
            busybox - 1.31.0-r0
            busybox-inetd - 1.31.0-r0
            busybox-mdev - 1.31.0-r0
            busybox-syslog - 1.31.0-r0
            busybox-udhcpc - 1.31.0-r0
        """
        output = self.run_cli("list-installed")

        regexp = re.compile(r"(\S+) - (\S+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► opkg list-upgradable
            openpli-bootlogo - 20190717-r0 - 20190718-r0
            enigma2-hotplug - 2.7+git1720+55c6b34-r0 - 2.7+git1722+daf2f52-r0
        """
        output = self.run_cli("list-upgradable")

        regexp = re.compile(r"(\S+) - (\S+) - (\S+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version, latest_version = match.groups()
                yield self.package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. warning::
            There is no search command so we simulate it by listing all packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. code-block:: shell-session

            ► opkg list
        """
        output = self.run_cli("list")

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)
            \ -\
            (?P<version>\S+)
            \ -\
            (?P<description>.+)
            """,
            re.VERBOSE | re.MULTILINE,
        )

        for package_id, version, description in regexp.findall(output):
            yield self.package(
                id=package_id, description=description, latest_version=version
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► opkg install enigma2-hotplug
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► opkg upgrade
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► opkg upgrade enigma2-hotplug
        """
        return self.build_cli("upgrade", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► opkg update
        """
        self.run_cli("update")
