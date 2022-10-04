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


class DNF(PackageManager):
    """
    Documentation: https://dnf.readthedocs.io/en/latest/command_ref.html

    See other command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta
    """

    homepage_url = "https://github.com/rpm-software-management/dnf"

    platforms = frozenset({LINUX})

    requirement = "4.0.0"

    cli_names = ("dnf",)

    """
    .. code-block:: shell-session

        ► dnf --version
        4.9.0
    """

    pre_args = ("--color=never",)

    list_cmd_regexp = re.compile(r"(\S+)\.\S+\s+(\S+)\s+\S+")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► dnf --color=never list --installed
            Installed Packages
            acl.x86_64         2.2.53-1.el8                         @anaconda
            audit.x86_64       3.0-0.10.20180831git0047a6c.el8      @anaconda
            audit-libs.x86_64  3.0-0.10.20180831git0047a6c.el8      @anaconda
            (...)
        """
        output = self.run_cli("list", "--installed")

        for package in output.splitlines()[1:]:
            match = self.list_cmd_regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► dnf --color=never list --upgrades
            Last metadata expiration check: 0:22:12 ago on Sun 03 Apr 2022.
            Available Upgrades
            acl.x86_64               2.2.53-1.el8                        updates
            audit.x86_64             3.0-0.10.20180831git0047a6c.el8     updates
            audit-libs.x86_64        3.0-0.10.20180831git0047a6c.el8     updates
            (...)
        """
        output = self.run_cli("list", "--upgrades")

        for package in output.splitlines()[2:]:
            match = self.list_cmd_regexp.match(package)
            if match:
                package_id, latest_version = match.groups()
                yield self.package(id=package_id, latest_version=latest_version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. code-block:: shell-session

            ► dnf --color=never search usd
            Last metadata expiration check: 0:06:37 ago on Sun 03 Apr 2022.
            =================== Name Exactly Matched: usd =====================
            usd.aarch64 : 3D VFX pipeline interchange file format
            =================== Name & Summary Matched: usd ===================
            python3-usd.aarch64 : Development files for USD
            usd-devel.aarch64 : Development files for USD
            ======================= Name Matched: usd =========================
            lvm2-dbusd.noarch : LVM2 D-Bus daemon
            usd-libs.aarch64 : Universal Scene Description library
        """
        output = self.run_cli("search", query)

        regexp = re.compile(r"(\S+)\.\S+\s:\s(\S+)")

        for line in output.splitlines()[1:]:
            # Skip section headers.
            if line.startswith("="):
                continue

            # Extract package ID and description.
            match = regexp.match(line)
            if match:
                package_id, description = match.groups()
                yield self.package(id=package_id, description=description)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes install pip
        """
        return self.run_cli("--assumeyes", "install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes upgrade
        """
        return self.build_cli("upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes upgrade pip
        """
        return self.build_cli("upgrade", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► dnf --color=never check-update
        """
        self.run_cli("check-update")

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes autoremove
            ► dnf --color=never clean all
        """
        self.run_cli("--assumeyes", "autoremove", sudo=True)
        self.run_cli("clean", "all")


class YUM(DNF):
    """yum is dnf is yum."""

    homepage_url = "http://yum.baseurl.org"

    cli_names = ("yum",)
