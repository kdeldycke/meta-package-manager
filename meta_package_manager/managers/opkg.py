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


class OPKG(PackageManager):

    platforms = frozenset({LINUX})

    requirement = "0.2.0"

    version_regex = r"opkg\s+version\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► opkg --version
        opkg version 0.3.6 (libsolv 0.7.5)
    """

    def sync(self):
        """

        Raw CLI output samples:

        .. code-block:: shell-session
        """
        super().sync()
        self.run_cli("update")

    @property
    def installed(self):
        """Fetch installed packages from ``opkg list-installed`` output.

        Raw CLI output samples:

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
        installed = {}

        output = self.run_cli("list-installed")

        if output:
            regexp = re.compile(r"(\S+) - (\S+)")
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
        """Simulate search by listing all packages."""
        matches = {}

        # opkg doesn't have a working 'search', so get all packages and
        # filter the packages later.
        output = self.run_cli("list")

        if output:
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

                # Skip all non-stricly matching package IDs in exact mode.
                if exact:
                    if query != package_id:
                        continue

                else:
                    # All other modes search for matching in package IDs and
                    # names.
                    searched_content = set(map(str, TokenizedString(package_id)))

                    # Also search within the description in extended mode.
                    if extended:
                        searched_content.update(
                            set(map(str, TokenizedString(description)))
                        )

                    # Skip package if not all sub-strings are present in the
                    # searched content.
                    query_parts = set(map(str, TokenizedString(query)))
                    if not query_parts.issubset(searched_content):
                        continue

                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(version),
                }

        return matches

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► opkg install enigma2-hotplug

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``opkg list-upgradable`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► opkg list-upgradable
            openpli-bootlogo - 20190717-r0 - 20190718-r0
            enigma2-hotplug - 2.7+git1720+55c6b34-r0 - 2.7+git1722+daf2f52-r0
        """
        outdated = {}

        output = self.run_cli("list-upgradable")

        if output:
            regexp = re.compile(r"(\S+) - (\S+) - (\S+)")
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

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, "upgrade"]
        if package_id:
            cmd.append(package_id)
        return cmd
