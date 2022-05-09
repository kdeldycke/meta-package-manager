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
from ..version import  parse_version


class Pipx(PackageManager):
    platforms = frozenset({MACOS, LINUX, WINDOWS})

    requirement = "1.0.0"

    @property
    def installed(self):
        """Fetch installed packages."""
        installed = {}
  
        output = self.run_cli("list", "--json")

        if output:
            for package_id, package_info in json.loads(output)["venvs"].items():
                package_version = package_info["metadata"]["main_package"]["package_version"]
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package_version),
                }

        return installed

    def install(self, package_id):
        """Install one package."""
        return self.run_cli("install", package_id)

    def upgrade_cli(self, package_id):
        """Upgrade the package provided as parameter."""
        return self.build_cli("upgrade", package_id)

    def upgrade_all_cli(self):
        """Upgrade all packages."""
        raise self.build_cli("upgrade-all")
