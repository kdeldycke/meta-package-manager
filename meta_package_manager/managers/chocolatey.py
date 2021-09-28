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

from ..base import PackageManager
from ..platform import WINDOWS
from ..version import parse_version


class Choco(PackageManager):

    platforms = frozenset([WINDOWS])

    requirement = "0.10.4"

    name = "Chocolatey"

    global_args = ["--no-progress", "--no-color"]

    version_cli_options = ["version"]
    version_regex = r"Chocolatey\s+v(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► choco version
        Chocolatey v0.11.0 Business
    """

    def sync(self):
        """
        .. code-block:: shell-session

            ► choco sync --no-progress --no-color
        """
        super().sync()
        self.run_cli("sync", self.global_args)

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► choco list --local-only --limit-output --no-progress --no-color
            adobereader 11.0.10
            ccleaner 5.03.5128
            chocolatey 0.9.9.2
            ConEmu 14.9.23.0
            gimp 2.8.14.1
            git 1.9.5.20150114
        """
        installed = {}

        output = self.run_cli(
            "list", "--local-only", "--limit-output", self.global_args
        )

        if output:
            regexp = re.compile(r"(\S+)\s+(\S+)")
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

            ► choco search virtualbox --by-id-only --limit-output --no-progress --no-color
            ► choco search virtualbox --by-id-only --exact --limit-output --no-progress --no-color
            ► choco search virtualbox --exact --limit-output --no-progress --no-color

            ► choco search virtualbox --limit-output --no-progress --no-color
            virtualbox 6.1.0 [Approved]
            VirtualBox.ExtensionPack 5.1.10.20161223 [Approved]
            enigmavirtualbox 9.20 [Approved] Downloads cached for licensed users - Possibly broken for FOSS users (due to original download location changes by vendor)
            virtualbox-guest-additions-guest.install 6.1.0 [Approved] Downloads cached for licensed users
            VBoxHeadlessTray 4.2.0.3
            VBoxVmService 6.1 [Approved] Downloads cached for licensed users
            multipass 1.0.0 [Approved]
            psievm 0.2.7.29815 [Approved]
            disk2vhd 2.01.0.20160213 [Approved] Downloads cached for licensed users
            packer 1.5.1 [Approved]
            vagrant 2.2.6 [Approved] Downloads cached for licensed users
            VBoxGuestAdditions.install 99.99.99.99 [Approved]
            docker-toolbox 19.03.1 [Approved] Downloads cached for licensed users
        """
        matches = {}

        query_params = ["--limit-output"]

        if not extended:
            query_params.append("--by-id-only")

        if exact:
            query_params.append("--exact")

        output = self.run_cli("search", query, query_params, self.global_args)

        if output:
            regexp = re.compile(r"(\S+)\s+(\S+)")

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

            ► choco install ccleaner --no-progress --no-color
        """
        super().install(package_id)
        return self.run_cli("install", package_id, self.global_args)

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

        output = self.run_cli("outdated", "--limit-output", self.global_args)

        if output:
            regexp = re.compile(r"(.+)|(.+)|(.+)|.+")
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

    def upgrade_cli(self, package_id):
        """
        .. code-block:: shell-session

            ► choco upgrade ccleaner --no-progress --no-color
        """
        return [self.cli_path, "upgrade", package_id, self.global_args]

    def upgrade_all_cli(self):
        """
        .. code-block:: shell-session

            ► choco upgrade all --no-progress --no-color
        """
        return [self.cli_path, "upgrade", "all", self.global_args]

    def cleanup(self):
        """
        .. code-block:: shell-session

            ► choco optimize
        """
        super().cleanup()
        self.run_cli("optimize")
