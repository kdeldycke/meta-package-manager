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
from typing import ClassVar

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


DRY_RUN_UPDATES_FOUND = 17
"""Exit code `gext update --dry-run` uses to report that updates exist.

A dry run finding nothing exits `0`, and finding something raises `SystemExit(17)`
after printing its report, so neither is a failure. Anything else is.
"""


class Gext(PackageManager):
    """Manager of GNOME Shell extensions, from [extensions.gnome.org](https://extensions.gnome.org).

    ```{note}
    GNOME ships an official `gnome-extensions` tool, which is deliberately not
    what this wraps. That one installs from a local bundle and never reaches the
    extension registry, has no search, and offers no upgrade verb at all; its
    `list --updates` filters on a boolean carrying no available version, so it
    could not report an outdated package even in principle. `gext` reaches the
    registry, and every operation below rests on that.
    ```

    ```{caution}
    An extension is identified by its UUID (`caffeine@patapon.info`), which is
    what the listing reports and what every other operation accepts. The
    human-readable name printed beside it is decoration and is never a valid
    argument.
    ```

    ```{important}
    A running GNOME is required, whichever backend is in play. `gext` talks to
    GNOME Shell over D-Bus when a session is there and falls back to reading the
    filesystem otherwise, but even that fallback shells out to `gsettings` for
    the enabled-extension list, so a host without GNOME's schemas fails rather
    than reporting an empty inventory. `mpm` leaves the backend choice to `gext`
    rather than forcing one, so a desktop session and a plain shell each get the
    path that works there.
    ```

    ```{warning}
    The inventory forces `--all`. Left off, `gext list` reports only the
    *enabled* extensions, silently omitting every installed-but-disabled one:
    that is the tool's own default and it would make the inventory a lie rather
    than a shorter list.
    ```

    No `sync`: the registry is queried per operation and there is no index to
    refresh. No `cleanup`: nothing prunes anything.

    No escalation: extensions install under the user's own data directory.

    Documentation: [gnome-extensions-cli](https://github.com/essembeh/gnome-extensions-cli).
    """

    name = "GNOME Shell extensions"

    homepage_url = "https://github.com/essembeh/gnome-extensions-cli"
    logo = "gnome"

    platforms = UNIX_WITHOUT_MACOS

    requirement = ">=0.11.0"
    """The release every format below was captured from.

    The parser most likely tolerates the `0.10.x` series, whose output is not
    known to differ, but the floor tracks what was verified rather than what was
    assumed: the dry run's exit code in particular is load-bearing here and was
    only observed on this release.
    """

    cli_names = ("gext",)

    extra_env: ClassVar = {
        # gext strips its own styling when this is set, exactly as its
        # `--no-color` flag does, which keeps every parser below on plain text.
        "NO_COLOR": "1",
    }

    version_regexes = (r"^gext\s+(?P<version>\S+)$",)
    r"""Search the version right after the program name.

    ```{code-block} shell-session

    $ gext --version
    gext 0.11.0
    ```
    """

    _INSTALLED_REGEXP = re.compile(
        r"^[🔵⚪]\s+.+\s+\((?P<package_id>[^()\s]+)\)"
        r"\s+(?:v(?P<installed_version>\S+)\s+)?/(?:user|system)$",
    )
    """One installed extension.

    A dot marks the extension enabled or disabled, then its name, its UUID in
    parentheses, its version and the tree it lives in. The name is matched
    greedily so a name carrying its own parentheses keeps them, the UUID being
    the last parenthesized group on the line. The version is optional and its
    absence is rendered as an empty field rather than omitted, leaving the two
    spaces the pattern tolerates: an extension whose metadata carries no version
    is reported without one instead of being dropped.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^\[\d+\]\s+Found extension\s+.+\s+\((?P<package_id>[^()\s]+)\)"
        r"\s+v(?P<latest_version>\S+)\s+:\s+outdated$",
    )
    """One upgradable extension of the dry-run report.

    The version on this line is the one the registry offers, not the one
    installed, so it is read as the latest. Anchoring on the trailing marker is
    what separates it from the `up-to-date` and `not installed` lines the same
    loop prints, and the summary that follows lists bare UUIDs on indented lines
    that match nothing here.
    """

    _SEARCH_REGEXP = re.compile(
        r"^[🔵⚪]\s+\[\d+/\d+\]\s+.+\s+\((?P<package_id>[^()\s]+)\)$",
    )
    """One search hit.

    Results are multi-line records and only their first line is matched, the
    remainder being indented `key : value` pairs. No version is read: the
    registry's own version sits on one of those continuation lines, and a record
    that a single pattern cannot span is better reported without a version than
    stitched together by guesswork.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ gext list --all
        🔵 Dash to Dock (dash-to-dock@micxgx.gmail.com) v92 /user
        🔵 Version Free (no-version@example.org)  /user
        ⚪ Caffeine (caffeine@patapon.info) v58 /user
        ```
        """
        output = self.run_cli("list", "--all")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{important}
        The dry run exits `17` once it has something to report, so a non-zero
        exit is the *populated* answer here and `0` is the empty one. Only a
        third code means the check itself failed. The entry that failing exit
        records is discarded, this one being a result rather than an error.
        ```

        ```{caution}
        Only enabled extensions carrying a version are checked, which is `gext`'s
        own rule rather than a filter applied here: a disabled extension appears
        in the inventory above but never in this report.
        ```

        ```{code-block} shell-session

        $ gext update --dry-run
        [1] Found extension Caffeine (caffeine@patapon.info) v60 : outdated
        [2] Found extension Dash to Dock (dash-to-dock@micxgx.gmail.com) v105 : outdated

        📦 Extensions to update:
           caffeine@patapon.info
           dash-to-dock@micxgx.gmail.com
        ```
        """
        before = len(self.cli_errors)
        output = self.run_cli("update", "--dry-run")

        last = self._last_run
        if last is not None:
            code = last[0]
            if code not in (0, DRY_RUN_UPDATES_FOUND):
                return
            # The dry run reports through its exit code, so the entry a non-zero
            # one recorded is not a failure to carry into mpm's own error tally.
            del self.cli_errors[before:]

        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search supports neither extended nor exact matching: the registry decides
        what the query matches, so
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`
        narrows whatever comes back.
        ```

        ```{code-block} shell-session

        $ gext search caffeine
        ⚪ [1/6] Caffeine (caffeine@patapon.info)
           link : https://extensions.gnome.org/extension/517/caffeine/
           screenshot : https://extensions.gnome.org/extension-data/screenshots/screenshot_517.png
           creator : eon
        ```
        """
        output = self.run_cli("search", query)
        yield from self.parse_regex_lines(self._SEARCH_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `gext` picks the release matching the running GNOME Shell on its own, so
        there is no version to pin.

        ```{code-block} shell-session

        $ gext install caffeine@patapon.info
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `--yes` answers the single confirmation `update` asks before applying;
        without it the command blocks on a prompt.

        ```{code-block} shell-session

        $ gext update --yes
        ```
        """
        return self.build_cli("update", "--yes")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Naming an extension genuinely restricts the run to it.

        ```{code-block} shell-session

        $ gext update --yes caffeine@patapon.info
        ```
        """
        return self.build_cli("update", "--yes", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{code-block} shell-session

        $ gext uninstall caffeine@patapon.info
        ```
        """
        return self.run_cli("uninstall", package_id)
