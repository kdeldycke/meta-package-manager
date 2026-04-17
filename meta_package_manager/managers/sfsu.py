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
"""sfsu (Scoop For Speed and Usability) is a fast Rust-based replacement for
slow Scoop operations.

It leverages the same Scoop package ecosystem but provides native JSON output
and significantly faster execution for listing, searching, and status checks.
Install and upgrade operations are delegated to Scoop.
"""

from __future__ import annotations

import json
from functools import cached_property

from extra_platforms import WINDOWS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class SFSU(PackageManager):
    """sfsu wraps the Scoop package ecosystem with a fast Rust implementation.

    Read-only operations (list, search, outdated) use sfsu with ``--json`` for
    structured output. Mutating operations (install, upgrade, remove) delegate
    to ``scoop`` because sfsu does not implement them.
    """

    homepage_url = "https://github.com/winpax/sfsu"

    platforms = WINDOWS

    requirement = ">=1.16.0"

    version_regexes = (r"sfsu\s+(?P<version>\S+)",)
    """
    .. code-block:: pwsh-session

        > sfsu --version
        sfsu 1.17.2
        sprinkles 0.22.0 (crates.io published version)
        ...
    """

    post_args = ("--no-color",)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: pwsh-session

            > sfsu list --json
            [
              {
                "name": "7zip",
                "version": "26.00",
                "source": "main",
                "updated": "2026-03-18 17:54:32",
                "notes": ""
              },
              ...
            ]
        """
        output = self.run_cli("list", "--json")
        if output:
            for pkg in json.loads(output):
                yield self.package(
                    id=pkg["name"],
                    name=pkg["name"],
                    installed_version=pkg["version"],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Uses ``sfsu status --only apps --json`` which returns packages with
        available updates.

        .. code-block:: pwsh-session

            > sfsu status --only apps --json
            {
              "packages": [
                {
                  "name": "git",
                  "current": "2.53.0.2",
                  "available": "2.53.0.3",
                  "missing_dependencies": [],
                  "info": null
                },
                ...
              ]
            }
        """
        output = self.run_cli("status", "--only", "apps", "--json")
        if output:
            data = json.loads(output)
            for pkg in data.get("packages", []):
                yield self.package(
                    id=pkg["name"],
                    name=pkg["name"],
                    installed_version=pkg["current"],
                    latest_version=pkg["available"],
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. Results are
            refiltered by
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`.

        .. code-block:: pwsh-session

            > sfsu search --json git
            {
              "main": [
                {
                  "name": "git",
                  "bucket": "main",
                  "version": "2.53.0.3",
                  "installed": true,
                  "bins": []
                },
                ...
              ],
              ...
            }
        """
        output = self.run_cli("search", "--json", query)
        if output:
            data = json.loads(output)
            # Results are grouped by bucket name.
            for packages in data.values():
                for pkg in packages:
                    yield self.package(
                        id=pkg["name"],
                        name=pkg["name"],
                        latest_version=pkg["version"],
                    )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        Delegates to ``scoop install`` because sfsu does not implement
        install.

        .. code-block:: pwsh-session

            > scoop install 7zip
        """
        return self.run_cli(
            "install",
            package_id,
            override_cli_path=self._scoop_path,
            auto_post_args=False,
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        Delegates to ``scoop update --all``.

        .. code-block:: pwsh-session

            > scoop update --all
        """
        return self.build_cli(
            "update",
            "--all",
            override_cli_path=self._scoop_path,
            auto_post_args=False,
        )

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        Delegates to ``scoop update <package_id>``.

        .. code-block:: pwsh-session

            > scoop update 7zip
        """
        return self.build_cli(
            "update",
            package_id,
            override_cli_path=self._scoop_path,
            auto_post_args=False,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        Delegates to ``scoop uninstall <package_id> --purge``.

        .. code-block:: pwsh-session

            > scoop uninstall 7zip --purge
        """
        return self.run_cli(
            "uninstall",
            package_id,
            "--purge",
            override_cli_path=self._scoop_path,
            auto_post_args=False,
        )

    def sync(self) -> None:
        """Sync package metadata.

        Uses sfsu's native ``update`` command which updates Scoop and all
        buckets.

        .. code-block:: pwsh-session

            > sfsu update
        """
        self.run_cli("update")

    def cleanup(self) -> None:
        """Removes old versions of all installed apps and clears the cache.

        .. code-block:: pwsh-session

            > sfsu cleanup --all --cache
        """
        self.run_cli("cleanup", "--all", "--cache")

    @cached_property
    def _scoop_path(self):
        """Resolves the path to the ``scoop`` CLI.

        Scoop is required for mutating operations (install, upgrade, remove)
        that sfsu does not implement.
        """
        return self.which("scoop")
