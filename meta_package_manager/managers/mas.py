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

from extra_platforms import MACOS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class MAS(PackageManager):
    name = "Mac AppStore"

    homepage_url = "https://github.com/mas-cli/mas"

    platforms = MACOS

    requirement = ">=7.0.0"
    """`7.0.0 <https://github.com/mas-cli/mas/releases/tag/v7.0.0>`_ introduces
    the ``--json`` flag on ``config``, ``list``, ``lookup``/``info``,
    ``outdated`` & ``search``. Parsing structured JSON output is the supported
    programmatic interface: it sidesteps the column-alignment ambiguities of
    the tabular output (app names containing parentheses or extra whitespace
    would break the previous regex-based parser).
    """

    version_cli_options = ("version",)
    """
    .. code-block:: shell-session

        $ mas version
        7.0.0
    """

    @staticmethod
    def _parse_json_stream(output: str) -> Iterator[dict]:
        """Parse mas ``--json`` output as a stream of newline-delimited JSON
        objects, one per app.
        """
        for line in output.splitlines():
            if line.strip():
                yield json.loads(line)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ mas list --json
            {"adamID":1569813296,"bundleID":"com.1password.1password-safari","name":"1Password for Safari","version":"2.3.5",...}
            {"adamID":1295203466,"bundleID":"com.microsoft.rdc.macos","name":"Microsoft Remote Desktop","version":"10.7.6",...}
            {"adamID":409183694,"bundleID":"com.apple.iWork.Keynote","name":"Keynote","version":"12.0",...}
        """
        output = self.run_cli("list", "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                installed_version=app["version"],
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ mas outdated --json
            {"adamID":409183694,"name":"Keynote","newVersion":"12.0","version":"11.0",...}
            {"adamID":1176895641,"name":"Spark","newVersion":"2.11.21","version":"2.11.20",...}
        """
        output = self.run_cli("outdated", "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                installed_version=app["version"],
                latest_version=app["newVersion"],
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best
            subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine
            them.

        .. code-block:: shell-session

            $ mas search python --json
            {"adamID":689176796,"name":"Python Runner","version":"1.3",...}
            {"adamID":630736088,"name":"Learning Python","version":"1.0",...}
            {"adamID":945397020,"name":"Run Python","version":"1.0",...}
            {"adamID":1164498373,"name":"PythonGames","version":"1.0",...}
            {"adamID":1400050251,"name":"Pythonic","version":"1.0.0",...}
        """
        output = self.run_cli("search", query, "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                latest_version=app["version"],
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ mas install 945397020
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ mas upgrade
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ mas upgrade 945397020
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        .. code-block:: shell-session

            $ sudo mas uninstall 1494051017
            Password:
            Deleted '/Applications/SimpleLogin.app' to '/Users/kde/.Trash/SimpleLogin.app'
        """
        return self.run_cli("uninstall", package_id, sudo=True)
