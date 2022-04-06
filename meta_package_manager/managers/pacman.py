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
from ..version import TokenizedString, parse_version

class Pacman(PackageManager):

    platforms = frozenset({LINUX})

    requirement = "5.0.0"

    pre_args = ("--noconfirm",)

    version_regex = r".*Pacman\s+v(?P<version>\S+)"
    """
    .. code-block:: shell-session
        ► pacman --version

         .--.                  Pacman v6.0.1 - libalpm v13.0.1
        / _.-' .-.  .-.  .-.   Copyright (C) 2006-2021 Pacman Development Team
        \  '-. '-'  '-'  '-'   Copyright (C) 2002-2006 Judd Vinet
         '--'
                            This program may be freely redistributed under
                            the terms of the GNU General Public License.

    """

    @property
    def installed(self):
        """Fetch installed packages from ``pacman --query`` output.

        Raw CLI output sample:

        .. code-block:: shell-session

            ► pacman --query
            a52dec 0.7.4-11
            aalib 1.4rc5-14
            abseil-cpp 20211102.0-2
            accountsservice 22.08.8-2
            acl 2.3.1-2
            acme.sh 3.0.2-1
            acpi 1.7-3
            acpid 2.0.33-1
        """
        installed = {}

        output = self.run_cli("--query")

        regexp = re.compile(r"(\S+) (\S+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(installed_version)
                }

        return installed

    @property
    def outdated(self):
        """Fetch outdated packages from ``pacman -Qu`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► pacman -Qu
            linux 4.19.1.arch1-1 -> 4.19.2.arch1-1 
            linux-headers 4.19.1.arch1-1 -> 4.19.2.arch1-1
        """
        outdated = {}

        output = self.run_cli("-Qu")

        regexp = re.compile(r"(\S+) (\S+) -> (\S+)")
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

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► pacman -S firefox
        """
        super().install(package_id)
        return self.run_cli("-S", package_id)

    def upgrade_cli(self, package_id=None):
        """Upgrade one package.

        .. code-block:: shell-session

            ► pacman -S firefox
        """
        return self.build_cli("-S", package_id)
    
    def sync(self):
        super().sync()
        self.run_cli("-Sy")

    def cleanup(self):
        super().cleanup()
        self.run_cli("-Scc")

    def upgrade_all_cli(self):
        return self.build_cli("-Syu")

    def search(self, query, extended, exact):
        """
        code-block:: shell-session

            ► pacman -Ss fire
            extra/dump_syms 0.0.7-1
                Symbol dumper for Firefox
            extra/firefox 99.0-1
                Standalone web browser from mozilla.org
            extra/firefox-i18n-ach 99.0-1
                Acholi language pack for Firefox
            extra/firefox-i18n-af 99.0-1
                Afrikaans language pack for Firefox
            extra/firefox-i18n-an 99.0-1
                Aragonese language pack for Firefox
            extra/firefox-i18n-ar 99.0-1
                Arabic language pack for Firefox
            extra/firefox-i18n-ast 99.0-1
                Asturian language pack for Firefox
        """
        matches = {}

        if exact:
            query = f"^{query}$"

        output = self.run_cli("-Ss", query)

        regexp = re.compile(r"(?P<package_id>\S+)\s+(?P<version>\S+).*\n\s+(?P<description>.+)", re.MULTILINE | re.VERBOSE)

        for package_id, version, description in regexp.findall(output):
            matches[package_id] = {
                "id": package_id,
                "name": package_id,
                "latest_version": parse_version(version),
            }

        return matches
