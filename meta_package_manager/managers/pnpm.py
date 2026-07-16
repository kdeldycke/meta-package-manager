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


from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class PNPM(PackageManager):
    """See command equivalences at:
    https://github.com/antfu-collective/ni?tab=readme-ov-file#ni.

    .. note::

        All operations target the global scope via ``--global``, like the
        :py:class:`meta_package_manager.managers.npm.NPM` manager.
    """

    name = "Node pnpm"

    homepage_url = "https://pnpm.io"

    platforms = ALL_PLATFORMS

    requirement = ">=11.0.0"
    """`11.0.0 <https://github.com/pnpm/pnpm/releases/tag/v11.0.0>`_ is the first
    version to ship the ``search`` subcommand. It also clears the ``10.16.0`` floor of
    ``minimumReleaseAge``, the release-age gate mpm drives for the supply-chain
    cooldown (see :py:attr:`cooldown_env_var`), so a single floor covers every
    advertised operation. Older pnpm releases either lack ``search`` or silently
    ignore the cooldown setting.
    """

    cooldown_env_var = "pnpm_config_minimum_release_age"
    """pnpm honors a release-age cooldown through its ``minimumReleaseAge`` setting.

    pnpm reads any setting from an environment variable built by snake-casing the
    setting name behind a ``pnpm_config_`` prefix (the docs render ``pmOnFail`` as
    ``pnpm_config_pm_on_fail``), so ``pnpm_config_minimum_release_age`` sets
    ``minimumReleaseAge`` without touching ``pnpm-workspace.yaml``. Once set, pnpm
    refuses to install any version published more recently than the configured age,
    across direct and transitive dependencies.

    ``minimumReleaseAge`` is expressed in minutes, so :py:meth:`cooldown_env_value`
    is overridden to emit a minute count.

    See https://pnpm.io/settings#minimumreleaseage.
    """

    def cooldown_env_value(self) -> str:
        """Render :py:attr:`meta_package_manager.execution.CLIExecutor.cooldown` as an
        integer minute count for pnpm's ``minimumReleaseAge``.

        Sub-minute cooldowns round up so the gate over-protects rather than silently
        collapsing to ``0`` (the "no cooldown" sentinel).
        """
        return self.cooldown_rounded_up(60)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ``pnpm list --json`` returns an array of project objects; the global scope
        resolves to a single one whose ``dependencies`` map holds the installed
        packages.

        .. code-block:: shell-session

            $ pnpm list --global --json --depth 0
            [
              {
                "name": "global",
                "dependencies": {
                  "eslint": {
                    "from": "eslint",
                    "version": "9.15.0"
                  },
                  "typescript": {
                    "from": "typescript",
                    "version": "5.6.3"
                  }
                }
              }
            ]
        """
        output = self.run_cli(
            "list", "--global", "--json", "--depth", "0", must_succeed=True
        )

        data = self.parse_json(output)
        if data:
            for project in data:
                for pkg_id, pkg_infos in project.get("dependencies", {}).items():
                    yield self.package(
                        id=pkg_id,
                        installed_version=pkg_infos["version"],
                    )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ``pnpm outdated`` exits with code ``1`` when it finds outdated packages, but
        writes the report to ``<stdout>`` and leaves ``<stderr>`` empty. Passing
        ``must_succeed`` keeps the lenient failure gate that tolerates a non-zero
        exit with an empty ``<stderr>`` as a benign status code, so the call does
        not raise (see :py:meth:`meta_package_manager.execution.CLIExecutor.run`).

        .. code-block:: shell-session

            $ pnpm outdated --global --json
            {
              "eslint": {
                "current": "9.10.0",
                "latest": "9.15.0",
                "wanted": "9.15.0",
                "isDeprecated": false,
                "dependencyType": "dependencies"
              }
            }
        """
        output = self.run_cli("outdated", "--global", "--json", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg_id, pkg_infos in data.items():
                yield self.package(
                    id=pkg_id,
                    installed_version=pkg_infos.get("current"),
                    latest_version=pkg_infos["latest"],
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        pnpm queries the registry's ``/-/v1/search`` endpoint and, with ``--json``,
        emits an array of the matched packages (an empty ``[]`` when none match).

        .. caution::
            Search does not support exact matching: the registry endpoint matches on
            names, descriptions and keywords, so the framework refilters the raw
            results for exact queries.

        .. code-block:: shell-session

            $ pnpm search --json is-positive
            [
              {
                "name": "is-positive",
                "version": "3.1.0",
                "description": "Check if something is a positive number",
                "date": "2017-10-24T15:24:08.180Z",
                "maintainers": [
                  {
                    "username": "sindresorhus"
                  }
                ]
              }
            ]
        """
        output = self.run_cli("search", "--json", query, must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg_infos in data:
                yield self.package(
                    id=pkg_infos["name"],
                    description=pkg_infos.get("description"),
                    latest_version=pkg_infos["version"],
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ pnpm add --global markdown
        """
        return self.run_cli("add", "--global", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ pnpm update --global --latest
        """
        return self.build_cli("update", "--global", "--latest")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ pnpm update --global --latest markdown
        """
        return self.build_cli("update", "--global", "--latest", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ pnpm remove --global markdown
        """
        return self.run_cli("remove", "--global", package_id)

    def cleanup(self) -> None:
        """Remove orphan packages from the global content-addressable store.

        .. code-block:: shell-session

            $ pnpm store prune
        """
        self.run_cli("store", "prune")
