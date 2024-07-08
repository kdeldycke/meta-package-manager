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
from typing import Iterator

from click_extra.platforms import ALL_PLATFORMS

from meta_package_manager.base import Package, PackageManager


class UV(PackageManager):
    homepage_url = "https://astral.sh"

    platforms = ALL_PLATFORMS

    requirement = "0.1.45"
    """`v0.1.45 <https://github.com/astral-sh/uv/releases/tag/0.1.45>`_ is the first
    version to support ``--format=json`` parameter.
    """

    pre_args = ("--color", "never")
    """
          ```text
          --color <COLOR_CHOICE>
          Control colors in output

          [default: auto]

          Possible values:
          - auto:   Enables colored output only when the output is going to a terminal or TTY with support
          - always: Enables colored output regardless of the detected environment
          - never:  Disables colored output
          ```
    """

    version_regex = r"uv\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► uv --version
        uv 0.2.21 (ebfe6d8fc 2024-07-03)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► uv --color never pip list --format=json | jq
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

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► uv pip install "tomli_w == 1.0.0"
            Resolved 1 package in 574ms
            Installed 1 package in 2ms
             + tomli-w==1.0.0
        """
        package_specs = package_id
        if version:
            package_specs += f" == {version}"
        return self.run_cli("pip", "install", f'"{package_specs}"')

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            ► uv pip install --upgrade "tomli_w == 0.4.0"
            Resolved 1 package in 1ms
            Uninstalled 1 package in 0.54ms
            Installed 1 package in 0.94ms
             - tomli-w==0.2.0
             + tomli-w==0.4.0

        .. code-block:: shell-session

            ► uv pip install --upgrade "tomli_w"
            Resolved 1 package in 2ms
            Uninstalled 1 package in 1ms
            Installed 1 package in 2ms
             - tomli-w==0.4.0
             + tomli-w==1.0.0
        """
        package_specs = package_id
        if version:
            package_specs += f" == {version}"
        return self.build_cli("pip", "install", "--upgrade", f'"{package_specs}"')

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► uv pip uninstall tomli_w
            Uninstalled 1 package in 5ms
             - tomli-w==1.0.0
        """
        return self.run_cli("pip", "uninstall", package_id)
