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

from typing import ClassVar

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Antigravity_CLI_Plugins(PackageManager):
    """The plugins of the Antigravity CLI, `agy`.

    A package is a plugin of the user's profile, identified by the `name` its
    `plugin.json` declares, and stored under `~/.gemini/config/plugins`. Plugins a
    project keeps in its own `.agents/plugins` directory are not reported: the
    listing covers the profile alone, whatever the working directory.

    `install` takes a local plugin directory, or `<plugin>@<marketplace>` for a
    marketplace the Antigravity application registered: the command line has no
    way to add one, and no search. The plugin is then listed under its `name`.

    The CLI itself updates with `agy update`, which is not a plugin operation and
    is left to [`topgrade`](topgrade.md).
    """

    # `agy plugin enable` and `disable` toggle a plugin without removing it, and
    # map onto no mpm operation. The listing does not report that state either.

    operation_notes: ClassVar = {
        "installed": "Listings carry plugin names only, with no version.",
        "outdated": "No command reports a newer plugin.",
        "search": (
            "No catalog is reachable from the command line: marketplaces are "
            "browsed in the Antigravity application."
        ),
        "upgrade": "No update command: the Antigravity application updates plugins.",
        "upgrade_all": "No update command: the Antigravity application updates plugins.",
    }

    name = "Antigravity CLI plugins"

    homepage_url = "https://antigravity.google/product/antigravity-cli"
    documentation_url = "https://antigravity.google/docs/plugins?tab=cli"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=1.2.14"
    """The release this wrapper was driven against. The changelog dates none of
    the `plugin` commands, so earlier releases are unverified.
    """

    cli_names = ("agy",)

    version_regexes = (r"^(?P<version>\d+\.\d+\.\d+)",)
    """The bare version, alone on its line.

    ```{code-block} shell-session

    $ agy --version
    1.2.14
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        The listing is a JSON document, except with no plugin at all, where it
        prints `No imported plugins.` instead of an empty array.

        ```{code-block} shell-session

        $ agy plugin list
        {
          "imports": [
            {
              "name": "apricot-notes",
              "source": "antigravity",
              "importedAt": "2026-09-30T09:08:27Z",
              "components": null
            }
          ]
        }
        ```
        """
        output = self.run_cli("plugin", "list")
        if output.strip() == "No imported plugins.":
            return
        yield from self.parse_json_items(
            output,
            list_path="imports",
            fields={"package_id": "name"},
        )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ agy plugin install ~/plugins/apricot-notes
        ```
        """
        return self.run_cli("plugin", "install", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{caution}
        `agy` reports the removal of a plugin it never had.
        ```

        ```{code-block} shell-session

        $ agy plugin uninstall apricot-notes
        Uninstalled plugin "apricot-notes"
        ```
        """
        return self.run_cli("plugin", "uninstall", package_id)
