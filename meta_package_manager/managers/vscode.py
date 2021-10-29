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

import simplejson as json
from boltons.iterutils import remap
from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..version import TokenizedString, parse_version


class VSCode(PackageManager):

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    requirement = "1.60.0"

    name = "Visual Studio Code"

    cli_names = ("code",)

    """
    .. code-block:: shell-session

        ► code --version
        1.60.2
        7f6ab5485bbc008386c4386d08766667e155244e
        x64
    """

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► code --list-extensions --show-versions
            ms-python.python@2021.9.1246542782
            ms-python.vscode-pylance@2021.9.3
            ms-toolsai.jupyter@2021.8.2041215044
            ms-toolsai.jupyter-keymap@1.0.0
            samuelcolvin.jinjahtml@0.16.0
            tamasfe.even-better-toml@0.14.2
            trond-snekvik.simple-rst@1.5.0
        """
        installed = {}

        output = self.run_cli("--list-extensions", "--show-versions")

        if output:
            for package in output.splitlines():
                package_id, installed_version = package.split("@")
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(installed_version),
                }

        return installed

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► code --install-extension tamasfe.even-better-toml
        """
        super().install(package_id)
        return self.run_cli("--install-extension", package_id)
