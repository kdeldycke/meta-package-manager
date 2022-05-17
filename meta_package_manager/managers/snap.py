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

from .. import logger
from ..base import PackageManager
from ..version import parse_version


class Snap(PackageManager):

    platforms = frozenset({LINUX})

    requirement = "2.0.0"

    post_args = ("--color=never",)

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
        """Fetch installed packages.

        .. code-block:: shell-session

            ► snap list --color=never
            Name    Version    Rev   Aufzeichnung   Herausgeber     Hinweise
            core    16-2.44.1  8935  latest/stable  canonical✓      core
            wechat  2.0        7     latest/stable  ubuntu-dawndiy  -
            pdftk   2.02-4     9     latest/stable  smoser          -
        """
        installed = {}

        output = self.run_cli("list")

        for package in output.splitlines()[1:]:
            package_id = package.split()[0]
            installed_version = package.split()[1]
            installed[package_id] = {
                "id": package_id,
                "name": package_id,
                "installed_version": parse_version(installed_version),
            }

        return installed

    @property
    def outdated(self):
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► snap refresh --list --color=never
            Name            Version  Rev  Herausgeber     Hinweise
            standard-notes  3.3.5    8    standardnotes✓  -
        """
        outdated = {}

        output = self.run_cli("refresh", "--list")

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

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. caution::
            Search is extended by default. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them

        .. code-block:: shell-session

            ► snap find doc --color=never
            Name       Version      Herausgeber  Hinweise  Zusammenfassung
            journey    2.14.3       2appstudio   -         Your private diary.
            nextcloud  17.0.5snap1  nextcloud✓   -         Nextcloud Server
            skype      8.58.0.93    skype✓       classic   One Skype for all.
        """
        if not extended:
            logger.warning(
                f"{self.id} does not implement non-extended search operation."
            )
        if exact:
            logger.warning(f"{self.id} does not implement exact search operation.")

        output = self.run_cli("find", query)

        regexp = re.compile(
            r"^(?P<package_id>\S+)\s+(?P<version>\S+)\s+\S+\s+\S+\s+(?P<description>.+)$",
            re.MULTILINE,
        )

        for package_id, version, description in regexp.findall(
            output.split("\n", 1)[1]
        ):
            yield {
                "id": package_id,
                "name": package_id,
                "description": description,
                "latest_version": parse_version(version),
            }

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► snap install standard-notes --color=never
        """
        return self.run_cli("install", package_id)

    def upgrade_cli(self, package_id=None):
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        Snap has an auto-update function, but snaps can be updated manually.

        .. code-block:: shell-session

            ► snap refresh --color=never

        .. code-block:: shell-session

            ► snap refresh standard-notes --color=never
        """
        return self.build_cli("refresh", package_id)
