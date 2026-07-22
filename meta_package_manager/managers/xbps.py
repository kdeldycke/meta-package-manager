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

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class XBPS(PackageManager):
    """X Binary Package System used by Void Linux.

    .. note::
        XBPS is split across several sibling binaries: ``xbps-query`` for
        read-only operations, ``xbps-install`` for installs, sync and
        upgrades, and ``xbps-remove`` for uninstalls and cache cleanup.
        ``mpm`` resolves the siblings from the same directory as
        :py:attr:`cli_path
        <meta_package_manager.execution.CLIExecutor.cli_path>`.
    """

    name = "Void XBPS"

    homepage_url = "https://github.com/void-linux/xbps"

    platforms = LINUX_LIKE

    default_sudo = True

    requirement = ">=0.59"
    """Version 0.59 is the first to ship the long-form options
    (``--list-pkgs``, ``--repository``, ``--search``, ``--update``,
    ``--dry-run``, ``--sync``, ``--yes``, ``--clean-cache``,
    ``--remove-orphans``) that the methods below depend on.
    """

    cli_names = ("xbps-install",)
    """Use ``xbps-install`` as the canonical entry point.

    The other XBPS binaries (``xbps-query``, ``xbps-remove``) are looked up
    in the same directory as ``xbps-install`` via
    :py:attr:`cli_path
    <meta_package_manager.execution.CLIExecutor.cli_path>`.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^ii\s+(?P<pkgver>\S+)\s+(?P<description>.+)$",
        re.MULTILINE,
    )
    """Match installed entries from ``xbps-query --list-pkgs`` output.

    The first column is a two-character state code: ``ii`` (installed),
    ``uu`` (unpacked, awaiting configuration), ``hr`` (half-removed) or
    ``??`` (unknown). Only ``ii`` packages are reported as installed.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<pkgver>\S+)\s+update\s+\S+\s+\S+\s+\S+\s+\S+\s*$",
        re.MULTILINE,
    )
    """Match update entries from ``xbps-install --update --dry-run`` output.

    Each line has the format
    ``<pkgver> <action> <arch> <repository> <installedsize> <downloadsize>``.
    Only ``update`` actions are kept, skipping ``install``, ``configure`` and
    ``remove`` entries that may also appear in a transaction.
    """

    _SEARCH_REGEXP = re.compile(
        r"^\[[\*\-]\]\s+(?P<pkgver>\S+)\s+(?P<description>.+)$",
        re.MULTILINE,
    )
    """Match search entries from ``xbps-query --repository --search`` output.

    Each line is prefixed with ``[*]`` (already installed) or ``[-]``
    (available in the repository).
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ xbps-query --list-pkgs
            ii base-files-0.144_1            Void Linux base system files
            ii cmark-gfm-0.29.0.gfm.13_1     CommonMark parsing and rendering library
            ii curl-8.5.0_1                  Command line tool for transferring data
        """
        output = self.run_cli(
            "--list-pkgs",
            override_cli_path=self.sibling_cli("xbps-query", same_dir=True),
        )

        for match in self._INSTALLED_REGEXP.finditer(output):
            if split := self.split_name_version(match.group("pkgver")):
                package_id, version = split
                yield self.package(
                    id=package_id,
                    description=match.group("description").strip(),
                    installed_version=version,
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. caution::
            Reads from the local repository cache. Run :py:meth:`sync` first
            to refresh the index.

        .. code-block:: shell-session

            $ xbps-install --update --dry-run
            firefox-120.0_1 update x86_64 https://repo-default.voidlinux.org/current 45MB 12MB
            python3-3.11.6_2 update x86_64 https://repo-default.voidlinux.org/current 30MB 8MB
        """
        installed_versions = self.installed_version_map

        output = self.run_cli("--update", "--dry-run")

        for match in self._OUTDATED_REGEXP.finditer(output):
            if split := self.split_name_version(match.group("pkgver")):
                package_id, version = split
                yield self.package(
                    id=package_id,
                    installed_version=installed_versions.get(package_id),
                    latest_version=version,
                )

    @property
    def orphans(self) -> Iterator[Package]:
        """Fetch packages installed as dependencies that nothing requires anymore.

        .. code-block:: shell-session

            $ xbps-query --list-orphans
            libglvnd-1.7.0_1
            orc-0.4.34_1
        """
        output = self.run_cli(
            "--list-orphans",
            override_cli_path=self.sibling_cli("xbps-query", same_dir=True),
        )

        for token in output.splitlines():
            if split := self.split_name_version(token.strip()):
                package_id, version = split
                yield self.package(id=package_id, installed_version=version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            ``xbps-query --search`` matches against ``pkgver`` and
            ``short_desc`` properties at the same time. Extended and exact
            matching are not supported, so the best subset of results is
            returned and refined later by
            :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`.

        .. code-block:: shell-session

            $ xbps-query --repository --search firefox
            [-] firefox-120.0_1            Standalone web browser from mozilla.org
            [*] firefox-esr-115.5.0_1      Extended support release of Firefox
        """
        output = self.run_cli(
            "--repository",
            "--search",
            query,
            override_cli_path=self.sibling_cli("xbps-query", same_dir=True),
        )

        for match in self._SEARCH_REGEXP.finditer(output):
            if split := self.split_name_version(match.group("pkgver")):
                package_id, version = split
                yield self.package(
                    id=package_id,
                    description=match.group("description").strip(),
                    latest_version=version,
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo xbps-install --yes firefox
        """
        return self.run_cli("--yes", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ sudo xbps-install --sync --update --yes
        """
        return self.build_cli("--sync", "--update", "--yes", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ sudo xbps-install --update --yes firefox
        """
        return self.build_cli("--update", "--yes", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        .. code-block:: shell-session

            $ sudo xbps-remove --yes firefox
        """
        return self.run_cli(
            "--yes",
            package_id,
            override_cli_path=self.sibling_cli("xbps-remove", same_dir=True),
            sudo=True,
        )

    def remove_orphan(self, package_id: str) -> str:
        """Remove one package, recursively dropping orphaned dependencies.

        .. code-block:: shell-session

            $ sudo xbps-remove --recursive --yes firefox
        """
        return self.run_cli(
            "--recursive",
            "--yes",
            package_id,
            override_cli_path=self.sibling_cli("xbps-remove", same_dir=True),
            sudo=True,
        )

    def sync(self) -> None:
        """Synchronize remote repository indexes.

        .. code-block:: shell-session

            $ sudo xbps-install --sync --yes
        """
        self.run_cli("--sync", "--yes", sudo=True)

    def cleanup(self) -> None:
        """Remove orphaned packages and clean the binary package cache.

        .. code-block:: shell-session

            $ sudo xbps-remove --remove-orphans --clean-cache --yes
        """
        self.run_cli(
            "--remove-orphans",
            "--clean-cache",
            "--yes",
            override_cli_path=self.sibling_cli("xbps-remove", same_dir=True),
            sudo=True,
        )

    def cleanup_orphan(self) -> None:
        """Remove installed packages no longer required by any other, sparing the cache.

        .. code-block:: shell-session

            $ sudo xbps-remove --remove-orphans --yes
        """
        self.run_cli(
            "--remove-orphans",
            "--yes",
            override_cli_path=self.sibling_cli("xbps-remove", same_dir=True),
            sudo=True,
        )
