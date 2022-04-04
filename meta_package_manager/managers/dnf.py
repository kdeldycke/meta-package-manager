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

import re

from click_extra.platform import LINUX

from ..base import PackageManager
from ..version import parse_version


class DNF(PackageManager):

    """
    Documentation: https://dnf.readthedocs.io/en/latest/command_ref.html
    """

    platforms = frozenset({LINUX})

    requirement = "4.0.0"

    """
    .. code-block:: shell-session

        ► dnf --version
        4.9.0
    """

    pre_args = (
        "--color=never",
    )

    list_cmd_regexp = re.compile(r"(\S+)\.\S+\s+(\S+)\s+\S+")

    @property
    def installed(self):
        """
        .. code-block:: shell-session

            ► dnf --color=never list --installed
            Installed Packages
            acl.x86_64               2.2.53-1.el8                          @anaconda
            audit.x86_64             3.0-0.10.20180831git0047a6c.el8       @anaconda
            audit-libs.x86_64        3.0-0.10.20180831git0047a6c.el8       @anaconda
            (...)
        """
        installed = {}

        output = self.run_cli("list", "--installed")

        for package in output.splitlines()[1:]:
            match = self.list_cmd_regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(installed_version),
                }

        return installed

    @property
    def outdated(self):
        """
        .. code-block:: shell-session

            ► dnf --color=never list --upgrades
            Last metadata expiration check: 0:22:12 ago on Sun 03 Apr 2022.
            Available Upgrades
            acl.x86_64               2.2.53-1.el8                          updates
            audit.x86_64             3.0-0.10.20180831git0047a6c.el8       updates
            audit-libs.x86_64        3.0-0.10.20180831git0047a6c.el8       updates
            (...)
        """
        outdated = {}

        output = self.run_cli("list", "--upgrades")

        for package in output.splitlines()[2:]:
            match = self.list_cmd_regexp.match(package)
            if match:
                package_id, latest_version = match.groups()
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(latest_version),
                }

        return outdated

    def install(self, package_id):
        """
        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes install pip
        """
        super().install(package_id)
        return self.run_cli("--assumeyes", "install", package_id, override_pre_cmds=("sudo",))

    def upgrade_cli(self, package_id=None):
        """
        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes upgrade pip

        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes upgrade
        """
        return self.build_cli("upgrade", package_id)

    def sync(self):
        """
        .. code-block:: shell-session

            ► dnf --color=never check-update
        """
        super().sync()
        self.run_cli("check-update")

    def cleanup(self):
        """
        .. code-block:: shell-session

            ► sudo dnf --color=never --assumeyes autoremove
            ► dnf --color=never clean all
        """
        super().cleanup()
        self.run_cli("--assumeyes", "autoremove", override_pre_cmds=("sudo",))
        self.run_cli("clean", "all")
