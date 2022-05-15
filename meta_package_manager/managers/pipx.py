# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import json

from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..version import parse_version


class Pipx(PackageManager):

    platforms = frozenset({MACOS, LINUX, WINDOWS})

    requirement = "1.0.0"
    """
    .. code-block:: shell-session

        ► pipx --version
        1.0.0
    """

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► pipx list --json | jq
            {
              "pipx_spec_version": "0.1",
              "venvs": {
                  "pycowsay": {
                    "metadata": {
                      "injected_packages": {},
                      "main_package": {
                        "app_paths": [
                          {
                            "__Path__": "/Users/kde/.local/pipx/venvs/pycowsay/bin/pycowsay",
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
        installed = {}

        output = self.run_cli("list", "--json")

        if output:
            for package_id, package_info in json.loads(output)["venvs"].items():
                package_version = package_info["metadata"]["main_package"][
                    "package_version"
                ]
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package_version),
                }

        return installed

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► pipx install pycowsay
            installed package pycowsay 0.0.0.1, installed using Python 3.10.4
            These apps are now globally available
                - pycowsay
            done! ✨ 🌟 ✨
        """
        return self.run_cli("install", package_id)

    def upgrade_cli(self, package_id):
        """Upgrade the package provided as parameter."""
        return self.build_cli("upgrade", package_id)

    def upgrade_all_cli(self):
        """Upgrade all packages."""
        return self.build_cli("upgrade-all")

    def remove(self, package_id):
        """Remove one package.

        .. code-block:: shell-session

            ► pipx uninstall pycowsay
            uninstalled pycowsay! ✨ 🌟 ✨
        """
        return self.run_cli("uninstall", package_id)