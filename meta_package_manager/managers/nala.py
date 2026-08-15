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

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_ANSI_REGEXP = re.compile(r"\x1b\[[0-9;]*m")
"""Style sequences to strip before parsing.

Nala drops its colouring when its output is not a terminal, with one leak: the
branch describing a package that carries no description interpolates an italic
sequence directly instead of going through the helper that checks for a
terminal, so it is emitted even through a pipe.
"""

_BRANCH_PREFIXES = ("+--", "`--", "├──", "└──")
"""Openings of the two lines continuing a record, whichever glyphs are in play.

`LC_ALL=C` selects the ASCII pair, but the Unicode ones are matched too so a
record is never mistaken for a new one should that lever ever fail.
"""


class Nala(PackageManager):
    """Front-end to Debian's `apt`, driving `libapt-pkg` directly.

    Nala reaches the same archives `apt` does, adding a parallel downloader, a
    mirror-scoring fetcher and a transaction history it can roll back. It is
    wrapped on the same grounds as the AUR helpers that sit over `pacman`: a
    distinct tool with a vocabulary of its own, rather than a translation layer
    over another CLI. It shares dpkg's lock with the rest of that family, so
    mpm runs it serially against them.

    ```{important}
    Every invocation forces `LC_ALL=C`, and it is doing two jobs at once. Nala
    translates its own output at runtime, so a French host reports `est
    installé` where the parsers expect `is installed`; and it picks its tree
    glyphs from the encoding of its output stream. The same flag that pins the
    language to the untranslated strings also selects the ASCII glyphs, giving
    one stable shape to parse instead of a matrix of locale and encoding.
    ```

    ```{caution}
    A listing is a record of three lines, not a line per package: a header
    naming the package and its version, a branch giving its status, and another
    carrying its description. That is why this is a class rather than a
    declarative definition, and why `outdated` correlates two lines to pair an
    installed version with the candidate it can move to.
    ```

    ```{note}
    Nala's own `upgrade` takes no package arguments at all, accepting only
    exclusions, so naming a package cannot restrict it. Upgrading one package
    therefore goes through `install`, which moves an already-installed package
    to its candidate version, exactly as `apt` does.
    ```

    Documentation: [nala](https://gitlab.com/volian/nala).
    """

    name = "Nala"

    homepage_url = "https://gitlab.com/volian/nala"
    logo = "debian"

    platforms = LINUX_LIKE

    default_sudo = True
    """Nala checks for root and exits with a message rather than escalating on
    its own, so mpm supplies the privilege for the operations that mutate.
    """

    requirement = ">=0.12.2"
    """The oldest release still shipped by a supported distribution, and the
    floor from which the listing format is unchanged: its emitting code is
    byte-identical from there through the newest release.
    """

    extra_env: ClassVar = {
        # Pins the language to the untranslated strings the parsers below
        # expect, and selects the ASCII tree glyphs at the same time.
        "LC_ALL": "C",
    }

    version_regexes = (r"nala\s+(?P<version>\S+)",)
    r"""Search the version right after the `nala` string.

    ```{code-block} shell-session

    $ nala --version
    nala 0.16.0
    ```
    """

    _HEADER_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<installed_version>\S+)(?:\s+\[[^\]]*\])?\s*$",
    )
    """A record's first line: the package, its version, and an optional bracket
    naming the archive it came from. Anchored at both ends so a short
    description cannot be read as a package and a version.
    """

    _UPGRADABLE_REGEXP = re.compile(r"upgradable to\s+(?P<latest_version>\S+)")
    """The candidate version, named on the status branch of a record when the
    package has one to move to.
    """

    def _parse_records(self, output: str) -> Iterator[tuple[str, str, str | None]]:
        """Yield `(package_id, installed_version, latest_version)` per record.

        A record spans a header and the branches below it, so the header is
        held while its branches are read, and emitted once the record closes.
        """
        package_id: str | None = None
        installed_version: str | None = None
        latest_version: str | None = None

        def flush() -> Iterator[tuple[str, str, str | None]]:
            if package_id and installed_version:
                yield package_id, installed_version, latest_version

        for raw_line in output.splitlines():
            line = _ANSI_REGEXP.sub("", raw_line)
            stripped = line.strip()

            if stripped.startswith(_BRANCH_PREFIXES):
                match = self._UPGRADABLE_REGEXP.search(stripped)
                if match:
                    latest_version = match.group("latest_version")
                continue

            # Anything else closes the record being read, blank line or not.
            yield from flush()
            package_id = installed_version = latest_version = None

            header = self._HEADER_REGEXP.match(line)
            if header:
                package_id = header.group("package_id")
                installed_version = header.group("installed_version")

        yield from flush()

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ nala list --installed
        ```

        ```{code-block} console

        vim 2:8.2.3995-1+b2 [Debian/sid main]
        +-- is installed
        `-- Vi IMproved - enhanced vi editor
        ```
        """
        output = self.run_cli("list", "--installed")
        for package_id, installed_version, _latest in self._parse_records(output):
            yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        The two versions sit on different lines: the header carries the
        installed one, and the status branch names the candidate.

        ```{code-block} shell-session

        $ nala list --upgradable
        ```

        ```{code-block} console

        vim 2:8.2.3995-1+b2 [Debian/sid main]
        +-- is installed and upgradable to 2:8.2.4659-1
        `-- Vi IMproved - enhanced vi editor
        ```
        """
        output = self.run_cli("list", "--upgradable")
        for package_id, installed_version, latest_version in self._parse_records(
            output,
        ):
            if not latest_version:
                continue
            yield self.package(
                id=package_id,
                installed_version=installed_version,
                latest_version=latest_version,
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        The query is a regular expression as far as nala is concerned, so mpm's
        own refiltering narrows whatever comes back.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ nala search vim
        ```
        """
        output = self.run_cli("search", query)
        for package_id, version, _latest in self._parse_records(output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo nala install --assume-yes firefox
        ```
        """
        return self.run_cli("install", "--assume-yes", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ sudo nala upgrade --assume-yes
        ```
        """
        return self.build_cli("upgrade", "--assume-yes", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        Routed through `install`, since nala's own `upgrade` accepts no package
        arguments and would upgrade everything. Installing a package already
        present moves it to its candidate version.

        ```{code-block} shell-session

        $ sudo nala install --assume-yes firefox
        ```
        """
        return self.build_cli("install", "--assume-yes", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{code-block} shell-session

        $ sudo nala remove --assume-yes firefox
        ```
        """
        return self.run_cli("remove", "--assume-yes", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ sudo nala update
        ```
        """
        self.run_cli("update", sudo=True)

    def cleanup_orphan(self) -> None:
        """Removes packages nothing depends on anymore.

        ```{code-block} shell-session

        $ sudo nala autoremove --assume-yes
        ```
        """
        self.run_cli("autoremove", "--assume-yes", sudo=True)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        ```{code-block} shell-session

        $ sudo nala clean
        ```
        """
        self.run_cli("clean", sudo=True)
