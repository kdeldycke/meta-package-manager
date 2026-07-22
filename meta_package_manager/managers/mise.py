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

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Mise(PackageManager):
    """mise (formerly rtx) installs and switches between versions of developer
    tools like Node, Python, Ruby and any tool reachable through its plugin
    backends.

    .. note::
        ``mpm`` is system-scoped, so this wrapper reports every tool version
        present on disk regardless of which ``mise.toml`` (global or project)
        requested it. Project-pinned versions are not surfaced as a separate
        scope.

    .. note::
        Backend-prefixed tool IDs (``pipx:ruff``, ``cargo:ubi-cli``,
        ``asdf:mise-plugins/mise-poetry``) round-trip as-is. The colon is part
        of the package ID; ``mpm install pipx:ruff`` resolves the backend
        through ``mise`` itself.

    .. caution::
        ``mise outdated --json`` only reports tools tracked in a ``mise.toml``
        (global or project). A tool installed bare with ``mise install <tool>``
        and never pinned with ``mise use`` will not appear in the outdated
        list, so ``mpm outdated --mise`` understates the upgrade surface for
        those entries.
    """

    name = "mise"

    homepage_url = "https://mise.jdx.dev"

    platforms = ALL_PLATFORMS

    requirement = ">=2025.5.10"
    """``mise search`` shipped in ``2025.5.10``, the binding floor for the
    feature set this wrapper depends on. Earlier releases also miss the
    ``outdated --json`` fix from ``2025.2.8`` that emits valid JSON when no
    tool is outdated.
    """

    version_regexes = (r"^(?P<version>\d+\.\d+\.\d+)",)
    """``mise`` uses CalVer (``YYYY.M.P``), not SemVer.

    .. code-block:: shell-session

        $ mise --version
        2026.6.3 macos-arm64 (2026-06-13)
    """

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s{2,}(?P<description>.+)$",
        re.MULTILINE,
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Emits one :py:class:`meta_package_manager.package.Package` per
        ``(tool, installed_version)`` pair, so a tool installed at multiple
        versions yields multiple entries sharing the same ID.

        .. code-block:: shell-session

            $ mise ls --installed --json
            {
              "node": [
                {
                  "version": "20.10.0",
                  "install_path": "~/.local/share/mise/installs/node/20.10.0",
                  "source": {"type": "mise.toml",
                             "path": "~/.config/mise/config.toml"}
                }
              ],
              "pipx:ruff": [
                {
                  "version": "0.6.9",
                  "install_path": "~/.local/share/mise/installs/pipx-ruff/0.6.9"
                }
              ]
            }
        """
        output = self.run_cli("ls", "--installed", "--json", must_succeed=True)
        data = self.parse_json(output)
        if not data:
            return
        for tool_id, entries in data.items():
            for entry in entries:
                yield self.package(
                    id=tool_id,
                    installed_version=entry["version"],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ mise outdated --json
            {
              "node": {
                "requested": "20",
                "current": "20.0.0",
                "latest": "20.10.0"
              }
            }
        """
        output = self.run_cli("outdated", "--json", must_succeed=True)
        data = self.parse_json(output)
        if not data:
            return
        for tool_id, info in data.items():
            yield self.package(
                id=tool_id,
                installed_version=info["current"],
                latest_version=info["latest"],
            )

    @search_capabilities(extended_support=True, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ``mise search`` returns a two-column ``Tool  Description`` table.
        ``--match-type contains`` keeps the candidate set wide; the framework's
        :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`
        narrows it down to honor ``extended`` and ``exact`` flags.

        .. code-block:: shell-session

            $ mise search --no-header --match-type contains node
            node                Node.js
            node-build          Compile and install Node.js
            nodejs              alias for node
        """
        output = self.run_cli(
            "search",
            "--no-header",
            "--match-type",
            "contains",
            query,
        )
        for match in self._SEARCH_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                description=match.group("description").strip(),
            )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ``mise install <tool>`` resolves to the latest version compatible with
        the active config; ``mise install <tool>@<version>`` pins it
        explicitly. Neither variant writes to ``mise.toml``: the dedicated
        ``mise use`` command is the config-mutating verb and is deliberately
        avoided here.

        .. code-block:: shell-session

            $ mise install node@20
        """
        spec = f"{package_id}@{version}" if version else package_id
        return self.run_cli("install", spec)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ mise upgrade
        """
        return self.build_cli("upgrade")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ mise upgrade node
        """
        spec = f"{package_id}@{version}" if version else package_id
        return self.build_cli("upgrade", spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ``mise uninstall <tool>`` errors when more than one version of the
        tool is installed. ``--all`` removes every installed version
        unconditionally, which matches ``mpm``'s "remove this package"
        contract.

        .. code-block:: shell-session

            $ mise uninstall --all node
        """
        return self.run_cli("uninstall", "--all", package_id)

    def sync(self) -> None:
        """Refresh plugin metadata.

        ``mise`` resolves tool listings and version catalogues through its
        plugins, so updating the plugins is the closest equivalent to the
        package-list refresh other managers perform during sync.

        .. code-block:: shell-session

            $ mise plugins update
        """
        self.run_cli("plugins", "update")

    def cleanup_cache(self) -> None:
        """Clear ``mise``'s download and metadata caches.

        .. code-block:: shell-session

            $ mise cache clear
        """
        self.run_cli("cache", "clear")

    def doctor_cli(self) -> tuple[str, ...]:
        """Generates the CLI running the native self-diagnosis.

        .. code-block:: shell-session

            $ mise doctor
        """
        return self.build_cli("doctor")
