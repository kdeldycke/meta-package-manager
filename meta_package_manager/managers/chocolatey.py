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

from click_extra.platform import WINDOWS

from ..base import PackageManager
from ..version import parse_version


class Choco(PackageManager):

    platforms = frozenset({WINDOWS})

    requirement = "0.10.4"

    name = "Chocolatey"

    global_args = ("--no-progress", "--no-color")
    prepend_global_args = False

    """
    .. code-block:: shell-session

        ► choco --version
        0.11.0
    """

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► choco list --local-only --limit-output --no-progress --no-color
            adobereader|11.0.10
            ccleaner|5.03.5128
            chocolatey|0.9.9.2
            ConEmu|14.9.23.0
            gimp|2.8.14.1
            git|1.9.5.20150114
        """
        installed = {}

        output = self.run_cli("list", "--local-only", "--limit-output")

        if output:
            regexp = re.compile(r"(.+)\|(.+)")
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, installed_version = match.groups()
                    installed[package_id] = {
                        "id": package_id,
                        "name": package_id,
                        "installed_version": parse_version(installed_version),
                    }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. code-block:: shell-session

            ► choco search VirtualBox --limit-output --no-progress --no-color
            virtualbox|6.1.0
            VirtualBox.ExtensionPack|5.1.10.20161223
            enigmavirtualbox|9.20
            virtualbox-guest-additions-guest.install|6.1.0
            VBoxHeadlessTray|4.2.0.3
            VBoxVmService|6.1
            multipass|1.0.0

        .. code-block:: shell-session

            ► choco search VirtualBox --by-id-only --limit-output --no-progress --no-color
            virtualbox|6.1.0
            VirtualBox.ExtensionPack|5.1.10.20161223
            enigmavirtualbox|9.20
            virtualbox-guest-additions-guest.install|6.1.0

        .. code-block:: shell-session

            ► choco search VirtualBox --by-id-only --exact --limit-output --no-progress --no-color
            virtualbox|6.1.0

        .. code-block:: shell-session

            ► choco search virtualbox --exact --limit-output --no-progress --no-color
            virtualbox|6.1.0

        """
        matches = {}

        query_params = ["--limit-output"]

        if not extended:
            query_params.append("--by-id-only")

        if exact:
            query_params.append("--exact")

        output = self.run_cli("search", query, query_params)

        if output:
            regexp = re.compile(r"(.+)\|(.+)")

            for package_id, latest_version in regexp.findall(output):
                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(latest_version),
                }

        return matches

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► choco install ccleaner --yes --limit-output --no-progress --no-color
        """
        super().install(package_id)
        return self.run_cli("install", package_id, "--yes", "--limit-output")

    @property
    def outdated(self):
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► choco outdated --limit-output --no-progress --no-color
            7zip.commandline|16.02.0.20170209|16.02.0.20170209|false
            7zip.portable|18.1|18.1|false
            atom|1.23.3|1.24.0|false
            autohotkey.portable|1.1.28.00|1.1.28.00|false
            bulkrenameutility|3.0.0.1|3.0.0.1|false
            bulkrenameutility.install|3.0.0.1|3.0.0.1|false
            calibre|3.17.0|3.17.0|false
            chocolatey|0.10.8|0.10.8|false
        """
        outdated = {}

        output = self.run_cli("outdated", "--limit-output")

        if output:
            regexp = re.compile(r"(.+)\|(.+)\|(.+)\|.+")
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, installed_version, latest_version = match.groups()
                    outdated[package_id] = {
                        "id": package_id,
                        "name": package_id,
                        "latest_version": parse_version(latest_version),
                        "installed_version": parse_version(installed_version),
                    }

        return outdated

    def upgrade_cli(self, package_id="all"):
        """
        .. code-block:: shell-session

            ► choco upgrade ccleaner --yes --limit-output --no-progress --no-color

        .. code-block:: shell-session

            ► choco upgrade all --yes --limit-output --no-progress --no-color
        """
        return [
            self.cli_path,
            "upgrade",
            package_id,
            "--yes",
            "--limit-output",
            self.global_args,
        ]
