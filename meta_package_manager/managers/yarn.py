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
from functools import cached_property

from extra_platforms import ALL_PLATFORMS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class Yarn(PackageManager):
    """Virtual package manager shared by Yarn Classic and Yarn Berry.

    See command equivalences at:
    https://github.com/antfu-collective/ni?tab=readme-ov-file#ni
    """

    homepage_url = "https://yarnpkg.com"

    platforms = ALL_PLATFORMS

    virtual = True

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        See: https://yarnpkg.com/cli/cache/clean

        .. code-block:: shell-session

            $ yarn cache clean --all
            yarn cache v1.22.19
            success Cleared cache.
            ✨  Done in 0.35s.
        """
        self.run_cli("cache", "clean", "--all")


class YarnClassic(Yarn):
    """Yarn Classic (1.x) package manager.

    .. warning::
        Yarn Classic has been in maintenance mode since January 2020. Only
        critical and security patches are accepted. Yarn Berry (2.x+) is
        the actively developed line but uses a fundamentally different CLI
        surface, so it is handled by a separate
        :py:class:`YarnBerry` manager.
    """

    id = "yarn"

    name = "Yarn Classic"

    requirement = ">=1.20.0,<2.0.0"

    cli_names = ("yarn",)

    pre_args = ("--silent",)

    _INSTALLED_REGEXP = re.compile(
        r"^.+\"data\":\"\\\"(?P<package_id>\S+)"
        r"@(?P<version>\S+)\\\" has binaries:\"\}$",
        re.MULTILINE,
    )

    """
    .. code-block:: shell-session

        $ yarn --version
        1.22.11
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ yarn global --json list --depth 0
            {"type":"activityStart","data":{"id":0}}
            {"type":"activityTick","data":{"id":0,"name":"awesome-lint@^0.18.0"}}
            {"type":"activityTick","data":{"id":0,"name":"arrify@^2.0.1"}}
            {"type":"activityTick","data":{"id":0,"name":"case@^1.6.3"}}
            {"type":"activityTick","data":{"id":0,"name":"emoji-regex@^9.2.0"}}
            (...)
            {"type":"activityEnd","data":{"id":0}}
            {"type":"progressStart","data":{"id":0,"total":327}}
            {"type":"progressTick","data":{"id":0,"current":1}}
            {"type":"progressTick","data":{"id":0,"current":2}}
            {"type":"progressTick","data":{"id":0,"current":3}}
            {"type":"progressTick","data":{"id":0,"current":4}}
            {"type":"progressTick","data":{"id":0,"current":5}}
            (...)
            {"type":"progressFinish","data":{"id":0}}
            {"type":"info","data":"\"awesome-lint@0.18.0\" has binaries:"}
            {"type":"list","data":{"type":"bins-awesome-lint","items":["awesome-lint"]}}

        .. code-block:: shell-session

            $ yarn global list --depth 0
            yarn global v1.22.19
            info "awesome-lint@0.18.0" has binaries:
               - awesome-lint
            ✨  Done in 0.13s.
        """
        output = self.run_cli(
            "global", "--json", "list", "--depth", "0", must_succeed=True
        )

        for package_id, version in self._INSTALLED_REGEXP.findall(output):
            yield self.package(id=package_id, installed_version=version)

    @cached_property
    def global_dir(self) -> str:
        """Locate the global directory.

        .. code-block:: shell-session

            $ yarn global dir
            ~/.config/yarn/global
        """
        return self.run_cli("global", "dir", force_exec=True).rstrip()

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ yarn --json outdated --cwd ~/.config/yarn/global | jq
            {"type":"warning","data":"package.json: No license field"}
            {
              "type": "info",
              "data":
                "Color legend : \\n"
                " \\"<red>\\"    : Major Update backward-incompatible updates \\n"
                " \\"<yellow>\\" : Minor Update backward-compatible features \\n"
                " \\"<green>\\"  : Patch Update backward-compatible bug fixes"
            }
            {
              "type": "table",
              "data": {
                "head": [
                  "Package",
                  "Current",
                  "Wanted",
                  "Latest",
                  "Package Type",
                  "URL"
                ],
                "body": [
                  [
                    "markdown",
                    "0.4.0",
                    "0.4.0",
                    "0.5.0",
                    "dependencies",
                    "git://github.com/evilstreak/markdown-js.git"
                  ]
                ]
              }
            }

        .. code-block:: shell-session

            $ yarn outdated --cwd ~/.config/yarn/global
            yarn outdated v1.22.19
            warning package.json: No license field
            info Color legend :
            "<red>"    : Major Update backward-incompatible updates
            "<yellow>" : Minor Update backward-compatible features
            "<green>"  : Patch Update backward-compatible bug fixes
            Package  Current Wanted Latest Package Type URL
            markdown 0.4.0   0.4.0  0.5.0  dependencies git://github.com/.../md-js.git
            ✨  Done in 0.95s.
        """
        output = self.run_cli(
            "--json", "outdated", "--cwd", self.global_dir, must_succeed=True
        )
        if output:
            for line in output.splitlines():
                if not line:
                    continue
                obj = json.loads(line)
                if obj["type"] == "table":
                    for package in obj["data"]["body"]:
                        if package[2] == "linked":
                            continue
                        yield self.package(
                            id=package[0],
                            installed_version=package[1],
                            latest_version=package[3],
                        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. warning::
            Yarn maintainers have `decided to not implement a dedicated search command
            <https://github.com/yarnpkg/yarn/issues/778#issuecomment-253146299>`_.

            Search is simulated by a direct call to ``yarn info``, and as a result only
            works for exact match.

        .. code-block:: shell-session

            $ yarn --json info python | jq
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
        output = self.run_cli("--json", "info", query, must_succeed=True)

        if output:
            result = json.loads(output)

            if result["type"] == "inspect":
                package = result["data"]
                yield self.package(
                    id=package["name"],
                    description=package["description"],
                    latest_version=package["version"],
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ yarn global add awesome-lint
            yarn global v1.22.19
            [1/4] 🔍  Resolving packages...
            [2/4] 🚚  Fetching packages...
            [3/4] 🔗  Linking dependencies...
            [4/4] 🔨  Building fresh packages...

            success Installed "awesome-lint@0.18.0" with binaries:
                - awesome-lint
            ✨  Done in 16.15s.
        """
        return self.run_cli("global", "add", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ yarn global upgrade --latest
            yarn global v1.22.19
            [1/4] 🔍  Resolving packages...
            [2/4] 🚚  Fetching packages...
            [3/4] 🔗  Linking dependencies...
            [4/4] 🔨  Rebuilding all packages...
            success Saved lockfile.
            success Saved 271 new dependencies.
            info Direct dependencies
            ├─ awesome-lint@0.18.0
            └─ markdown@0.5.0
            info All dependencies
            ├─ @babel/code-frame@7.18.6
            ├─ @babel/helper-validator-identifier@7.18.6
            ├─ @nodelib/fs.scandir@2.1.5
            ├─ array-to-sentence@1.1.0
            ├─ array-union@2.1.0
            ├─ awesome-lint@0.18.0
            ├─ fs.realpath@1.0.0
            (...)
            └─ zwitch@1.0.5
            ✨  Done in 19.89s.
        """
        return self.build_cli("global", "upgrade", "--latest")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ yarn global upgrade markdown --latest
            yarn global v1.22.19
            [1/4] 🔍  Resolving packages...
            [2/4] 🚚  Fetching packages...
            [3/4] 🔗  Linking dependencies...
            [4/4] 🔨  Rebuilding all packages...
            success Saved lockfile.
            success Saved 2 new dependencies.
            info Direct dependencies
            └─ markdown@0.5.0
            info All dependencies
            ├─ markdown@0.5.0
            └─ nopt@2.1.2
            ✨  Done in 1.77s.
        """
        return self.build_cli("global", "upgrade", package_id, "--latest")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ yarn global remove awesome-lint
            yarn global v1.22.19
            [1/2] 🗑  Removing module awesome-lint...
            [2/2] 🔨  Regenerating lockfile and installing missing dependencies...
            success Uninstalled packages.
            ✨  Done in 0.21s.
        """
        return self.run_cli("global", "remove", package_id)


class YarnBerry(Yarn):
    """Yarn Berry (2.x+) package manager.

    .. warning::
        Yarn Berry removed ``yarn global`` commands entirely. There is no concept
        of globally installed packages, so ``installed``, ``outdated``, ``install``,
        ``upgrade``, and ``remove`` operations are not available.
    """

    id = "yarn-berry"

    name = "Yarn Berry"

    requirement = ">=2.0.0"

    cli_names = ("yarn",)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. warning::
            Search is simulated by a direct call to ``yarn npm info``, and as a
            result only works for exact match.

        .. code-block:: shell-session

            $ yarn npm info python --json | jq
            {
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
              "version": "0.0.4",
              (...)
            }
        """
        output = self.run_cli("npm", "info", query, "--json")

        if output:
            package = json.loads(output)
            yield self.package(
                id=package["name"],
                description=package.get("description"),
                latest_version=package.get("dist-tags", {}).get("latest")
                or package.get("version"),
            )
