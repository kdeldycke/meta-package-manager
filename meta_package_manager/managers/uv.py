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

from extra_platforms import ALL_PLATFORMS

from ..base import Package, PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class UVBase(PackageManager):
    """Virtual package manager shared by ``UV`` and ``UVX`` CLI defined below.

    .. hint::
        Package spec are not quoted anywhere here to `workaround issues
        <https://github.com/kdeldycke/meta-package-manager/issues/1653>`_ with how `uv`
        fails to parses them sometimes.
    """

    homepage_url = "https://docs.astral.sh/uv"

    requirement = "0.5.0"
    """`0.5.0 <https://github.com/astral-sh/uv/releases/tag/0.5.0>`_ is the first
    version to introduce ``pip list --outdated`` command.
    """

    platforms = ALL_PLATFORMS

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    virtual = True

    pre_args = ("--color", "never", "--no-progress")
    """
    - ``--color color-choice``
        Control colors in output [default: ``auto``]

        Possible values:
        - ``auto``: Enables colored output only when the output is going to a terminal or TTY with support
        - ``always``: Enables colored output regardless of the detected environment
        - ``never``: Disables colored output

    - ``--no-progress``
        Hide all progress outputs.

        For example, spinners or progress bars.
    """

    version_regexes = (r"uv\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ uv --version
        uv 0.2.21 (ebfe6d8fc 2024-07-03)
    """

    def _build_package_spec(self, package_id: str, version: str | None = None) -> str:
        """Build package specification with optional version constraint."""
        package_specs = package_id
        if version:
            package_specs += f"=={version}"
        return package_specs


class UV(UVBase):
    """Python package manager using uv pip commands."""

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ uv --color never --no-progress pip list --format=json | jq
            [
              {
                "name": "markupsafe",
                "version": "2.1.5"
              },
              {
                "name": "meta-package-manager",
                "version": "5.17.0",
                "editable_project_location": "/Users/kde/meta-package-manager"
              },
              {
                "name": "myst-parser",
                "version": "3.0.1"
              },
              (...)
            ]
        """
        output = self.run_cli("pip", "list", "--format=json")

        if output:
            for package in json.loads(output):
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ uv --color never --no-progress pip list --outdated --format=json | jq
            [
              {
                "name": "lark-parser",
                "version": "0.7.8",
                "latest_version": "0.12.0",
                "latest_filetype": "wheel"
              },
              {
                "name": "types-setuptools",
                "version": "75.3.0.20241107",
                "latest_version": "75.3.0.20241112",
                "latest_filetype": "wheel"
              }
            ]
        """
        output = self.run_cli("pip", "list", "--outdated", "--format=json")

        if output:
            for package in json.loads(output):
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                    latest_version=package["latest_version"],
                )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ uv --color never --no-progress pip install arrow
        """
        package_specs = self._build_package_spec(package_id, version)
        return self.run_cli("pip", "install", package_specs)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ uv --color never --no-progress pip install --upgrade arrow
        """
        package_specs = self._build_package_spec(package_id, version)
        return self.build_cli("pip", "install", "--upgrade", package_specs)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ uv --color never --no-progress pip uninstall arrow
        """
        return self.run_cli("pip", "uninstall", package_id)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ uv --color never --no-progress cache clean
            Clearing cache at: /Users/kde/Library/Caches/uv
            Removed 97279 files (2.0GiB)

        .. code-block:: shell-session

            $ uv --color never --no-progress cache prune
            No cache found at: /Users/kde/.cache/uv
        """
        self.run_cli("cache", "clean")
        self.run_cli("cache", "prune")


class UVX(UVBase):
    """UV tool manager for isolated Python tools.

    Like ``pipx``, but uses ``uv tool`` commands.
    """

    cli_names = ("uv",)

    homepage_url = "https://docs.astral.sh/uv/guides/tools/"

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ uv --color never --no-progress tool list
            pycowsay v0.0.0.1
            - pycowsay
        """
        output = self.run_cli("tool", "list")

        if output:
            # Parse lines like "package_name vX.Y.Z"
            package_regex = re.compile(r"^(?P<package_id>\S+)\s+v(?P<version>\S+)$")
            for line in output.splitlines():
                match = package_regex.match(line)
                if match:
                    yield self.package(
                        id=match.group("package_id"),
                        installed_version=match.group("version"),
                    )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ uv --color never --no-progress tool install pycowsay
        """
        package_specs = self._build_package_spec(package_id, version)
        return self.run_cli("tool", "install", package_specs)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ uv --color never --no-progress tool upgrade pycowsay
        """
        package_specs = self._build_package_spec(package_id, version)
        return self.build_cli("tool", "upgrade", package_specs)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ uv --color never --no-progress tool upgrade --all
            Updated pycowsay v0.0.0.1 -> v0.0.0.2
                - pycowsay
        """
        return self.build_cli("tool", "upgrade", "--all")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ uv --color never --no-progress tool uninstall pycowsay
        """
        return self.run_cli("tool", "uninstall", package_id)
