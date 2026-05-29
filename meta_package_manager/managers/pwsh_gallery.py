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
from typing import cast

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities
from ..manager import CLIError, PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


def _pwsh_quote(value: str) -> str:
    """Wrap ``value`` in PowerShell single quotes, doubling embedded single quotes.

    PowerShell single-quoted strings are literal: the only escape is ``''`` for a
    literal single quote. No backslash interpretation, no variable expansion.
    """
    return "'" + value.replace("'", "''") + "'"


class PWSH_Gallery(PackageManager):
    """PowerShell Gallery client, driven through the modern
    `Microsoft.PowerShell.PSResourceGet
    <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.psresourceget/>`_
    module.

    .. note::
        Only ``pwsh`` (PowerShell 7+) is supported. Legacy Windows PowerShell 5.1
        is intentionally excluded: it ships ``PowerShellGet`` v2, which depends on
        the NuGet provider and prompts to trust ``PSGallery`` on first install.
        ``PSResourceGet`` ships bundled with ``pwsh`` 7.4+ and supersedes the v2
        cmdlets with cleaner, JSON-friendly objects.

    .. caution::
        All install and search operations target ``-Scope CurrentUser`` so that
        ``mpm`` does not require elevation. ``upgrade`` and ``remove`` are scope-
        agnostic and operate on whichever scope holds each module.

    .. caution::
        ``Install-PSResource`` is invoked with ``-TrustRepository`` so the
        confirmation prompt on the default ``PSGallery`` repository is bypassed.
        Only the default repository is consulted: third-party ``PSRepository``
        registrations are out of scope.
    """

    name = "PowerShell Gallery"
    """The metaclass derives ``id = "pwsh-gallery"`` from the class name
    (``PWSH_Gallery``: lowercased, underscore→dash). ``name`` here is the
    official product name shown to users.
    """

    homepage_url = "https://www.powershellgallery.com"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=7.4.0"
    """``PSResourceGet`` is bundled with PowerShell 7.4+, which is the floor where
    every operation below runs without installing extra modules.
    """

    cli_names = ("pwsh",)

    pre_args = ("-NoProfile", "-NonInteractive", "-Command")
    """Always invoke ``pwsh`` non-interactively, with no user profile, and run a
    single ``-Command`` expression. Each operation passes one PowerShell
    expression as the final argument; subprocess receives a clean argv list so no
    shell quoting is required between Python and ``pwsh``.

    .. note::
        Version detection (``pwsh --version``) skips ``pre_args`` because
        :py:func:`meta_package_manager.manager.PackageManager.version` calls
        ``run_cli`` with ``auto_pre_args=False``.
    """

    version_regexes = (r"PowerShell\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ pwsh --version
        PowerShell 7.4.6
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed PowerShell resources.

        ``Get-InstalledPSResource`` enumerates every module, script and DSC
        resource in every installed scope. The ``Version`` property is a
        ``NuGetVersion`` object: ``ConvertTo-Json`` would otherwise serialise it
        as a structured ``{Major, Minor, ...}`` mapping, so it is projected to a
        string up-front. ``ConvertTo-Json -AsArray`` forces a JSON array even
        when zero or one resource is returned (single results would otherwise be
        serialised as a bare object).

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Get-InstalledPSResource | \\
                 Select-Object Name, @{n='Version';e={$_.Version.ToString()}} | \\
                 ConvertTo-Json -AsArray -Depth 2 -Compress"
            [{"Name":"PSReadLine","Version":"2.3.6"},
             {"Name":"Pester","Version":"5.5.0"}]
        """
        output = self.run_cli(
            "Get-InstalledPSResource"
            " | Select-Object Name, @{n='Version';e={$_.Version.ToString()}}"
            " | ConvertTo-Json -AsArray -Depth 2 -Compress",
            must_succeed=True,
        )
        for entry in self._parse_json_array(output):
            yield self.package(
                id=entry["Name"],
                installed_version=entry["Version"],
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch resources with a newer release on the gallery.

        ``PSResourceGet`` has no built-in ``outdated`` cmdlet. The comparison is
        done server-side in a single ``pwsh`` invocation: each installed resource
        is looked up via ``Find-PSResource`` and only emitted when the gallery
        version is strictly greater. Running the loop inside ``pwsh`` avoids the
        N+1 round trips that a Python-side comparison would cause.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Get-InstalledPSResource | ForEach-Object { ... } | \\
                 ConvertTo-Json -AsArray -Depth 2 -Compress"
            [{"Name":"PSReadLine","Installed":"2.3.4","Latest":"2.3.6"}]
        """
        output = self.run_cli(
            "Get-InstalledPSResource | ForEach-Object {"
            " $i = $_;"
            " $l = Find-PSResource -Name $i.Name -ErrorAction SilentlyContinue"
            " | Select-Object -First 1;"
            " if ($l -and $l.Version -gt $i.Version) {"
            " [PSCustomObject]@{"
            " Name = $i.Name;"
            " Installed = $i.Version.ToString();"
            " Latest = $l.Version.ToString()"
            " } }"
            " } | ConvertTo-Json -AsArray -Depth 2 -Compress",
            must_succeed=True,
        )
        for entry in self._parse_json_array(output):
            yield self.package(
                id=entry["Name"],
                installed_version=entry["Installed"],
                latest_version=entry["Latest"],
            )

    @search_capabilities(extended_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search the gallery.

        ``Find-PSResource -Name`` accepts a wildcard pattern. Wildcards are added
        around ``query`` for fuzzy search and dropped for exact match.

        ``extended`` search (matching against description) is not supported by
        ``Find-PSResource``: results are refiltered in Python by the framework
        when ``extended=True``.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Find-PSResource -Name '*readline*' | \\
                 Select-Object Name, @{n='Version';e={$_.Version.ToString()}}, Description | \\
                 ConvertTo-Json -AsArray -Depth 2 -Compress"
            [{"Name":"PSReadLine","Version":"2.3.6",
              "Description":"Great command line editing..."}]
        """
        pattern = query if exact else f"*{query}*"
        output = self.run_cli(
            f"Find-PSResource -Name {_pwsh_quote(pattern)}"
            " -ErrorAction SilentlyContinue"
            " | Select-Object Name,"
            " @{n='Version';e={$_.Version.ToString()}},"
            " Description"
            " | ConvertTo-Json -AsArray -Depth 2 -Compress",
            must_succeed=True,
        )
        for entry in self._parse_json_array(output):
            yield self.package(
                id=entry["Name"],
                description=entry.get("Description"),
                latest_version=entry.get("Version"),
            )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one resource into the current-user scope.

        ``-TrustRepository`` bypasses the ``Untrusted repository`` prompt that
        ``PSGallery`` emits on first install. ``-AcceptLicense`` silently accepts
        any module-bundled license. ``-Reinstall`` is *not* passed: re-running
        ``install`` on an already-installed resource is a no-op, matching
        ``pip install`` behaviour.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Install-PSResource -Name 'PSReadLine' -Scope CurrentUser \\
                 -TrustRepository -AcceptLicense"
        """
        expression = (
            f"Install-PSResource -Name {_pwsh_quote(package_id)}"
            " -Scope CurrentUser -TrustRepository -AcceptLicense"
        )
        if version:
            expression += f" -Version {_pwsh_quote(version)}"
        return self.run_cli(expression)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Upgrade every installed resource to its latest gallery version.

        Scope is intentionally not constrained: any installed resource is
        eligible, regardless of which scope it lives in.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Update-PSResource -TrustRepository -AcceptLicense"
        """
        return self.build_cli("Update-PSResource -TrustRepository -AcceptLicense")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Upgrade a single resource.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Update-PSResource -Name 'PSReadLine' -TrustRepository -AcceptLicense"
        """
        expression = (
            f"Update-PSResource -Name {_pwsh_quote(package_id)}"
            " -TrustRepository -AcceptLicense"
        )
        if version:
            expression += f" -Version {_pwsh_quote(version)}"
        return self.build_cli(expression)

    def remove(self, package_id: str) -> str:
        """Uninstall a resource from whichever scope holds it.

        .. code-block:: shell-session

            $ pwsh -NoProfile -NonInteractive -Command \\
                "Uninstall-PSResource -Name 'PSReadLine'"
        """
        return self.run_cli(
            f"Uninstall-PSResource -Name {_pwsh_quote(package_id)}",
        )

    @staticmethod
    def _parse_json_array(output: str) -> list[dict]:
        """Parse ``ConvertTo-Json -AsArray`` output into a list of dicts.

        ``-AsArray`` (PowerShell 7.2+) guarantees a JSON array even when zero or
        one object would be serialised. The pipe still produces empty stdout
        when ``Get-InstalledPSResource`` returns nothing on a fresh install, so
        the empty-string guard is kept for safety.

        Raises :py:class:`~meta_package_manager.manager.CLIError` when the output
        is non-empty but not valid JSON. This propagates through the caller's
        generator so that :py:func:`~meta_package_manager.cli.installed` (and
        similar) can catch it and skip the manager gracefully.
        """
        if not output.strip():
            return []
        try:
            return cast("list[dict]", json.loads(output))
        except json.JSONDecodeError as ex:
            raise CLIError(None, output, str(ex)) from ex
