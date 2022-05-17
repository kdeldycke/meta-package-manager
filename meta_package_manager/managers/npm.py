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
from operator import itemgetter

from boltons.iterutils import remap
from click_extra.platform import LINUX, MACOS, WINDOWS

from .. import logger
from ..base import PackageManager
from ..version import parse_version


class NPM(PackageManager):

    name = "Node's npm"

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    requirement = "4.0.0"

    """
    .. code-block:: shell-session

        ► npm --version
        6.13.7
    """

    def run_cli(self, *args, **kwargs):
        """Like the common run_cli helper, but silence NPM's JSON output on error.

        NPM is prone to breakage if local node version is not in sync:

        .. code-block:: shell-session

            ► npm --global --progress=false --json --no-update-notifier outdated
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
                output = None

        return output

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► npm --global --json list | jq
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
        installed = {}

        output = self.run_cli("--global", "--json", "list")

        if output:

            def visit(path, key, value):
                if key == "version":
                    package_id = path[-1]
                    installed[package_id] = {
                        "id": package_id,
                        "name": package_id,
                        "installed_version": parse_version(value),
                    }
                return True

            remap(json.loads(output), visit=visit)

        return installed

    @property
    def outdated(self):
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► npm --global --progress=false --json --no-update-notifier outdated
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
                "location": "/Users/..."
              }
            }
        """
        outdated = {}

        output = self.run_cli(
            "--global",
            "--progress=false",
            "--json",
            "--no-update-notifier",
            "outdated",
        )

        if output:
            for package_id, values in json.loads(output).items():
                if values["wanted"] == "linked":
                    continue
                outdated[package_id] = {
                    "id": f"{package_id}@{values['latest']}",
                    "name": package_id,
                    "installed_version": parse_version(values["current"]),
                    "latest_version": parse_version(values["latest"]),
                }

        return outdated

    def search(self, query, extended, exact):
        """Fetch matching packages.

        Doc: https://docs.npmjs.com/cli/search.html

        .. caution::
            Search does not supports exact matching.

        .. code-block:: shell-session

            ► npm search --json python | jq
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

            ► npm search --json --no-description python | jq
        """
        if exact:
            logger.warning(f"{self.id} does not implement exact search operation.")

        search_args = []
        if not extended:
            search_args.append("--no-description")

        output = self.run_cli("search", "--json", search_args, query)

        if output:
            for package_id, version, description in map(
                itemgetter("name", "version", "description"), json.loads(output)
            ):
                yield {
                    "id": package_id,
                    "name": package_id,
                    "description": description,
                    "latest_version": parse_version(version),
                }

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier install raven
        """
        return self.run_cli(
            "--global",
            "--progress=false",
            "--no-update-notifier",
            "install",
            package_id,
        )

    def upgrade_cli(self, package_id=None, version=None):
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier update

        .. code-block:: shell-session

            ► npm --global --progress=false --no-update-notifier install raven
        """
        cmd_args = ("update",)
        if package_id:
            cmd_args = (
                "install",
                f"{package_id}@{version}" if version else package_id,
            )

        return self.build_cli(
            "--global", "--progress=false", "--no-update-notifier", *cmd_args
        )
