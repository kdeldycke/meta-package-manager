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

from extra_platforms import BSD, LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class APM(PackageManager):
    """Atom's package manager, from the sunset Atom editor.

    apm installed packages and themes for GitHub's Atom editor, exposing an
    npm-style CLI whose queries mpm parses from ``--json`` output.

    Atom was `sunset on December 15, 2022
    <https://github.blog/2022-06-08-sunsetting-atom/>`_, so apm is flagged
    deprecated here. mpm keeps the wrapper while doing so stays cheap: the
    community fork `atom-community/apm <https://github.com/atom-community/apm>`_
    has been floated but never produced a usable drop-in, and per the project's
    stability policy a deprecated manager may be dropped without notice once it
    becomes a burden to maintain.
    """

    deprecated = True
    deprecation_url = "https://github.blog/2022-06-08-sunsetting-atom/"
    """GitHub announced the end of the project for December 15, 2022.
    Source: https://github.blog/2022-06-08-sunsetting-atom/

    There is a tentative community fork being discussed. See:
    https://github.com/atom-community/apm

    In the mean time, as long as no apm alternative is useable, it is safe to tag this
    manager as deprecated.
    """

    name = "Atom apm"

    homepage_url = "https://atom.io/packages"

    platforms = BSD, LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=1.0.0"

    version_regexes = (r"apm\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ apm --version
        apm  2.6.2
        npm  6.14.13
        node 12.14.1 x64
        atom 1.58.0
        python 2.7.16
        git 2.33.0
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ apm list --json
            {
              "core": [
                {
                  "name": "background-tips",
                  "version": "0.26.1",
                  "description": "Displays tips about Atom in the background."
                }
              ],
              "user": [
                {
                  "name": "file-icons",
                  "version": "2.0.9",
                  "description": "Assign file extension icons"
                }
              ]
            }
        """
        output = self.run_cli("list", "--json", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for package_list in data.values():
                for pkg in package_list:
                    yield self.package(
                        id=pkg["name"],
                        description=pkg["description"],
                        installed_version=pkg["version"],
                    )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ apm outdated --compatible --json
            [
              {
                "name": "file-icons",
                "version": "2.0.9",
                "latestVersion": "2.0.10",
                "description": "Assign file extension icons"
              }
            ]
        """
        output = self.run_cli("outdated", "--compatible", "--json", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg in data:
                yield self.package(
                    id=pkg["name"],
                    description=pkg["description"],
                    installed_version=pkg["version"],
                    latest_version=pkg["latestVersion"],
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports exact matching.

        .. code-block:: shell-session

            $ apm search --json python | jq
            [
              {
                "name": "atom-python-run",
                "main": "./lib/atom-python-run.js",
                "version": "0.7.3",
                "description": "Run a python source file.",
                "keywords": [
                  "python"
                ],
                "repository": "https://github.com/foreshadow/atom-python-run",
                "license": "MIT",
                "engines": {
                  "atom": ">=1.0.0 <2.0.0"
                },
                "dependencies": {},
                "readme": "Blah blah",
                "downloads": 41379,
                "stargazers_count": 16
              },
              {
                "name": "build-python",
                "version": "0.6.3",
                "description": "Atom Build provider for python/python3",
                "repository": "https://github.com/idleberg/atom-build-python",
                "license": "MIT",
                "keywords": [
                  "buildprovider",
                  "compile",
                  "python",
                  "python3",
                  "linter",
                  "lint"
                ],
                "main": "lib/provider.js",
                "engines": {
                  "atom": ">=1.0.0 <2.0.0"
                },
                "providedServices": {
                  "builder": {
                    "description": "Compiles Python",
                    "versions": {
                      "2.0.0": "provideBuilder"
                    }
                  }
                },
                "package-deps": [
                  "build"
                ],
                "dependencies": {
                  "atom-package-deps": "^4.3.1"
                },
                "devDependencies": {
                  "babel-eslint": "^7.1.1",
                  "coffeelint-stylish": "^0.1.2",
                  "eslint": "^3.13.1",
                  "eslint-config-atom-build": "^4.0.0",
                  "gulp": "github:gulpjs/gulp#4.0",
                  "gulp-coffeelint": "^0.6.0",
                  "gulp-debug": "^3.0.0",
                  "gulp-jshint": "^2.0.4",
                  "gulp-jsonlint": "^1.2.0",
                  "gulp-lesshint": "^2.1.0",
                  "jshint": "^2.9.4"
                },
                "scripts": {
                  "test": "gulp lint"
                },
                "readme": "Blah blah",
                "downloads": 2838,
                "stargazers_count": 0
              },
              (...)
            ]

        .. code-block:: shell-session

            $ apm search --no-description --json python | jq
        """
        search_args = []
        if not extended:
            search_args.append("--no-description")

        output = self.run_cli("search", search_args, "--json", query, must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg in data:
                yield self.package(
                    id=pkg["name"],
                    description=pkg["description"],
                    latest_version=pkg["version"],
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ apm install image-view
            The image-view package is bundled with Atom and should not be explicitly
            installed. You can run `apm uninstall image-view` to uninstall it and then
            the version bundled with Atom will be used.
            Installing image-view to /Users/kde/.atom/packages ✓
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        .. code-block:: shell-session

            $ apm update --no-confirm
        """
        return self.build_cli("update", "--no-confirm")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        .. code-block:: shell-session

            $ apm update --no-confirm image-view
        """
        return self.build_cli("update", "--no-confirm", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ apm uninstall image-view
        """
        return self.run_cli("uninstall", package_id)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ apm clean
        """
        self.run_cli("clean")
