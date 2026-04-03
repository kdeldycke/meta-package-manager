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

from extra_platforms import LINUX_LIKE, MACOS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class Nix(PackageManager):
    """Nix package manager.

    .. note::
        All operations use the imperative ``nix-env`` interface, which manages
        a per-user package profile. Declarative approaches (NixOS modules,
        home-manager) are not covered.
    """

    homepage_url = "https://nixos.org"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=2.0.0"

    cli_names = ("nix-env",)

    version_regexes = (r"nix-env \(Nix\) (?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ nix-env --version
        nix-env (Nix) 2.18.1
    """

    _NAME_VERSION_REGEXP = re.compile(
        r"^(?P<package_id>.+)-(?P<version>\d\S*)$",
    )
    """Split a Nix derivation name into package name and version.

    Nix convention: version starts after the last hyphen followed by a digit.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<name_version>\S+)\s+<\s+(?P<latest_version>\S+)",
        re.MULTILINE,
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ nix-env --query --installed
            hello-2.12.1
            nix-2.18.1
            python3-3.11.6
        """
        output = self.run_cli("--query", "--installed")

        for line in output.splitlines():
            match = self._NAME_VERSION_REGEXP.match(line.strip())
            if match:
                yield self.package(
                    id=match.group("package_id"),
                    installed_version=match.group("version"),
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ nix-env --query --upgradeable --compare-versions
            hello-2.12.1 < 2.13.0
            python3-3.11.6 < 3.12.0
        """
        output = self.run_cli(
            "--query",
            "--upgradeable",
            "--compare-versions",
        )

        for match in self._OUTDATED_REGEXP.finditer(output):
            name_match = self._NAME_VERSION_REGEXP.match(
                match.group("name_version"),
            )
            if name_match:
                yield self.package(
                    id=name_match.group("package_id"),
                    installed_version=name_match.group("version"),
                    latest_version=match.group("latest_version"),
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we return
            the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`
            refine them.

        .. caution::
            ``nix-env --query --available`` evaluates the full nixpkgs set and
            can be slow on first invocation.

        .. code-block:: shell-session

            $ nix-env --query --available --attr-path --description 'hello'
            nixpkgs.hello  hello-2.12.1  A program that produces a friendly greeting
        """
        output = self.run_cli(
            "--query",
            "--available",
            "--attr-path",
            "--description",
            query,
        )

        for line in output.splitlines():
            # Columns are padded with variable whitespace (2+ spaces).
            parts = re.split(r"\s{2,}", line.strip(), maxsplit=2)
            if len(parts) < 2:
                continue
            name_version = parts[1]
            description = parts[2] if len(parts) > 2 else None

            name_match = self._NAME_VERSION_REGEXP.match(name_version)
            if name_match:
                yield self.package(
                    id=name_match.group("package_id"),
                    description=description,
                    latest_version=name_match.group("version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ nix-env --install hello
        """
        return self.run_cli("--install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ nix-env --upgrade
        """
        return self.build_cli("--upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ nix-env --upgrade hello
        """
        return self.build_cli("--upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ nix-env --uninstall hello
        """
        return self.run_cli("--uninstall", package_id)

    def sync(self) -> None:
        """Update Nix channel metadata.

        .. code-block:: shell-session

            $ nix-channel --update
        """
        assert self.cli_path is not None
        self.run_cli(
            "--update",
            override_cli_path=self.cli_path.parent / "nix-channel",
        )

    def cleanup(self) -> None:
        """Remove old generations and garbage-collect the Nix store.

        .. code-block:: shell-session

            $ nix-collect-garbage --delete-old
        """
        assert self.cli_path is not None
        self.run_cli(
            "--delete-old",
            override_cli_path=self.cli_path.parent / "nix-collect-garbage",
        )
