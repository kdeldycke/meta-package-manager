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

from operator import attrgetter

from extra_platforms import ALL_PLATFORMS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Pipx(PackageManager):
    """pipx installs Python CLI applications, each in its own isolated venv."""

    name = "Python pipx"

    homepage_url = "https://pipx.pypa.io"

    platforms = ALL_PLATFORMS

    requirement = ">=1.0.0"
    """
    .. code-block:: shell-session

        $ pipx --version
        1.0.0
    """

    cooldown_env_var = "PIP_UPLOADED_PRIOR_TO"
    """pipx defers resolution to pip, so it honors pip's ``--uploaded-prior-to``
    gate through the same environment variable.

    Setting ``PIP_UPLOADED_PRIOR_TO`` on a pipx invocation propagates to the pip
    subprocess pipx spawns to install the application and its dependencies, so the
    cutoff applies to the whole resolution. mpm injects the RFC 3339 timestamp from
    the default :py:meth:`meta_package_manager.execution.CLIExecutor.cooldown_env_value`.

    .. caution::
        Same caveat as :py:class:`meta_package_manager.managers.pip.Pip`: the
        underlying pip must be at least ``26.1`` for the gate to take effect. Older
        pip releases silently ignore the env var.

    See https://github.com/pypa/pipx/issues/1811.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ pipx list --json | jq
            {
              "pipx_spec_version": "0.1",
              "venvs": {
                  "pycowsay": {
                    "metadata": {
                      "injected_packages": {},
                      "main_package": {
                        "app_paths": [
                          {
                            "__Path__": "~/.local/pipx/venvs/pycowsay/bin/pycowsay",
                            "__type__": "Path"
                          }
                        ],
                        "app_paths_of_dependencies": {},
                        "apps": [
                          "pycowsay"
                        ],
                        "apps_of_dependencies": [],
                        "include_apps": true,
                        "include_dependencies": false,
                        "package": "pycowsay",
                        "package_or_url": "pycowsay",
                        "package_version": "0.0.0.1",
                        "pip_args": [],
                        "suffix": ""
                      },
                    "pipx_metadata_version": "0.2",
                    "python_version": "Python 3.10.4",
                    "venv_args": []
                  }
                }
              }
            }
        """
        output = self.run_cli("list", "--json", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for package_id, package_info in data["venvs"].items():
                yield self.package(
                    id=package_id,
                    installed_version=package_info["metadata"]["main_package"][
                        "package_version"
                    ],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. todo::

            Mimics ``Pip.outdated()`` operation. There probably is a way to factorize
            it.

        Only the venv's main package is reported; its dependencies also show up
        in ``pip list --outdated`` but are silenced:

        .. code-block:: shell-session

            $ pipx runpip pycowsay list --no-color --format=json --outdated \
            > --verbose --quiet | jq
            [
              {
                "name": "pycowsay",
                "version": "0.0.0.1",
                "location": "~/.local/pipx/venvs/pycowsay/lib/python3.10/site-packages",
                "installer": "pip",
                "latest_version": "0.0.0.2",
                "latest_filetype": "wheel"
              }
            ]
        """
        for main_package_id in map(attrgetter("id"), self.installed):
            # --quiet is required here to silence warning and error messages
            # mangling the JSON content.
            output = self.run_cli(
                "runpip",
                main_package_id,
                "list",
                "--no-color",
                "--format=json",
                "--outdated",
                "--verbose",
                "--quiet",
                must_succeed=True,
            )

            data = self.parse_json(output)
            if data:
                for sub_package in data:
                    # Only report the main package as outdated, silencing its
                    # dependencies.
                    sub_package_id = sub_package["name"]
                    if sub_package_id == main_package_id:
                        yield self.package(
                            id=sub_package_id,
                            installed_version=sub_package["version"],
                            latest_version=sub_package["latest_version"],
                        )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ pipx install pycowsay
            installed package pycowsay 0.0.0.1, installed using Python 3.10.4
            These apps are now globally available
                - pycowsay
            done! ✨ 🌟 ✨
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Upgrade all packages."""
        return self.build_cli("upgrade-all")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Upgrade the package provided as parameter."""
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ pipx uninstall pycowsay
            uninstalled pycowsay! ✨ 🌟 ✨
        """
        return self.run_cli("uninstall", package_id)
