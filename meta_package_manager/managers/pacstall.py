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

from extra_platforms import LINUX_LIKE

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class Pacstall(PackageManager):
    """Pacstall is an AUR-inspired package manager for Ubuntu and other Linux
    distributions.

    .. note::
        Pacstall builds packages from source using "pacscripts" and installs
        them as ``.deb`` files via ``dpkg``.
    """

    homepage_url = "https://pacstall.dev"

    platforms = LINUX_LIKE

    requirement = ">=6.0.0"

    extra_env = {"NO_COLOR": "1", "DISABLE_PROMPTS": "1"}  # noqa: RUF012
    """Suppress ANSI colors and disable interactive prompts."""

    version_regexes = (r"(?P<version>\d+\.\d+\.\d+)",)
    """
    .. code-block:: shell-session

        $ pacstall --version
        6.3.7 Vanilla
    """

    _OUTDATED_REGEXP = re.compile(
        r"^\t(?P<package_id>\S+)\s+@\s+\S+"
        r"\s+\(\s*(?P<installed_version>\S+)"
        r"\s*->\s*(?P<latest_version>\S+)\s*\)",
        re.MULTILINE,
    )

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+@\s+\S+$",
        re.MULTILINE,
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ pacstall --list
            neofetch
            neovim

        .. note::
            When piped, ``pacstall --list`` outputs bare package names without
            versions. A follow-up ``pacstall --cache-info <pkg> version`` call
            retrieves the installed version per package.
        """
        output = self.run_cli("--list")
        for line in output.splitlines():
            package_id = line.strip()
            if not package_id:
                continue
            version_output = self.run_cli("--cache-info", package_id, "version")
            installed_version = version_output.strip() if version_output else None
            yield self.package(
                id=package_id,
                installed_version=installed_version,
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ pacstall --list-upgrades
            Upgradable: 2
            \tneofetch @ pacstall-programs#master ( 7.1.0-2 -> 7.2.0-1 )
            \tneovim @ pacstall-programs#master ( 0.9.4-1 -> 0.10.0-1 )
        """
        output = self.run_cli("--list-upgrades")
        for match in self._OUTDATED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching, and does not
            provide version information. Returns the best subset of results and
            lets
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`
            refine them.

        .. code-block:: shell-session

            $ pacstall --search neovim
            neovim @ pacstall-programs
            neovim-git @ pacstall-programs
        """
        output = self.run_cli("--search", query)
        for match in self._SEARCH_REGEXP.finditer(output):
            yield self.package(id=match.group("package_id"))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ pacstall --install neofetch
        """
        return self.run_cli("--install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ pacstall --upgrade
        """
        return self.build_cli("--upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package by reinstalling it.

        .. code-block:: shell-session

            $ pacstall --install neofetch
        """
        return self.build_cli("--install", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ pacstall --remove neofetch
        """
        return self.run_cli("--remove", package_id)

    def sync(self) -> None:
        """Sync package metadata from remote repositories.

        .. code-block:: shell-session

            $ pacstall --update
        """
        self.run_cli("--update")
