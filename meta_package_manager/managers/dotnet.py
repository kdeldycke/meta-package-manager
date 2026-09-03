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

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class DotNet(PackageManager):
    """.NET global tools, the CLI programs the .NET SDK installs from NuGet.

    Every operation goes through the `dotnet tool` subcommand group, forced by
    {attr}`DotNet.pre_args`, and targets the user-wide scope with `--global`. Global
    tools land under `~/.dotnet/tools` and are never shared between users, so
    no operation escalates: elevation is only ever needed for the separate
    `--tool-path` scenario, which this wrapper does not drive.

    Documentation: [.NET global tools](https://learn.microsoft.com/dotnet/core/tools/global-tools).

    ```{note}
    The listing and the search results are column tables whose headers are
    localized resource strings, translated into thirteen languages. Rather
    than match English literals, {attr}`DotNet.extra_env` pins the CLI language and
    both parsers key on the shape of the row: a package ID, two or more
    spaces, then a version starting with a digit. That skips the header, the
    dashed rule and any diagnostic prose the SDK prints above the table, such
    as the broken-tool warning of
    [dotnet/sdk#4111](https://github.com/dotnet/sdk/issues/4111).
    ```

    ```{note}
    `dotnet tool list` also speaks JSON, through an undocumented
    `--format json` that landed in the `9.0.100` SDK
    ([dotnet/sdk#37394](https://github.com/dotnet/sdk/pull/37394)). mpm
    deliberately parses the table instead: the three columns of the global
    listing are all whitespace-free, so nothing is gained, while keying on
    JSON would raise the floor past `8.0.4xx`, the oldest SDK band still
    supported.
    ```

    ```{caution}
    No `outdated` operation is declared: the SDK ships no way to compare
    installed tools against NuGet without mutating them. A spec for
    `dotnet tool list --outdated` was written by an SDK maintainer in
    [dotnet/sdk#22853](https://github.com/dotnet/sdk/issues/22853), which was
    then closed as not planned. `upgrade --all` is unaffected and maps to the
    native `dotnet tool update --all`.
    ```

    ```{note}
    No `cleanup` either. The obvious candidate, `dotnet nuget locals all
    --clear`, empties the machine-wide NuGet package folder every .NET project
    restores against, so a tool-scoped cleanup would invalidate unrelated
    builds. Nothing clears only what the global tools pulled.
    ```
    """

    name = "dotnet tool"

    homepage_url = "https://learn.microsoft.com/dotnet/core/tools/global-tools"
    logo = "dotnet"

    keywords = ("nuget",)

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=8.0.400"
    """`--all` on `dotnet tool update` first shipped in the `8.0.400` SDK, the
    opening release of the `8.0.4xx` feature band
    ([dotnet/sdk#38996](https://github.com/dotnet/sdk/pull/38996), merged onto
    `release/8.0.4xx`). It was never backported to `8.0.3xx`, so that is the
    binding floor: every other operation this wrapper drives predates it by
    years, `dotnet tool search` being the youngest at `5.0.100`.
    """

    extra_env: ClassVar = {
        # Pin the CLI language so the localized table headers and messages stay
        # in English, whatever the host locale.
        "DOTNET_CLI_UI_LANGUAGE": "en-us",
        # Keep the first-run banner and the telemetry notice off stdout, where
        # they would precede the table.
        "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    }

    pre_args = ("tool",)
    """Every operation is a `dotnet tool` subcommand, so the group is forced
    onto each call. The version probe is exempt: it runs with
    `auto_pre_args=False`, which is what leaves it as a bare `dotnet --version`.
    """

    version_regexes = (r"^(?P<version>\d+\.\d+\.\d+\S*)",)
    """`dotnet --version` prints the SDK version alone, on a single unlabelled
    line.

    It is deliberately preferred over `dotnet --info` as the probe: on a machine
    carrying the .NET runtime but no SDK, `--version` fails while `--info` still
    exits `0` and reports its inventory. Since `dotnet tool` needs the SDK, the
    failure is the correct availability signal.

    ```{code-block} shell-session

    $ dotnet --version
    9.0.306
    ```
    """

    _LIST_REGEXP = re.compile(
        r"""
        ^                                  # Anchor on the start of the line.
        (?P<package_id>[a-zA-Z0-9._-]+)    # NuGet package ID.
        \ {2,}                             # Column delimiter, six spaces wide.
        (?P<installed_version>\d\S*)       # Version, always starting with a digit.
        """,
        re.VERBOSE,
    )
    _SEARCH_REGEXP = re.compile(
        r"""
        ^                                  # Anchor on the start of the line.
        (?P<package_id>[a-zA-Z0-9._-]+)    # NuGet package ID.
        \ {2,}                             # Column delimiter, six spaces wide.
        (?P<latest_version>\d\S*)          # Version, always starting with a digit.
        """,
        re.VERBOSE,
    )
    """Match one data row of a `dotnet tool` column table.

    Both listings are rendered by the same `PrintableTable`, which pads every
    cell and joins the columns with six spaces, so the two patterns differ only
    in which package field the version lands in. Requiring a digit-leading
    second column is what discriminates a data row from the header, whose own
    second column is a word in whatever language the CLI runs under.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ dotnet tool list --global
        Package Id      Version      Commands
        --------------------------------------
        dotnet-ef       2.1.11       dotnet-ef
        ```
        """
        output = self.run_cli("list", "--global")
        yield from self.parse_regex_lines(self._LIST_REGEXP, output)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        `dotnet tool search` queries NuGet's search endpoint with
        `packageType=dotnettool`, so only .NET tools come back. NuGet offers no
        flag to restrict or widen that match, so both refinements are left to
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`.

        Only the first two columns are captured: `Authors` and `Downloads` have
        no package field to land in, and `Verified` is a marker rather than a
        value.

        ```{caution}
        NuGet matches the query against descriptions and tags as well as
        package IDs, but the default table prints no description column, so
        `mpm` cannot see why a row matched. `--extended` is therefore declared
        unsupported rather than claimed: refiltering keeps only the ID and name
        matches, and a package that matched on its description alone is
        dropped. Widening this means parsing `dotnet tool search --detail`,
        whose per-package blocks do carry a `Description:` line, at the cost of
        keying the parser on localized field labels instead of on the row
        shape.
        ```

        ```{code-block} shell-session

        $ dotnet tool search format
        Package ID                              Latest Version      Authors                                                                     Downloads      Verified
        ---------------------------------------------------------------------------------------------------------------------------------------------------------------
        dotnet-format                           4.1.131201          Microsoft                                                                   496746
        bsoa.generator                          1.0.0               Microsoft                                                                   533
        ```
        """
        output = self.run_cli("search", query)
        yield from self.parse_regex_lines(self._SEARCH_REGEXP, output)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ dotnet tool install --global dotnetsay
        ```

        ```{code-block} shell-session

        $ dotnet tool install --global dotnetsay --version 2.1.7
        ```
        """
        args = ["install", "--global", package_id]
        if version:
            # --version is the portable pin. The dotnetsay@2.1.7 shorthand only
            # parses from the 10.0.100 SDK onwards.
            args += ["--version", version]
        return self.run_cli(*args)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ dotnet tool update --global --all
        ```
        """
        return self.build_cli("update", "--global", "--all")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        `dotnet tool update` is implemented upstream as an uninstall followed by
        a reinstall, and refuses to move a tool backwards: a `version` older
        than the installed one needs a `remove` first.

        ```{code-block} shell-session

        $ dotnet tool update --global dotnetsay
        ```

        ```{code-block} shell-session

        $ dotnet tool update --global dotnetsay --version 2.1.7
        ```
        """
        args = ["update", "--global", package_id]
        if version:
            args += ["--version", version]
        return self.build_cli(*args)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ dotnet tool uninstall --global dotnetsay
        ```
        """
        return self.run_cli("uninstall", "--global", package_id)
