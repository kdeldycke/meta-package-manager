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
from boltons.cacheutils import cachedproperty
from click_extra.logging import logger
from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..version import parse_version


class Yarn(PackageManager):

    name = "Node's yarn"

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    requirement = "1.21.0"

    """
    .. code-block:: shell-session

        ► yarn --version
        1.22.11
    """

    def parse(self, output):
        packages = {}

        if not output:
            return packages

        for line in output.splitlines():
            if not line:
                continue
            obj = json.loads(line)
            if obj["type"] != "info":
                continue
            package = self.parse_info(obj)
            packages[package["id"]] = package
        return packages

    @staticmethod
    def parse_info(obj):
        data = obj["data"].replace("has binaries:", "")
        parts = data.replace('"', "").split("@")
        package_id = parts[0]
        version = parts[1]
        return {
            "id": package_id,
            "name": package_id,
            "installed_version": parse_version(version),
        }

    @property
    def installed(self):
        """Fetch installed packages from ``yarn list`` output.

        .. code-block:: shell-session

            ► yarn global --json list --depth 0
            (...)
        """
        output = self.run_cli("global", "--json", "list", "--depth", "0")
        return self.parse(output)

    def search(self, query, extended, exact):
        """Call ``yarn info`` and only works for exact match.

        Yarn maintainers have decided not to implement a dedicated ``search``
        command:
        https://github.com/yarnpkg/yarn/issues/778#issuecomment-253146299

        .. code-block:: shell-session

            ► yarn --json info python | jq
            {
              "type": "inspect",
              "data": {
                "name": "python",
                "description": "Interact with python child process",
                "dist-tags": {
                  "latest": "0.0.4"
                },
                "versions": [
                  "0.0.0",
                  "0.0.1",
                  "0.0.2",
                  "0.0.3",
                  "0.0.4"
                ],
                "maintainers": [
                  {
                    "name": "drderidder",
                    "email": "drderidder@gmail.com"
                  }
                ],
                "time": {
                  "modified": "2017-09-16T05:26:13.151Z",
                  "created": "2011-07-11T01:59:04.362Z",
                  "0.0.0": "2011-07-11T01:59:05.137Z",
                  "0.0.1": "2011-07-17T05:23:33.166Z",
                  "0.0.2": "2011-07-20T03:42:50.379Z",
                  "0.0.3": "2014-06-08T00:39:08.562Z",
                  "0.0.4": "2015-01-25T02:48:07.820Z"
                },
                "author": {
                  "name": "Darren DeRidder"
                },
                "repository": {
                  "type": "git",
                  "url": "git://github.com/73rhodes/node-python.git"
                },
                "homepage": "https://github.com/73rhodes/node-python",
                "bugs": {
                  "url": "https://github.com/73rhodes/node-python/issues"
                },
                "readmeFilename": "README.md",
                "users": {
                  "dewang-mistry": true,
                  "goliatone": true,
                  "sapanbhuta": true,
                  "aditcmarix": true,
                  "imlucas": true,
                  "heyderpd": true,
                  "ukuli": true,
                  "chbardel": true,
                  "asaupup": true,
                  "nuwaio": true
                },
                "version": "0.0.4",
                "main": "./lib/python.js",
                "engines": {
                  "node": ">= 0.4.1"
                },
                "gitHead": "69754aaa57658193916a1bf5fc391198098f74f6",
                "scripts": {},
                "dist": {
                  "shasum": "3094e898ef17a33aa9c3e973b3848a38e47d1818",
                  "tarball": "https://registry.npmjs.org/python/-/python-1.tgz"
                },
                "directories": {}
              }
            }
        """
        matches = {}

        if extended:
            logger.warning(
                f"Extended search not supported for {self.id}. Fallback to Fuzzy."
            )
        elif not exact:
            logger.warning(
                f"Fuzzy search not supported for {self.id}. Fallback to Exact."
            )

        output = self.run_cli("--json", "info", query)

        if output:
            result = json.loads(output)

            if result["type"] == "inspect":
                package = result["data"]
                package_id = package["name"]
                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(package["version"]),
                }

        return matches

    @cachedproperty
    def global_dir(self):
        return self.run_cli("global", "dir", force_exec=True).rstrip()

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► yarn install python

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``yarn outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► yarn --json outdated --cwd
            (...)
        """
        outdated = {}

        output = self.run_cli("--json", "outdated", "--cwd", self.global_dir)

        if not output:
            return outdated

        packages = []
        for line in output.splitlines():
            if not line:
                continue
            obj = json.loads(line)
            if obj["type"] == "table":
                packages = obj["data"]["body"]
                break

        for package in packages:
            package_id = package[0]
            values = {"current": package[1], "wanted": package[2], "latest": package[3]}

            if values["wanted"] == "linked":
                continue
            outdated[package_id] = {
                "id": package_id + "@" + values["latest"],
                "name": package_id,
                "installed_version": parse_version(values["current"]),
                "latest_version": parse_version(values["latest"]),
            }
        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, "global"]

        if package_id:
            cmd.append("add")
            cmd.append(package_id)
        else:
            cmd.append("upgrade")

        return cmd

    def cleanup(self):
        """Remove the shared cache files.

        See: https://yarnpkg.com/cli/cache/clean
        """
        super().cleanup()
        self.run_cli("cache", "clean", "--all")
