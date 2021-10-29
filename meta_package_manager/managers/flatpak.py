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

from click_extra.logging import logger
from click_extra.platform import LINUX

from ..base import PackageManager
from ..version import parse_version


class Flatpak(PackageManager):

    platforms = frozenset({LINUX})

    requirement = "1.2.0"

    version_regex = r"Flatpak\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► flatpak --version
        Flatpak 1.4.2
    """

    @property
    def installed(self):
        """Fetch installed packages from ``flatpak list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► flatpak list --app --columns=name,application,version \
            > --ostree-verbose
            Name                      Application ID                   Version
            Peek                      com.uploadedlobster.peek         1.3.1
            Fragments                 de.haeckerfelix.Fragments        1.4
            GNOME MPV                 io.github.GnomeMpv               0.16
            Syncthing GTK             me.kozec.syncthingtk             v0.9.4.3
            Builder                   org.flatpak.Builder
        """
        installed = {}

        output = self.run_cli(
            "list",
            "--app",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

        if output:
            regexp = re.compile(
                r"(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)"
            )
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    name, package_id, installed_version = match.groups()
                    installed[package_id] = {
                        "id": package_id,
                        "name": name,
                        "installed_version": parse_version(installed_version),
                    }
        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``flatpak search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► flatpak search gitg --ostree-verbose
            gitg    GUI for git        org.gnome.gitg  3.32.1  stable  flathub
        """
        matches = {}

        if extended:
            logger.warning(
                f"Extended search not supported for {self.id}. Fallback to Fuzzy."
            )

        output = self.run_cli("search", query, "--ostree-verbose")

        if output:
            regexp = re.compile(
                r"""
                ^(?P<package_name>\S+)\t
                (?P<description>\S+)\t
                (?P<package_id>\S+)\t
                (?P<version>\S+)\t
                (?P<branch>\S+)\t
                (?P<remotes>.+)
                """,
                re.VERBOSE,
            )

            for (
                package_name,
                description,
                package_id,
                version,
                branch,
                remotes,
            ) in regexp.findall(output):

                # Filters out fuzzy matches, only keep stricly matching
                # packages.
                if exact and query not in (package_id, package_name):
                    continue

                matches[package_id] = {
                    "id": package_id,
                    "name": package_name,
                    "latest_version": parse_version(version),
                }

        return matches

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► flatpak install org.gnome.Dictionary

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``flatpak remote-ls`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► flatpak remote-ls --app --updates --ostree-verbose
            GNOME Dictionary    org.gnome.Dictionary    3.26.0  stable  x86_64
        """
        outdated = {}

        output = self.run_cli(
            "remote-ls",
            "--app",
            "--updates",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

        if output:
            regexp = re.compile(
                r"(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)"
            )
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    name, package_id, latest_version = match.groups()

                    info_installed_output = self.run_cli(
                        "info",
                        "--ostree-verbose",
                        package_id,
                    )
                    current_version = re.search(
                        r"version:\s(?P<version>\S.*?)\n",
                        info_installed_output,
                        re.IGNORECASE,
                    )

                    installed_version = (
                        current_version.group("version")
                        if current_version
                        else "unknow"
                    )

                    outdated[package_id] = {
                        "id": package_id,
                        "name": name,
                        "latest_version": parse_version(latest_version),
                        "installed_version": parse_version(installed_version),
                    }

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, self.global_args, "update", "--noninteractive"]
        if package_id:
            cmd.append(package_id)
        return cmd

    def cleanup(self):
        """Runs:

        .. code-block:: shell-session

            ► flatpak repair --user

        See: https://docs.flatpak.org/en/latest
        /flatpak-command-reference.html#flatpak-repair
        """
        super().cleanup()
        self.run_cli("repair", "--user")
