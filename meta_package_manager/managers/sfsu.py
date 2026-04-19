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

from extra_platforms import WINDOWS

from ..base import PackageManager
from ..capabilities import Delegate, search_capabilities
from .scoop import Scoop

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

    # Mutating operations delegate to the Scoop CLI.
    _scoop = Delegate(Scoop)

    homepage_url = "https://github.com/winpax/sfsu"

    platforms = WINDOWS

    requirement = ">=1.16.0"

    post_args = ("--no-color",)

    version_regexes = (r"sfsu\s+(?P<version>\S+)",)
    """
    .. code-block:: pwsh-session

        > sfsu --version
        sfsu 1.17.2
        sprinkles 0.22.0 (crates.io published version)
        ...
    """

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

    install = _scoop.install
    upgrade_all_cli = _scoop.upgrade_all_cli
    upgrade_one_cli = _scoop.upgrade_one_cli
    remove = _scoop.remove

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
