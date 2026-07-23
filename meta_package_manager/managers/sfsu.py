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

from extra_platforms import WINDOWS

from ..capabilities import Delegate, search_capabilities
from ..manager import PackageManager
from .scoop import Scoop

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class SFSU(PackageManager):
    """sfsu (Scoop For Speed and Usability) is a Rust reimplementation of
    Scoop's slower read paths, working against the same buckets and `~/scoop`
    install tree.

    mpm reaches for sfsu only where it is both faster than Scoop and speaks
    JSON: `installed`, `outdated` and `search` all pass `--json` and are
    parsed as structured objects instead of the whitespace tables Scoop prints.

    ```{note}
    sfsu implements no mutating verbs, so `install`, `remove` and both
    upgrade commands are bound straight to
    {class}`~meta_package_manager.managers.scoop.Scoop` through the
    {class}`~meta_package_manager.capabilities.Delegate` descriptor: those
    operations run the `scoop` binary, and a host with sfsu but no Scoop
    cannot mutate anything.
    ```
    """

    # Mutating operations delegate to the Scoop CLI.
    _scoop = Delegate(Scoop)

    name = "Scoop sfsu"

    homepage_url = "https://github.com/winpax/sfsu"

    platforms = WINDOWS

    requirement = ">=1.16.0"

    post_args = ("--no-color",)

    version_regexes = (r"sfsu\s+(?P<version>\S+)",)
    """
    ```{code-block} pwsh-session

    > sfsu --version
    sfsu 1.17.2
    sprinkles 0.22.0 (crates.io published version)
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} pwsh-session

        > sfsu list --json
        [
          {
            "name": "7zip",
            "version": "26.00",
            "source": "main",
            "updated": "2026-03-18 17:54:32",
            "notes": ""
          },
          {
            "name": "git",
            "version": "2.53.0.3",
            "source": "main",
            "updated": "2026-03-15 09:12:04",
            "notes": ""
          }
        ]
        ```
        """
        output = self.run_cli("list", "--json")
        yield from self.parse_json_items(
            output,
            fields={"package_id": "name", "installed_version": "version"},
        )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Uses `sfsu status --only apps --json` which returns packages with
        available updates.

        ```{code-block} pwsh-session

        > sfsu status --only apps --json
        {
          "packages": [
            {
              "name": "git",
              "current": "2.53.0.2",
              "available": "2.53.0.3",
              "missing_dependencies": [],
              "info": null
            }
          ]
        }
        ```
        """
        output = self.run_cli("status", "--only", "apps", "--json")
        yield from self.parse_json_items(
            output,
            list_path="packages",
            fields={
                "package_id": "name",
                "installed_version": "current",
                "latest_version": "available",
            },
        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching. Results are
        refiltered by
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`.
        ```

        ```{code-block} pwsh-session

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
        ```
        """
        output = self.run_cli("search", "--json", query)
        data = self.parse_json(output)
        if data:
            # Results are grouped by bucket name.
            for packages in data.values():
                for pkg in packages:
                    yield self.package(
                        id=pkg["name"],
                        latest_version=pkg["version"],
                    )

    install = _scoop.install
    upgrade_all_cli = _scoop.upgrade_all_cli
    upgrade_one_cli = _scoop.upgrade_one_cli
    remove = _scoop.remove

    def sync(self) -> None:
        """Sync package metadata.

        Uses sfsu's native `update` command which updates Scoop and all
        buckets.

        ```{code-block} pwsh-session

        > sfsu update --no-color
        ```
        """
        self.run_cli("update")

    def cleanup_cache(self) -> None:
        """Removes old versions of all installed apps and clears the cache.

        ```{code-block} pwsh-session

        > sfsu cleanup --all --cache --no-color
        ```
        """
        self.run_cli("cleanup", "--all", "--cache")
