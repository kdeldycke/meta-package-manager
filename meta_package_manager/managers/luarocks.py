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

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ..package import Package


class LuaRocks(PackageManager):
    """LuaRocks, the package manager for Lua modules.

    A package is a *rock*, identified by the bare name every listing prints. Its
    version carries a packaging revision after a dash (`3.1.2-0`), kept verbatim
    because that is the form `luarocks install` accepts back.

    ```{note}
    Every read passes `--porcelain`, which replaces the default grouped display
    with one tab-separated record per line.
    ```

    ```{note}
    Search is what makes this a class rather than a bundled definition.
    `luarocks search` prints one row per *(rock, version, kind)* triple, so a
    single rock comes back a dozen times over: once per published version, and
    again for each of the `rockspec` and `src` forms it ships in. mpm keys a
    package on its id alone, so the rows are reduced here to one entry per rock.
    The installed and outdated listings get the same treatment, LuaRocks being
    able to hold several versions of a rock in one tree.
    ```

    ```{caution}
    `--no-project` is load-bearing. LuaRocks walks up from the working directory
    looking for a project tree and silently switches to it when one is found, so
    without the flag the inventory would answer for whichever directory mpm
    happened to be invoked from instead of for the machine. `haxelib` forces
    `--global` against the same hazard.

    The flag is a global one, placed before the subcommand, which is why it is
    declared as {attr}`pre_args` rather than repeated per operation. The version
    probe skips `pre_args` entirely and so runs bare.
    ```

    ```{caution}
    Reads and writes disagree about scope, and deliberately so. `list` reports
    every configured tree at once, which is the right answer for an inventory of
    the machine: the system tree and the user's `~/.luarocks` both show up, each
    row naming the tree holding it. `install` and `remove` act on one tree only,
    the default one, so removing a rock that lives in the *other* tree fails
    with `Error: Could not find rock 'say' in /opt/homebrew`.

    That asymmetry is left as LuaRocks defines it rather than papered over.
    Forcing `--local` would make the user tree writable at the cost of the
    system one, and forcing `--global` the reverse; neither is right for every
    host, and the failure is loud, immediate and names the tree it searched.
    ```

    ```{note}
    No `upgrade --all`: LuaRocks has no command updating every installed rock,
    `install` being what upgrades a named one in place. mpm backfills the bulk
    case from `outdated` plus the per-rock upgrade.

    No `sync` either, nothing refreshing the manifest without also downloading,
    and no `cleanup`: `luarocks purge` empties an entire tree rather than
    reclaiming anything, which is a mass removal and not a cleanup.
    ```

    Documentation: [LuaRocks documentation](https://github.com/luarocks/luarocks/wiki/Documentation).
    """

    name = "LuaRocks"

    homepage_url = "https://luarocks.org"

    platforms = ALL_PLATFORMS

    requirement = ">=3.9.1"
    """The release adding `--no-project`, which is what pins every read to the
    machine instead of to the working directory's project tree.
    """

    pre_args = ("--no-project",)
    """Ignore any project tree found by walking up from the working directory,
    so the inventory describes the machine and not the current directory.
    """

    version_regexes = (r"luarocks(?:\.exe)?[ \t]+(?P<version>\d+\.\d+(?:\.\d+)?)",)
    r"""Search the version right after the binary path LuaRocks echoes back.

    ```{code-block} shell-session

    $ luarocks --version
    /opt/homebrew/bin/luarocks 3.13.0
    LuaRocks main command-line interface
    ```

    The path is printed in full and varies per host, so the pattern anchors on
    the binary name rather than on the start of the line.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>[^\t]+)\t(?P<installed_version>[^\t]+)\tinstalled\t",
    )
    """One installed rock: name, version, the literal `installed` state, then the
    tree holding it. The state column is matched so a row of any other kind is
    skipped rather than misread.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>[^\t]+)\t(?P<installed_version>[^\t]+)\t"
        r"(?P<latest_version>[^\t]+)\t",
    )
    """One upgradable rock: name, the version held, the version available, then
    the server offering it.
    """

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>[^\t]+)\t(?P<latest_version>[^\t]+)\t",
    )
    """One search hit: name and version. The kind and server columns are dropped,
    being what makes the same rock repeat across rows.
    """

    def _newest_per_rock(
        self,
        rows: Iterable[tuple[str, str | None, str | None]],
    ) -> Iterator[Package]:
        """Reduce rows to one package per rock, keeping the highest version.

        LuaRocks repeats a rock across rows, by installed version in a listing
        and by published version and packaging kind in a search. Ranking is done
        on whichever version the row carries: the installed one where there is
        one, the available one otherwise.
        """
        best: dict[str, tuple[str | None, str | None]] = {}
        for package_id, installed, latest in rows:
            ranked = installed or latest
            current = best.get(package_id)
            if current is not None:
                current_ranked = current[0] or current[1]
                if ranked is None or (
                    current_ranked is not None
                    and parse_version(ranked) <= parse_version(current_ranked)
                ):
                    continue
            best[package_id] = (installed, latest)
        for package_id, (installed, latest) in best.items():
            yield self.package(
                id=package_id,
                installed_version=installed,
                latest_version=latest,
            )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ luarocks --no-project list --porcelain
        inspect	3.1.2-0	installed	/Users/kde/.luarocks/lib/luarocks/rocks-5.5
        say	1.4.1-3	installed	/Users/kde/.luarocks/lib/luarocks/rocks-5.5
        ```
        """
        output = self.run_cli("list", "--porcelain")
        yield from self._newest_per_rock(
            (match.group("package_id"), match.group("installed_version"), None)
            for match in map(self._INSTALLED_REGEXP.match, output.splitlines())
            if match
        )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{code-block} shell-session

        $ luarocks --no-project list --outdated --porcelain
        inspect	3.1.2-0	3.1.3-0	https://luarocks.org
        ```
        """
        output = self.run_cli("list", "--outdated", "--porcelain")
        yield from self._newest_per_rock(
            (
                match.group("package_id"),
                match.group("installed_version"),
                match.group("latest_version"),
            )
            for match in map(self._OUTDATED_REGEXP.match, output.splitlines())
            if match
        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ luarocks --no-project search say --porcelain
        say	1.4.1-3	rockspec	https://luarocks.org
        say	1.4.1-3	src	https://luarocks.org
        say	1.4.0-1	rockspec	https://luarocks.org
        say	1.4.0-1	src	https://luarocks.org
        say	1.3-1	rockspec	https://luarocks.org
        ```
        """
        output = self.run_cli("search", query, "--porcelain")
        yield from self._newest_per_rock(
            (match.group("package_id"), None, match.group("latest_version"))
            for match in map(self._SEARCH_REGEXP.match, output.splitlines())
            if match
        )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ luarocks --no-project install inspect
        inspect 3.1.3-0 depends on lua >= 5.1 (5.5-1 provided by VM: success)
        No existing manifest. Attempting to rebuild...
        inspect 3.1.3-0 is now installed in /opt/homebrew (license: MIT <http://opensource.org/licenses/MIT>)
        ```
        """
        spec = (package_id,) if version is None else (package_id, version)
        return self.run_cli("install", *spec)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generate the CLI to upgrade one package.

        LuaRocks has no `upgrade` verb: installing a rock that is already
        present replaces it with the newer build, which is the upgrade.

        ```{code-block} shell-session

        $ luarocks --no-project install inspect
        inspect 3.1.3-0 depends on lua >= 5.1 (5.5-1 provided by VM: success)
        No existing manifest. Attempting to rebuild...
        inspect 3.1.3-0 is now installed in /opt/homebrew (license: MIT <http://opensource.org/licenses/MIT>)
        ```
        """
        spec = (package_id,) if version is None else (package_id, version)
        return self.build_cli("install", *spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        Acts on the default tree, so a rock held in another one is refused by
        name rather than removed, as covered in the class notes above.

        ```{code-block} shell-session

        $ luarocks --no-project remove inspect
        Checking stability of dependencies in the absence of
        inspect 3.1.3-0...

        Removing inspect 3.1.3-0...
        Removal successful.
        ```
        """
        return self.run_cli("remove", package_id)
