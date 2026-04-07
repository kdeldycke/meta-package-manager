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

from extra_platforms import WINDOWS

from ..base import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from ..base import Package


class WinGet(PackageManager):
    homepage_url = "https://github.com/microsoft/winget-cli"

    platforms = WINDOWS

    requirement = ">=1.7"

    post_args = ("--accept-source-agreements", "--disable-interactivity")
    """
    ``--accept-source-agreements``:
        Used to accept the source license agreement, and avoid the following prompt:

        .. code-block:: pwsh-session
            PS C:\\Users\\kev> winget list
            The "msstore' source requires that you view the following agreements before using.
            Terms of Transaction: https://aka.ms/microsoft-store-terms-of-transaction
            The source requires the current machine's 2-letter geographic region to be sent to the backend service to function prope rly (ex. "US").

            Do you agree to all the source agreements terms?
            [Y] Yes [N] No:

    ``--disable-interactivity``:
        Disable interactive prompts.

    ..todo::
        Add the ``--no-progress`` option once it is available in the stable release:
        - https://github.com/microsoft/winget-cli/pull/6049
        - https://github.com/microsoft/winget-cli/issues/3494#issuecomment-3921618377
    """

    version_regexes = (r"v\s*(?P<version>\S+)",)
    """
    .. code-block:: pwsh-session

        PS C:\\Users\\kev> winget --version
        Windows Package Manager v1.28.220
    """

    def _parse_details(
        self, output: str, filter_by_source: bool = False
    ) -> Iterator[tuple[str, str, str, str | None]]:
        """Parse --details output from winget list or upgrade-available commands.

        Each package is formatted as:
            (N/M) <Name> [<Id>]
            Version: <current_version>
            Publisher: <publisher>
            Origin Source: winget
            ...
            [Available Upgrades:]
            [  winget [<latest_version>]]

        If filter_by_source=True, only packages with Origin Source: winget are returned.
        """
        # Split on block markers like "(1/232) Package Name [Id]"
        blocks = re.split(r'(?=^\(\d+/\d+\) )', output, flags=re.MULTILINE)

        for block in blocks:
            if not block.strip():
                continue

            lines = block.strip().splitlines()
            if not lines:
                continue

            # Parse the header line: (N/M) <Name> [<Id>]
            header = lines[0]
            header_match = re.match(
                r'^\(\d+/\d+\)\s+(.+)\s+\[([^\]]+)\]$',
                header,
            )
            if not header_match:
                continue

            name = header_match.group(1).strip()
            package_id = header_match.group(2).strip()
            version = None
            origin_source = None

            # Look for version on the next line or in key:value format
            latest_version = None
            for i, line in enumerate(lines[1:], 1):
                line_stripped = line.strip()
                # Extract version from "Version: X.Y.Z" line
                if line_stripped.startswith('Version:'):
                    version = line_stripped.split(':', 1)[1].strip()
                # Track Origin Source
                elif line_stripped.startswith('Origin Source:'):
                    origin_source = line_stripped.split(':', 1)[1].strip()
                # Look for available upgrades
                elif line_stripped == 'Available Upgrades:':
                    # Next non-empty line should have the version.
                    for future_line in lines[i + 1:]:
                        future_line = future_line.strip()
                        if future_line:
                            # Format: "winget [X.Y.Z]"
                            upgrade_match = re.search(r'\[([^\]]+)\]', future_line)
                            if upgrade_match:
                                latest_version = upgrade_match.group(1)
                            break
                    break

            # Only yield if we found a version
            if version:
                # Filter by source if requested (only include winget packages)
                if filter_by_source and origin_source != 'winget':
                    continue

                yield (name, package_id, version, latest_version)

    def _parse_table(self, output: str) -> Iterator[Generator[str, None, None]]:
        """Parse a table from the output of a winget command and returns a generator of cells."""
        # Extract table.
        table_start = "Name "
        assert table_start in output, (
            f"Cannot find table starting with {table_start!r} in:\n{output}"
        )
        assert output.count(table_start) == 1, (
            f"{table_start!r} not unique in:\n{output}"
        )
        table = output.split(table_start, 1)[1]

        # Check table format.
        lines = table.splitlines()
        table_width = len(lines[0])
        assert lines[1] == "-" * table_width, (
            f"Table headers not followed by expected separator:\n{table}"
        )
        assert all(len(line) <= table_width for line in lines[2:]), (
            f"Table lines with different width:\n{table}"
        )

        # Guess column positions.
        headers = []
        col_str = ""
        for char in lines[0]:
            if col_str and char != " " and " " in col_str:
                headers.append(col_str)
                col_str = ""
            col_str += char
        if col_str:
            headers.append(col_str)

        col_ranges = []
        for header in headers:
            start = lines[0].index(header)
            end = start + len(header)
            col_ranges.append((start, end))

        for line in lines[2:]:
            yield (line[start:end].strip() for start, end in col_ranges)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget list --details --accept-source-agreements --disable-interactivity
            (1/7) CCleaner [CCleaner] Version: 6.08
            Publisher: Piriform Software Ltd
            Local Identifier: ARP\\Machine\\X64\\CCleaner
            Product Code: CCleaner
            Installer Category: exe
            Installed Scope: Machine
            Installed Architecture: X64
            Installed Locale: en-US
            Origin Source: winget
            Available Upgrades:

            (2/7) Git [Git.Git] Version: 2.37.3
            Publisher: The Git Development Community
            ...

        Only returns packages with Origin Source: winget to exclude packages
        installed via other sources (e.g., sideload, portable).
        """
        output = self.run_cli("list", "--details")

        for name, package_id, installed_version, _ in self._parse_details(
            output, filter_by_source=True
        ):
            yield self.package(
                id=package_id,
                name=name,
                installed_version=installed_version,
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget list --upgrade-available --details --accept-source-agreements --disable-interactivity
            (1/4) Git [Git.Git] Version: 2.37.3
            Publisher: The Git Development Community
            ...
            Available Upgrades:
              winget [2.45.1]

            (2/4) Microsoft Edge [Microsoft.Edge] Version: 109.0.1518.70
            Publisher: Microsoft
            ...
            Available Upgrades:
              winget [125.0.2535.51]

        Only returns packages with Origin Source: winget to exclude packages
        installed via other sources (e.g., sideload, portable).
        """
        output = self.run_cli("list", "--upgrade-available", "--details")

        for name, package_id, installed_version, latest_version in self._parse_details(
            output, filter_by_source=True
        ):
            yield self.package(
                id=package_id,
                name=name,
                installed_version=installed_version,
                latest_version=latest_version,
            )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --query vscode --accept-source-agreements --disable-interactivity
            Name                             Id                               Version      Match               Source
            ---------------------------------------------------------------------------------------------------------
            Microsoft Visual Studio Code     Microsoft.VisualStudioCode       1.89.1       Moniker: vscode     winget
            MrCode                           zokugun.MrCode                   1.82.0.23253 Tag: vscode         winget
            VSCodium Insiders                VSCodium.VSCodium.Insiders       1.88.0.24095 Tag: vscode         winget
            VSCodium                         VSCodium.VSCodium                1.89.1.24130 Tag: vscode         winget
            Upgit                            pluveto.Upgit                    0.2.18       Tag: vscode         winget
            vscli                            michidk.vscli                    0.3.0        Tag: vscode         winget
            Huawei QuickApp IDE              Huawei.QuickAppIde               14.0.1       Tag: vscode         winget
            TheiaBlueprint                   EclipseFoundation.TheiaBlueprint 1.44.0       Tag: vscode         winget
            Codium                           Alex313031.Codium                1.86.2.24053 Tag: vscode         winget
            Cursor Editor                    CursorAI,Inc.Cursor              latest       Tag: vscode         winget
            Microsoft Visual Studio Code CLI Microsoft.VisualStudioCode.CLI   1.89.1       Moniker: vscode-cli winget

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --query vscode --exact --accept-source-agreements --disable-interactivity
            Name                         Id                               Version      Match           Source
            -------------------------------------------------------------------------------------------------
            Microsoft Visual Studio Code Microsoft.VisualStudioCode       1.89.1       Moniker: vscode winget
            MrCode                       zokugun.MrCode                   1.82.0.23253 Tag: vscode     winget
            VSCodium Insiders            VSCodium.VSCodium.Insiders       1.88.0.24095 Tag: vscode     winget
            VSCodium                     VSCodium.VSCodium                1.89.1.24130 Tag: vscode     winget
            Upgit                        pluveto.Upgit                    0.2.18       Tag: vscode     winget
            vscli                        michidk.vscli                    0.3.0        Tag: vscode     winget
            Huawei QuickApp IDE          Huawei.QuickAppIde               14.0.1       Tag: vscode     winget
            TheiaBlueprint               EclipseFoundation.TheiaBlueprint 1.44.0       Tag: vscode     winget
            Codium                       Alex313031.Codium                1.86.2.24053 Tag: vscode     winget
            Cursor Editor                CursorAI,Inc.Cursor              latest       Tag: vscode     winget

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --id VSCodium.VSCodium --accept-source-agreements --disable-interactivity
            Name              Id                         Version      Source
            ----------------------------------------------------------------
            VSCodium Insiders VSCodium.VSCodium.Insiders 1.88.0.24095 winget
            VSCodium          VSCodium.VSCodium          1.89.1.24130 winget

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --name Codium --accept-source-agreements --disable-interactivity
            Name              Id                         Version      Source
            ----------------------------------------------------------------
            Codium            Alex313031.Codium          1.86.2.24053 winget
            VSCodium Insiders VSCodium.VSCodium.Insiders 1.88.0.24095 winget
            VSCodium          VSCodium.VSCodium          1.89.1.24130 winget

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --id VSCodium.VSCodium  --exact --accept-source-agreements --disable-interactivity
            Name     Id                Version      Source
            ----------------------------------------------
            VSCodium VSCodium.VSCodium 1.89.1.24130 winget

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget search --name Codium --exact --accept-source-agreements --disable-interactivity
            Name   Id                Version      Source
            --------------------------------------------
            Codium Alex313031.Codium 1.86.2.24053 winget
        """
        # Default search is extended to all metadata: id, name, moniker and tag.
        if extended:
            args = ["search", "--query", query]
            # Exact search deactivates substring search.
            if exact:
                args.append("--exact")
            output = self.run_cli(args)
            for name, package_id, version, _, _ in self._parse_table(output):
                yield self.package(id=package_id, name=name, latest_version=version)

        # For non-extended search, we need to perform 2 queries, one for id and
        # one for name.
        else:
            for field in "--id", "--name":
                output = self.run_cli(
                    "search", field, query, "--exact" if exact else None
                )
                for name, package_id, version, _ in self._parse_table(output):
                    yield self.package(id=package_id, name=name, latest_version=version)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget install --id Microsoft.PowerToys --accept-package-agreements --version 0.15.2 --accept-source-agreements --disable-interactivity
            Found Power Toys [Microsoft.PowerToys] Version 0.15.2
            This application is licensed to you by its owner.
            Microsoft is not responsible for, nor does it grant any licenses to, third-party packages.
            Successfully verified installer hash
            Starting package install...
              ██████████████████████████████  100%
            Successfully installed
        """
        args = ["install", "--id", package_id, "--accept-package-agreements"]
        if version:
            args += ["--version", version]
        return self.run_cli(args)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget upgrade --all --accept-package-agreements --accept-source-agreements --disable-interactivity
            Name                            Id                            Version       Available     Source
            ------------------------------------------------------------------------------------------------
            Microsoft Edge                  Microsoft.Edge                109.0.1518.70 125.0.2535.51 winget
            Microsoft Edge WebView2 Runtime Microsoft.EdgeWebView2Runtime 109.0.1518.70 125.0.2535.51 winget
            Python Launcher                 Python.Launchez               < 3.12.0      3.12.0        winget
            Microsoft Visual C++ (x86)...   Microsoft.VCRedist.2015+.X86  14.34.31931.0 14.38.33135.0 winget
            4 upgrades available.

            Installing dependencies:
            This package requires the following dependencies:
              - Packages
                  Microsoft.UI.Xaml.2.8 [>= 8.2306.22001.0]
            (1/3) Found Microsoft Edge WebView2 Runtime [Microsoft.EdgeWebView2Runtime] Version 125. 0.2535.51
            This application is licensed to you by its owner.
            Microsoft is not responsible for, nor does it grant any licenses to, third-party packages.
            Downloading https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/e5dd841e-17ff-43b7-a2c0-ff759f55c202/MicrosoftEdgeWebView2RuntimeInstallerARM64.exe
              ██████████████████████████████  166 MB /  166 MB
            Successfully verified installer hash
            Starting package install...
            Successfully installed

            (...)
        """
        return self.build_cli("update", "--all", "--accept-package-agreements")

    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget upgrade --id Git.Git --accept-package-agreements --accept-source-agreements --disable-interactivity
            Found Git [Git.Git] Version 2.45.1
            This application is licensed to you by its owner.
            Microsoft is not responsible for, nor does it grant any licenses to, third-party packages.
            Downloading https://github.com/git-for-windows/git/releases/download/v2.45.1.windows.1/Git-2.45.1-64-bit.exe
              ██████████████████████████████  64.7 MB / 64.7 MB
            Successfully verified installer hash
            Starting package install...
            Successfully installed

        .. todo::

            Automatically uninstall the package if the technology is different:

            .. code-block:: pwsh-session

                PS C:\\Users\\kev> winget upgrade --id Microsoft.Edge
                A newer version was found, but the install technology is different from the current version installed. Please uninstall the package and install the newer version.
        """
        args = ["install", "--id", package_id, "--accept-package-agreements"]
        if version:
            args += ["--version", version]
        return self.build_cli(args)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: pwsh-session

            PS C:\\Users\\kev> winget uninstall --id Microsoft.PowerToys --source winget --accept-source-agreements --disable-interactivity
            Found PowerToys (Preview) [Microsoft.PowerToys]
            Starting package uninstall...
              ██████████████████████████████  100%
            Successfully uninstalled
        """
        return self.run_cli("uninstall", "--id", package_id, "--source", "winget")
