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
    from collections.abc import Iterator

    from ..package import Package


class Nimble(PackageManager):
    """Nimble, the package manager of the Nim language.

    A package is a Nim library or binary, identified by the bare name the
    registry publishes it under.

    ```{caution}
    The inventory forces `--ver`, and that flag is the whole difference between
    a useful listing and a misleading one. Without it `nimble list --installed`
    prints package names and nothing else, so every package would be reported
    with no version at all while looking perfectly healthy. Upstream tracked the
    flag being ignored as
    [nim-lang/nimble#1469](https://github.com/nim-lang/nimble/issues/1469),
    closed as completed; the fix is what sets the requirement floor below.
    ```

    ```{note}
    Both listings open with a three-line legend describing the format, whose
    own lines look exactly like the records that follow: a `{PackageName}`
    placeholder where a name goes, and a `└── @{Version} (...)` placeholder
    where a version goes. Both parsers therefore demand a *real* value, refusing
    the brace-wrapped placeholders, rather than skipping a fixed number of
    header lines that a future release could renumber.
    ```

    ```{note}
    Records span two lines, a name followed by one indented line per version
    held, which is what makes this a class rather than a bundled definition.
    Nimble keeps several versions of a package side by side, so the versions are
    reduced here to the newest per name.
    ```

    ```{note}
    No `outdated`: Nimble has no command reporting which installed packages have
    newer releases.

    No upgrade either, and that is a deliberate reading rather than an
    oversight. `nimble upgrade` is documented as upgrading "*a list of packages
    in the lock file*", which is a project operation on a `nimble.lock` and not
    something that acts on the machine. Installing a package again does fetch
    the newest release, but Nimble adds it *beside* the version already held
    rather than replacing it, so reporting that as an upgrade would misstate
    what happened.
    ```

    Documentation: [Nimble README](https://github.com/nim-lang/nimble#readme).
    """

    name = "Nimble"

    homepage_url = "https://github.com/nim-lang/nimble"

    platforms = ALL_PLATFORMS

    requirement = ">=0.22.0"
    """First release carrying the fix that makes `list --installed --ver` print
    versions: [nim-lang/nimble#1469](https://github.com/nim-lang/nimble/issues/1469)
    was closed on 2025-09-18, between `v0.20.1` and `v0.22.0`.
    """

    pre_args = ("--noColor", "--accept")
    """Strip styling so the parsers see plain text, and pre-answer the prompts.

    `--accept` is not cosmetic: `uninstall` asks *"Do you wish to continue?"* and
    blocks forever without it.
    """

    version_regexes = (r"nimble[ \t]+v(?P<version>\S+)",)
    r"""Search the version right after the `nimble v` string.

    ```{code-block} shell-session

    $ nimble --version
    nimble v0.22.2 compiled at 2026-04-24 03:34:24
    git hash: couldn't determine git hash
    ```
    """

    _INSTALLED_NAME_REGEXP = re.compile(r"^(?P<package_id>[A-Za-z0-9][\w.-]*)$")
    """A package name, alone on its line. Anchored on an alphanumeric first
    character so the legend's `{PackageName}` placeholder cannot match.
    """

    _INSTALLED_VERSION_REGEXP = re.compile(
        r"^[├└]──[ \t]+@(?P<installed_version>[^\s{(]+)[ \t]+\(",
    )
    """One version of the package named on the line above. The excluded brace
    keeps the legend's `@{Version}` placeholder from matching.

    Both branch glyphs are accepted, and that matters: Nimble draws `└──` when a
    package holds a single version and switches to `├──` for every version but
    the last as soon as it holds several. Matching `└──` alone silently reports
    the *oldest* of a multi-version package, which reads as correct right up
    until a second version is installed.
    """

    _SEARCH_NAME_REGEXP = re.compile(r"^(?P<package_id>[A-Za-z0-9][\w.-]*):$")
    """A search hit's name, which opens its record with a trailing colon."""

    _SEARCH_DESCRIPTION_REGEXP = re.compile(
        r"^[ \t]+description:[ \t]+(?P<description>.+)$",
    )
    """The one field of a search record mpm keeps besides the name. Nimble
    reports no version in search results at all.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ nimble --noColor --accept list --installed --ver
        Package list format:
        {PackageName}
        └── @{Version} ({CheckSum})[Special Versions (if any)] ({InstallPath})
        parsetoml
        ├── @0.7.2 (2a9fb57ef1f6460fd61b1cfab2d83af44f788a25) (/Users/kde/.nimble/pkgs2/parsetoml-0.7.2-2a9fb57ef1f6460fd61b1cfab2d83af44f788a25)
        └── @0.7.1 (586fe63467a674008c4445ed1b8ac882177d7103) (/Users/kde/.nimble/pkgs2/parsetoml-0.7.1-586fe63467a674008c4445ed1b8ac882177d7103)
        ```
        """
        output = self.run_cli("list", "--installed", "--ver")

        newest: dict[str, str] = {}
        package_id = None
        for line in output.splitlines():
            name_match = self._INSTALLED_NAME_REGEXP.match(line)
            if name_match:
                package_id = name_match.group("package_id")
                continue
            version_match = self._INSTALLED_VERSION_REGEXP.match(line)
            if version_match and package_id:
                version = version_match.group("installed_version")
                held = newest.get(package_id)
                if held is None or parse_version(version) > parse_version(held):
                    newest[package_id] = version

        for package_id, version in newest.items():
            yield self.package(id=package_id, installed_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching, and reports no
        version: Nimble's records carry a URL, tags, a description, a license
        and a website, but nothing identifying a release.
        ```

        ```{code-block} shell-session

        $ nimble --noColor --accept search parsetoml
        parsetoml:
          url:         https://github.com/NimParsers/parsetoml.git (git)
          tags:        library, parse
          description: Library for parsing TOML files.
          license:     MIT
          website:     https://github.com/NimParsers/parsetoml
        ```
        """
        output = self.run_cli("search", query)

        package_id = None
        description = None
        for line in output.splitlines():
            name_match = self._SEARCH_NAME_REGEXP.match(line)
            if name_match:
                if package_id:
                    yield self.package(id=package_id, description=description)
                package_id = name_match.group("package_id")
                description = None
                continue
            description_match = self._SEARCH_DESCRIPTION_REGEXP.match(line)
            if description_match:
                description = description_match.group("description").strip()
        if package_id:
            yield self.package(id=package_id, description=description)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ nimble --noColor --accept install checksums
        Downloading https://github.com/nim-lang/checksums using git
              Info: using /opt/homebrew/Cellar/nim/2.2.10/nim/bin/nim for compilation
        ```
        """
        spec = package_id if version is None else f"{package_id}@{version}"
        return self.run_cli("install", spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ nimble --noColor --accept uninstall checksums
            Looking for checksums (any version)
           Checking reverse dependencies
            Prompt: The following packages will be removed:
                ... checksums-0.2.2-6357ab195ec23e0e0a54d4d8b5e0212456bf899e
                ... Do you wish to continue? -> [forced yes]
            Removed checksums-0.2.2-6357ab195ec23e0e0a54d4d8b5e0212456bf899e
        ```
        """
        return self.run_cli("uninstall", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ nimble --noColor --accept refresh
        Downloading Official package list
            Success Package list downloaded.
        ```
        """
        self.run_cli("refresh")
