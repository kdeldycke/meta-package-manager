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

from click_extra.platform import LINUX

from ..base import PackageManager
from ..version import TokenizedString, parse_version


class Snap(PackageManager):

    platforms = frozenset({LINUX})

    requirement = "2.0.0"

    global_args = ("--color=never",)

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
    def installed(self):
        """Fetch installed packages from ``snap list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session
            ► snap list
            Name    Version    Rev   Aufzeichnung   Herausgeber     Hinweise
            core    16-2.44.1  8935  latest/stable  canonical✓      core
            wechat  2.0        7     latest/stable  ubuntu-dawndiy  -
            pdftk   2.02-4     9     latest/stable  smoser          -
        """
        installed = {}

        output = self.run_cli("list")

        if output:
            for package in output.splitlines()[1:]:
                package_id = package.split()[0]
                installed_version = package.split()[1]
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(installed_version),
                }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``snap find`` output.

        .. code-block:: shell-session
            ► snap find doc
            Name       Version      Herausgeber  Hinweise  Zusammenfassung
            journey    2.14.3       2appstudio   -         Your private diary.
            nextcloud  17.0.5snap1  nextcloud✓   -         Nextcloud Server
            skype      8.58.0.93    skype✓       classic   One Skype for all.
        """
        matches = {}

        output = self.run_cli("find", query)

        if output:

            for package in output.splitlines()[1:]:

                package_id = package.split()[0]
                version = package.split()[1]
                description = " ".join(map(str, package.split()[4:]))

                # Skip all non-stricly matching package IDs in exact mode.
                if exact:
                    if query != package_id:
                        continue

                else:
                    # Exclude packages not featuring the search query in their
                    # ID or name.
                    if not extended:
                        query_parts = set(map(str, TokenizedString(query)))
                        pkg_parts = set(map(str, TokenizedString(package_id)))
                        if not query_parts.issubset(pkg_parts):
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

            ► snap install standard-notes

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``snap refresh --list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► snap refresh --list
            Name            Version  Rev  Herausgeber     Hinweise
            standard-notes  3.3.5    8    standardnotes✓  -
        """
        outdated = {}

        output = self.run_cli("refresh", "--list")

        if output and len(output.splitlines()) > 1:
            for package in output.splitlines()[1:]:
                package_id = package.split()[0]
                latest_version = package.split()[1]
                installed_version = (
                    self.run_cli("list", package_id).splitlines()[-1].split()[1]
                )
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(latest_version),
                    "installed_version": parse_version(installed_version),
                }

        return outdated

    def upgrade_cli(self, package_id=None):
        """Snap has an auto-update function, but snaps can be updated
        manually.
        """
        cmd = [self.cli_path, self.global_args, "refresh"]
        if package_id:
            cmd.append(package_id)
        return cmd
