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
import re

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class VCPKG(PackageManager):
    """C and C++ library manager, covering what it installs machine-wide.

    vcpkg has two modes and only one is a package manager in mpm's sense. In
    *manifest* mode it reads a `vcpkg.json` from a project tree and installs
    beside it, which is project scope and out of scope here, recorded among the
    project-scoped ecosystems of {doc}`/unsupported`. In *classic* mode it
    installs into its own root, shared by everything on the machine, which
    Microsoft's own documentation compares to `brew` or `apt`. That mode is
    what this wraps, on the same footing as the runtime managers mpm wraps for
    what they install globally.

    ```{important}
    `--classic` is forced on every invocation, and it is the whole basis of
    that scoping. vcpkg otherwise searches upwards from the working directory
    for a `vcpkg.json` and silently switches modes on finding one, so a listing
    taken inside a C++ project would report that project's dependencies instead
    of the machine's. Unlike the equivalent levers on other managers, this one
    is a documented, stable switch rather than a workaround.
    ```

    ```{caution}
    A package is identified by its full specification, `name:triplet`, because
    that is vcpkg's own unit: the same library built for two triplets is two
    installations, removed independently. Search results are named without a
    triplet, since nothing is installed yet and a bare name resolves against
    the default triplet at install time.
    ```

    ```{note}
    The inventory is read as JSON rather than from the human listing, which
    cannot be parsed safely: that listing pads the specification to a fixed
    fifty columns and truncates anything longer to exactly fifty characters,
    leaving no separator at all before the version. Real specifications exceed
    that width, so the rows whose identifier was already corrupted are also the
    rows a whitespace split would silently misread.
    ```

    ```{warning}
    A vcpkg binary on `PATH` is not necessarily a working one. vcpkg is
    normally cloned and bootstrapped, and a packaged binary with no root
    configured errors on every operation asking for `VCPKG_ROOT` to be set.
    Homebrew ships exactly that, and says so in its own caveats. The failure is
    loud and self-explanatory rather than silent.
    ```

    Documentation: [vcpkg classic mode](https://learn.microsoft.com/en-us/vcpkg/concepts/classic-mode).
    """

    name = "vcpkg"

    homepage_url = "https://vcpkg.io"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = None
    """No floor, because vcpkg's version is a release date rather than a
    semantic version and a requirement here is written in digits and
    comparisons alone, which a hyphenated date cannot be.

    Nothing is lost by it. Every interface used here shipped alongside manifest
    mode in 2020, so no release a user could plausibly be running lacks them,
    and a floor could not catch the case that would matter anyway: a locally
    built vcpkg reports a sentinel date far in the future precisely so that
    version checks in scripts always pass.
    """

    pre_args = ("--classic",)
    """Pins every call to the machine-wide installation, whatever the working
    directory contains.
    """

    version_regexes = (r"version (?P<version>\d{4}-\d{2}-\d{2})",)
    r"""Search the release date the version banner reports.

    ```{code-block} shell-session

    $ vcpkg --classic version
    vcpkg package management program version 2026-07-27-unknownhash

    See LICENSE.txt for license information.
    ```

    The trailing component is a commit hash, or a packager's own marker, and is
    dropped.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^\t(?P<package_id>\S+)\s+(?P<installed_version>\S+) -> (?P<latest_version>\S+)$",
    )
    """One upgradable package. Unlike the installed listing this one is written
    with a literal separator and no truncation, so it is parsed as text.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ vcpkg --classic list --x-json
        ```

        ```{code-block} console

        {
          "zlib:x64-linux": {
            "package_name": "zlib",
            "triplet": "x64-linux",
            "version": "1.3.1",
            "port_version": 0,
            "features": [],
            "desc": ["A compression library"]
          }
        }
        ```

        The port revision is appended to the version as vcpkg itself renders
        it, and only when it is not zero.
        """
        output = self.run_cli("list", "--x-json")
        if not output.strip():
            return
        for spec, data in json.loads(output).items():
            if not isinstance(data, dict):
                continue
            version = data.get("version")
            port_version = data.get("port_version") or 0
            if version and port_version:
                version = f"{version}#{port_version}"
            yield self.package(id=spec, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        vcpkg's `update` is a report rather than a mutation: in classic mode it
        compares what is installed against the ports catalog and prints the
        difference, changing nothing. It refuses to run in manifest mode at
        all, which the forced `--classic` keeps it out of.

        ```{code-block} shell-session

        $ vcpkg --classic update
        ```

        ```{code-block} console

        Using local port versions. To update the local ports, use `git pull`.
        The following packages differ from their port versions:
                corrade:x64-windows              2020.06#4 -> 2020.06#5
                openal-soft:x64-windows          1.22.2#5 -> 1.23.0
        ```
        """
        output = self.run_cli("update")
        yield from (
            self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )
            for match in map(self._OUTDATED_REGEXP.match, output.splitlines())
            if match
        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Read as JSON, whose keys are the port names. The human listing computes
        its column widths from the results and renders a port's features as
        rows of their own carrying no version, neither of which a single
        pattern reads reliably.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ vcpkg --classic search zlib --x-json
        ```
        """
        output = self.run_cli("search", query, "--x-json")
        if not output.strip():
            return
        for port_name, data in json.loads(output).items():
            version = data.get("version") if isinstance(data, dict) else None
            yield self.package(id=port_name, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        A bare name resolves against the default triplet; a full specification
        pins the one it names.

        ```{code-block} shell-session

        $ vcpkg --classic install zlib:x64-linux
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        `--no-dry-run` is required for vcpkg to act at all: without it the
        command prints its plan, warns, and exits non-zero.

        ```{code-block} shell-session

        $ vcpkg --classic upgrade --no-dry-run
        ```
        """
        return self.build_cli("upgrade", "--no-dry-run")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        ```{code-block} shell-session

        $ vcpkg --classic upgrade --no-dry-run zlib:x64-linux
        ```
        """
        return self.build_cli("upgrade", "--no-dry-run", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        `--recurse` is deliberately not passed. vcpkg refuses to remove a
        package other installations depend on, listing them and exiting
        non-zero, and that refusal is the right outcome: the alternative would
        quietly remove packages the user never named.

        ```{code-block} shell-session

        $ vcpkg --classic remove zlib:x64-linux
        ```
        """
        return self.run_cli("remove", package_id)
