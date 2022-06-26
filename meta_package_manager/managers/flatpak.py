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

from ..base import Package, PackageManager, no_exact_search, no_extended_search


class Flatpak(PackageManager):

    homepage_url = "https://flatpak.org"

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
        """Fetch installed packages.

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
        output = self.run_cli(
            "list",
            "--app",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

        regexp = re.compile(
            r"(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)"
        )

        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                name, package_id, installed_version = match.groups()
                yield Package(
                    id=package_id,
                    name=name,
                    installed_version=installed_version,
                )

    @property
    def outdated(self):
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► flatpak remote-ls --app --updates --columns=name,application,version --ostree-verbose
            GNOME Dictionary    org.gnome.Dictionary    3.26.0  stable  x86_64
        """
        output = self.run_cli(
            "remote-ls",
            "--app",
            "--updates",
            "--columns=name,application,version",
            "--ostree-verbose",
        )

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
                    current_version.group("version") if current_version else "unknow"
                )

                yield Package(
                    id=package_id,
                    name=name,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    @no_exact_search
    @no_extended_search
    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. code-block:: shell-session

            ► flatpak search gitg --ostree-verbose
            gitg    GUI for git        org.gnome.gitg  3.32.1  stable  flathub
        """
        output = self.run_cli("search", query, "--ostree-verbose")

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
            yield Package(
                id=package_id,
                name=package_name,
                description=description,
                latest_version=version,
            )

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► flatpak install org.gnome.Dictionary
        """
        return self.run_cli("install", package_id)

    def upgrade_cli(self, package_id=None):
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► flatpak update --noninteractive

        .. code-block:: shell-session

            ► flatpak update --noninteractive org.gnome.Dictionary
        """
        return self.build_cli("update", "--noninteractive", package_id)

    def cleanup(self):
        """Removes things we don't need anymore.

        See:
        https://docs.flatpak.org/en/latest/flatpak-command-reference.html#flatpak-repair

        .. code-block:: shell-session

            ► flatpak repair --user
        """
        self.run_cli("repair", "--user")
