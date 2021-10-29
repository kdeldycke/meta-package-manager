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
from click_extra.platform import MACOS

from ..base import PackageManager
from ..version import parse_version


class MAS(PackageManager):

    platforms = frozenset({MACOS})

    # 'mas search' output has been fixed in 1.6.1:
    # https://github.com/mas-cli/mas/pull/205
    requirement = "1.6.1"

    name = "Mac AppStore"

    version_cli_options = ("version",)
    """
    .. code-block:: shell-session

        ► mas version
        1.8.3
    """

    @property
    def installed(self):
        """Fetch installed packages from ``mas list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► mas list
            408981434 iMovie (10.1.4)
            747648890 Telegram (2.30)
        """
        installed = {}

        output = self.run_cli("list")

        if output:
            regexp = re.compile(r"(\d+) (.*) \((\S+)\)$")
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, package_name, installed_version = match.groups()
                    installed[package_id] = {
                        "id": package_id,
                        "name": package_name,
                        # Normalize unknown version. See:
                        # https://github.com/mas-cli/mas/commit
                        # /1859eaedf49f6a1ebefe8c8d71ec653732674341
                        "installed_version": parse_version(installed_version),
                    }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``mas search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► mas search python
               689176796  Python Runner   (1.3)
               630736088  Learning Python (1.0)
               945397020  Run Python      (1.0)
              1164498373  PythonGames     (1.0)
              1400050251  Pythonic        (1.0.0)
        """
        matches = {}

        if extended:
            logger.warning(
                f"Extended search not supported for {self.id}. Fallback to Fuzzy."
            )

        output = self.run_cli("search", query)

        if output:
            regexp = re.compile(
                r"""
                (?P<package_id>\d+)
                \s+
                (?P<package_name>.+?)
                \s+
                \(
                    (?P<version>\S+)
                \)
                """,
                re.MULTILINE | re.VERBOSE,
            )

            for package_id, package_name, version in regexp.findall(output):

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

            ► mas install 945397020

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``mas outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► mas outdated

        .. todo

            An example of ``mas outdated`` output is missing above.
        """
        outdated = {}

        output = self.run_cli("outdated")

        if output:
            regexp = re.compile(r"(\d+) (.*) \((\S+) -> (\S+)\)$")
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    (
                        package_id,
                        package_name,
                        installed_version,
                        latest_version,
                    ) = match.groups()
                    outdated[package_id] = {
                        "id": package_id,
                        "name": package_name,
                        "latest_version": parse_version(latest_version),
                        # Normalize unknown version. See:
                        # https://github.com/mas-cli/mas/commit
                        # /1859eaedf49f6a1ebefe8c8d71ec653732674341
                        "installed_version": parse_version(installed_version),
                    }

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, "upgrade"]
        if package_id:
            cmd.append(package_id)
        return cmd
