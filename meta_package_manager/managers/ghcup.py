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

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_SELF_TOOL = "ghcup"
"""The one row of ghcup's own inventory that cannot be addressed as a package.

`ghcup list` reports the running ghcup among the installed tools, but its
argument parser rejects the name outright, with `'ghcup' is not a valid tool in
this context`, so the row round-trips through neither `install` nor `rm`. It is
dropped from the inventory rather than offered as a package mpm cannot act on.
"""

_UNAVAILABLE_NOTE = "no-bindist"
"""Note marking a version with no binary distribution for the running platform.

Such a row is a real release, listed because the metadata knows it, but nothing
`ghcup install` can fetch here. Kept out of search results, which exist to name
things the user can then install.
"""


class GHCup(PackageManager):
    """Haskell toolchain installer, covering GHC and the tools built around it.

    ghcup installs several kinds of tool side by side: GHC itself, plus
    `cabal`, `hls`, `stack` and whatever else its metadata offers. All of them
    are packages here, because `ghcup list` reports every kind in one flat
    listing whose every line names its own kind, and because `install`, `rm`,
    `set` and `whereis` all take the same `<tool> <version>` pair. Reporting
    only GHC versions would hide from the inventory tools mpm remains perfectly
    able to install and remove.

    A package is therefore identified as `<tool>-<version>`, and split back on
    its **first** hyphen to rebuild the pair. First rather than last is
    load-bearing: a cross-compiling GHC renders its target into the version
    cell, so `ghc-aarch64-unknown-linux-gnu-9.4.8` has to split into `ghc` and
    `aarch64-unknown-linux-gnu-9.4.8`, and that remainder is exactly the token
    ghcup's own version parser accepts. No tool name contains a hyphen today.

    ```{note}
    Every listing forces `--show-revisions none`. ghcup otherwise appends a
    `-rN` metadata-revision suffix to versions that have one, and that suffixed
    string is not a version `ghcup rm` will match: the inventory would then
    report packages that cannot be removed. The suffix appears only while a
    revision is pending, so the corruption is intermittent, which is worse than
    a consistent one.
    ```

    ```{caution}
    Neither upgrade operation is declared, and neither is an oversight.
    `ghcup upgrade` upgrades **the ghcup binary itself**, not the tools it
    installs, so mapping it onto `upgrade --all` would replace the user's
    package manager when they asked to upgrade their packages. And ghcup has no
    in-place upgrade for a tool at all: a newer GHC is a fresh side-by-side
    install that leaves the old one in place, which is what `install` already
    does.
    ```

    ```{note}
    No `outdated` either, for a reason that follows from the package identity
    above rather than from any missing command. Since the version is part of
    the id, a package having a newer version is a contradiction: the newer
    version is a *different* package, installed alongside rather than over. A
    report pairing `ghc-9.6.7` with a latest of `9.10.1` would also name an
    upgrade mpm cannot perform, both upgrade operations being absent. ghcup's
    own new-version notice is no help here: it is prose on stderr, it
    deduplicates itself against a cache file so a second run prints nothing,
    and it fires as a side effect of unrelated commands.
    ```

    Documentation: [ghcup user guide](https://www.haskell.org/ghcup/guide/).
    """

    name = "Haskell ghcup"

    homepage_url = "https://www.haskell.org/ghcup/"
    logo = "haskell"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=0.2.1.0"
    """First release accepting `--show-revisions`, which every listing needs to
    keep the `-rN` suffix out of versions that must round-trip to `ghcup rm`.

    Higher than the release the parsers themselves would need, and deliberately
    so: ghcup is installed by its own bootstrap script and upgrades itself
    rather than being carried by distributions, so a recent floor costs little.
    """

    extra_env: ClassVar = {
        # The only color switch ghcup honors: it reads the variable's presence,
        # offers no --no-color flag, and performs no TTY detection at all, so a
        # piped run is colored too.
        "NO_COLOR": "1",
        # Silences the new-version notice ghcup prints to stderr after mutating
        # commands, which is chatter mpm never parses.
        "GHCUP_SKIP_UPDATE_CHECK": "1",
    }

    version_cli_options = ("--numeric-version",)
    """Preferred over `--version`, which wraps the number in a sentence and
    interpolates a build-time git description. This prints the bare version.
    """

    version_regexes = (r"^(?P<version>\d+(?:\.\d+)+)",)
    r"""Search the bare version this option prints on its own.

    ```{code-block} shell-session

    $ ghcup --numeric-version
    0.2.6.2
    ```
    """

    @staticmethod
    def _parse_row(line: str) -> tuple[str, str, str] | None:
        """Split one `--raw-format` row into tool, version and notes.

        Raw rows are the four cells joined with single spaces and no padding,
        so an empty cell shows up as two spaces in a row. Splitting on a single
        space keeps those empties in place, where splitting on runs of
        whitespace would collapse them and shift every later cell left, landing
        a note in the tags column.
        """
        cells = line.split(" ", 3)
        if len(cells) < 2:
            return None
        tool, version = cells[0], cells[1]
        if not tool or not version:
            return None
        notes = cells[3] if len(cells) > 3 else ""
        return tool, version, notes

    def _package_id(self, tool: str, version: str) -> str:
        """Join a tool and version into the id mpm keys the package on."""
        return f"{tool}-{version}"

    @staticmethod
    def split_package_id(package_id: str) -> tuple[str, str]:
        """Split a package id back into the `<tool> <version>` pair ghcup takes.

        Splits on the first hyphen, which is what keeps a cross-compiling GHC
        intact: its target triple lives in the version cell, so everything after
        the tool name belongs to the version.
        """
        tool, _, version = package_id.partition("-")
        return tool, version

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `--show-criteria installed` filters upstream, so the installed marker
        never has to be read back off the glyph column, which `--raw-format`
        drops anyway.

        ```{code-block} shell-session

        $ ghcup list --raw-format --show-revisions none --show-criteria installed
        cabal 3.14.2.0 recommended
        ghc 9.6.7 recommended,base-4.18.3.0
        ghcup 0.2.6.2  stray
        ```
        """
        output = self.run_cli(
            "list",
            "--raw-format",
            "--show-revisions",
            "none",
            "--show-criteria",
            "installed",
        )
        for line in output.splitlines():
            row = self._parse_row(line)
            if not row:
                continue
            tool, version, _notes = row
            if tool == _SELF_TOOL:
                continue
            yield self.package(
                id=self._package_id(tool, version),
                installed_version=version,
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ghcup has no search command: the full listing *is* its catalog, and a
        small one, so mpm filters it itself.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ ghcup list --raw-format --show-revisions none
        cabal 3.14.2.0 recommended
        ghc 9.6.7 recommended,base-4.18.3.0
        ghc 9.8.1  2023-10-09
        ```
        """
        output = self.run_cli("list", "--raw-format", "--show-revisions", "none")
        for line in output.splitlines():
            row = self._parse_row(line)
            if not row:
                continue
            tool, version, notes = row
            # The self row is not installable, and a version with no binary
            # distribution for this platform cannot be fetched here.
            if tool == _SELF_TOOL or _UNAVAILABLE_NOTE in notes.split(","):
                continue
            yield self.package(
                id=self._package_id(tool, version),
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        The version is already carried by the id, which is why this takes no
        version of its own.

        ```{code-block} shell-session

        $ ghcup install ghc 9.6.7
        ```
        """
        tool, tool_version = self.split_package_id(package_id)
        return self.run_cli("install", tool, tool_version)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        Removing the version currently set neither fails nor warns: ghcup drops
        the symlinks and the set marker, leaving the tool simply unset.

        ```{code-block} shell-session

        $ ghcup rm ghc 9.6.7
        ```
        """
        tool, tool_version = self.split_package_id(package_id)
        return self.run_cli("rm", tool, tool_version)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ ghcup prefetch metadata
        ```
        """
        self.run_cli("prefetch", "metadata")

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        Confined to the download cache and the temporary directories. `ghcup
        gc` also offers switches that delete installed tools, which is not
        cleanup as mpm means it, and they are deliberately not passed.

        ```{code-block} shell-session

        $ ghcup gc --cache --tmpdirs
        ```
        """
        self.run_cli("gc", "--cache", "--tmpdirs")
