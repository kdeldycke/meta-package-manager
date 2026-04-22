# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

from __future__ import annotations

import re

from extra_platforms import MACOS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class MacPorts(PackageManager):
    """MacPorts package manager for macOS.

    .. note::

        MacPorts installs into ``/opt/local`` by default and requires root
        privileges for mutating operations. The ``port`` binary is located at
        ``/opt/local/bin/port``.
    """

    homepage_url = "https://www.macports.org"

    platforms = MACOS

    requirement = ">=2.0.0"

    cli_names = ("port",)

    cli_search_path = ("/opt/local/bin",)

    _INSTALLED_REGEXP = re.compile(
        r"^\s+(?P<package_id>\S+)\s+@(?P<version>[^+\s]+)\S*\s+\(active\)",
        re.MULTILINE,
    )

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s+<\s+(?P<latest_version>\S+)",
        re.MULTILINE,
    )

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>[^\t]+)\t(?P<version>[^\t]+)\t[^\t]+\t(?P<description>.+)$",
        re.MULTILINE,
    )

    version_cli_options = ("version",)
    version_regexes = (r"Version:\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ port version
        Version: 2.12.4
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Only active ports are returned. Inactive ports (old versions kept by
        MacPorts) are skipped.

        .. code-block:: shell-session

            $ port -q installed
              curl @8.7.1_0 (active)
              python312 @3.12.3_0+lzma+optimizations (active)
              vim @9.1.0_0 (active)
        """
        output = self.run_cli("-q", "installed")

        for package_id, version in self._INSTALLED_REGEXP.findall(output):
            yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ port -q outdated
            curl                            8.7.1_0 < 8.8.0_0
            python312                       3.12.3_0 < 3.12.4_0
        """
        output = self.run_cli("-q", "outdated")

        for (
            package_id,
            installed_version,
            latest_version,
        ) in self._OUTDATED_REGEXP.findall(output):
            yield self.package(
                id=package_id,
                installed_version=installed_version,
                latest_version=latest_version,
            )

    @search_capabilities(extended_support=True, exact_support=True)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. code-block:: shell-session

            $ port search --name --line vim
            MacVim	9.1.1092	aqua	MacVim - VIM for macOS
            vim	9.1.1092	editors	Vi IMproved
        """
        args: list[str] = ["search", "--name"]
        if extended:
            args.append("--description")
        if exact:
            args.append("--exact")
        args.extend(("--line", query))

        output = self.run_cli(*args)

        for package_id, version, description in self._SEARCH_REGEXP.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ port install vim
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ port upgrade outdated
        """
        return self.build_cli("upgrade", "outdated")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ port upgrade vim
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ port uninstall vim
        """
        return self.run_cli("uninstall", package_id)

    def sync(self) -> None:
        """Sync the local ports tree with remote repositories.

        .. code-block:: shell-session

            $ port sync
        """
        self.run_cli("sync")

    def cleanup(self) -> None:
        """Remove work directories, distfiles, and logs for installed ports.

        .. code-block:: shell-session

            $ port clean --all installed
        """
        self.run_cli("clean", "--all", "installed")
