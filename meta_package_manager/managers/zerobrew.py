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

import json
import re
from typing import ClassVar

from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class ZeroBrew(PackageManager):
    """ZeroBrew is a fast, Homebrew-compatible package manager written in Rust.

    .. note::
        ZeroBrew uses Homebrew's formula ecosystem but stores packages in a
        content-addressable store at ``/opt/zerobrew``.

    .. caution::
        ZeroBrew has no ``search`` command. Use ``brew search`` or browse the
        Homebrew formula repository instead.
    """

    name = "ZeroBrew"

    homepage_url = "https://github.com/lucasgelfond/zerobrew"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=0.3.0"
    """Minimum version required for ``upgrade`` support.

    ``zb upgrade`` was added in ``0.3.0``. The ``outdated`` command and its
    ``--json`` output were already available in ``0.2.0``.
    """

    cli_names = ("zb",)

    cli_search_path = ("/opt/zerobrew/bin",)
    """Default macOS install location."""

    # Suppress terminal styling from the ``console`` Rust crate.
    extra_env: ClassVar = {"NO_COLOR": "1"}

    version_regexes = (r"zb\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ zb --version
        zb 0.3.0
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<package_version>\S+)$",
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ zb list
            jq 1.7.1
            wget 1.24.5
        """
        output = self.run_cli("list")

        for line in output.splitlines():
            match = self._INSTALLED_REGEXP.match(line)
            if match:
                yield self.package(
                    id=match.group("package_id"),
                    installed_version=match.group("package_version"),
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ zb outdated --json
            [
              {
                "name": "jq",
                "installed_versions": [
                  "1.7.1"
                ],
                "current_version": "1.7.2"
              }
            ]
        """
        output = self.run_cli("outdated", "--json")

        if output:
            for pkg_data in json.loads(output):
                installed = pkg_data.get("installed_versions", [])
                yield self.package(
                    id=pkg_data["name"],
                    installed_version=installed[0] if installed else None,
                    latest_version=pkg_data.get("current_version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ zb install jq
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generate the CLI to upgrade all packages.

        Called with no argument, ``zb upgrade`` upgrades every package that
        ``zb outdated`` would list.

        .. code-block:: shell-session

            $ zb upgrade
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generate the CLI to upgrade one package.

        .. code-block:: shell-session

            $ zb upgrade jq
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ zb uninstall jq
        """
        return self.run_cli("uninstall", package_id)
