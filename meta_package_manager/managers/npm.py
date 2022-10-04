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

from __future__ import annotations

import json
from typing import Any, Iterator

from boltons.iterutils import remap
from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import Arg, NestedArgs, Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class NPM(PackageManager):

    name = "Node's npm"

    homepage_url = "https://www.npmjs.com"

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    requirement = "4.0.0"

    pre_args = (
        # Operates in "global" mode, so that packages are installed into the
        # prefix folder instead of the current working directory.
        "--global",
        # Suppress the progress bar.
        "--progress=false",
        # Suppress the update notification when using an older version of npm than
        # the latest.
        "--no-update-notifier",
        # Hide the message displayed at the end of each install that acknowledges
        # the number of dependencies looking for funding.
        "--no-fund",
        # Disable sending of audit reports to the configured registries.
        "--no-audit",
    )

    """
    .. code-block:: shell-session

        ► npm --version
        6.13.7
    """

    def run_cli(self, *args: Arg | NestedArgs, **kwargs: Any) -> str:
        """Like the common run_cli helper, but silence NPM's JSON output on error.

        NPM is prone to breakage if local node version is not in sync:

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit --json outdated
            {
              "error": {
                "code": "ERR_OUT_OF_RANGE",
                "summary": "The value of \"err\" is out of range. Received 536870212",
                "detail": ""
              }
            }
        """
        output = super().run_cli(*args, **kwargs)

        # NPM fatal errors are reported both in <stderr> output and as JSON. So we
        # silence the errors in JSON so they get reported in CLI output (as
        # they're already featured in self.cli_errors) without raising error
        # (unless the --stop-on-error option is provided).
        if "--json" in args:
            if output and self.cli_errors:
                output = ""

        return output

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit --json list | jq
            {
              "dependencies": {
                "npm": {
                  "version": "4.0.5",
                  "dependencies": {
                    "JSONStream": {
                      "version": "1.2.1",
                      "from": "JSONStream@latest",
                      "resolved": "https://(...)/JSONStream-1.2.1.tgz",
                      "dependencies": {
                        "jsonparse": {
                          "version": "1.2.0",
                          "from": "jsonparse@>=1.2.0 <2.0.0",
                          "resolved": "https://(...)/jsonparse-1.2.0.tgz"
                        },
                        "through": {
                          "version": "2.3.8",
                          "from": "through@>=2.2.7 <3.0.0",
                          "resolved": "https://(...)/through-2.3.8.tgz"
                        }
                      }
                    },
                    "abbrev": {
                      "version": "1.0.9",
                      "from": "abbrev@1.0.9",
                      "resolved": "https://(...)/abbrev-1.0.9.tgz"
                    },
                    "ansi-regex": {
                      "version": "2.0.0",
                      "from": "ansi-regex@2.0.0",
                      "resolved": "https://(...)/ansi-regex-2.0.0.tgz"
                    },
            (...)
        """
        installed = []

        output = self.run_cli("--json", "list")

        if output:

            def visit(path, key: str, value: str) -> bool:
                if key == "version":
                    package_id = path[-1]
                    installed.append(
                        self.package(id=package_id, installed_version=value)
                    )
                return True

            remap(json.loads(output), visit=visit)

        yield from installed

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit --json outdated | jq
            {
              "my-linked-package": {
                "current": "0.0.0-development",
                "wanted": "linked",
                "latest": "linked",
                "location": "/Users/..."
              },
              "npm": {
                "current": "3.10.3",
                "wanted": "3.10.5",
                "latest": "3.10.5",
                "location": "/opt/homebrew/lib/node_modules/npm"
              }
            }
        """
        output = self.run_cli("--json", "outdated")

        if output:
            for package_id, values in json.loads(output).items():
                if values["wanted"] == "linked":
                    continue
                yield self.package(
                    id=f"{package_id}",
                    # It seems "current" is not always populated.
                    installed_version=values.get("current"),
                    latest_version=values["latest"],
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Doc: https://docs.npmjs.com/cli/search.html

        .. caution::
            Search does not supports exact matching.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit search --json python | jq
            [
              {
                "name": "python",
                "description": "Interact with a python child process",
                "maintainers": [
                  {
                    "username": "drderidder",
                    "email": "drderidder@gmail.com"
                  }
                ],
                "version": "0.0.4",
                "date": "2015-01-25T02:48:07.820Z"
              },
              {
                "name": "raven",
                "description": "A standalone (Node.js) client for Sentry",
                "maintainers": [
                  {
                    "username": "benvinegar",
                    "email": "ben@benv.ca"
                  },
                  {
                    "username": "lewisjellis",
                    "email": "me@lewisjellis.com"
                  },
                  {
                    "username": "mattrobenolt",
                    "email": "m@robenolt.com"
                  },
                  {
                    "username": "zeeg",
                    "email": "dcramer@gmail.com"
                  }
                ],
                "keywords": [
                  "raven",
                  "sentry",
                  "python",
                  "errors",
                  "debugging",
                  "exceptions"
                ],
                "version": "1.1.2",
                "date": "2017-02-09T02:54:07.723Z"
              },
              {
                "name": "brush-python",
                "description": "Python brush module for SyntaxHighlighter.",
                "maintainers": [
                  {
                    "username": "alexgorbatchev",
                    "email": "alex.gorbatchev@gmail.com"
                  }
                ],
                "keywords": [
                  "syntaxhighlighter",
                  "brush",
                  "python"
                ],
                "version": "4.0.0",
                "date": "2016-02-07T21:32:39.597Z"
              },
              (...)
            ]

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit search --json --no-description python | jq
        """
        search_args = []
        if not extended:
            search_args.append("--no-description")

        output = self.run_cli("search", "--json", search_args, query)

        if output:
            for pkg in json.loads(output):
                yield self.package(
                    id=pkg.get("name"),
                    description=pkg.get("description"),
                    latest_version=pkg.get("version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit install markdown

            added 3 packages in 3s
        """
        return self.run_cli("install", "--no-fund", "--no-audit", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit upgrade
        """
        return self.build_cli("update")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit upgrade raven
        """
        return self.build_cli("upgrade", f"{package_id}")

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier --no-fund --no-audit uninstall raven
        """
        return self.run_cli("uninstall", package_id)
