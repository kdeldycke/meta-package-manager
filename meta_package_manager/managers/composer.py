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

import re

import simplejson as json
from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..version import parse_version


class Composer(PackageManager):

    name = "PHP's Composer"
    global_args = ("global",)
    platforms = frozenset({LINUX, MACOS, WINDOWS})
    requirement = "1.4.0"

    version_regex = r"Composer\s+version\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► composer --version
        Composer version 2.1.8 2021-09-15 13:55:14
    """

    @property
    def installed(self):
        """Fetch installed packages from ``composer global show`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► composer global show --format=json | jq
            {
              "installed": [
                {
                  "name": "carbondate/carbon",
                  "version": "1.33.0",
                  "description": "A simple API extension for DateTime."
                },
                {
                  "name": "guzzlehttp/guzzle",
                  "version": "6.3.3",
                  "description": "Guzzle is a PHP HTTP client library"
                },
                {
                  "name": "guzzlehttp/promises",
                  "version": "v1.3.1",
                  "description": "Guzzle promises library"
                },
                {
                  "name": "guzzlehttp/psr7",
                  "version": "1.4.2",
                  "description": "PSR-7 message (...) methods"
                },
            (...)
        """
        installed = {}

        output = self.run_cli("show", "--format=json")

        if output:

            package_list = json.loads(output)
            for package in package_list["installed"]:
                package_id = package["name"]
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package["version"]),
                }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``composer search`` output.

        .. code-block:: shell-session

            ► composer global search symfony
            symfony/symfony The Symfony PHP framework
            symfony/yaml Symfony Yaml Component
            symfony/var-dumper Symfony (...) dumping PHP variables
            symfony/translation Symfony Translation Component
            symfony/routing Symfony Routing Component
            symfony/process Symfony Process Component
            symfony/polyfill-php70 Symfony (...) features to lower PHP versions
            symfony/polyfill-mbstring Symfony (...) Mbstring extension
            symfony/polyfill-ctype Symfony polyfill for ctype functions
            symfony/http-kernel Symfony HttpKernel Component
            symfony/http-foundation Symfony HttpFoundation Component
            symfony/finder Symfony Finder Component
            symfony/event-dispatcher Symfony EventDispatcher Component
            symfony/debug Symfony Debug Component
            symfony/css-selector Symfony CssSelector Component

        .. code-block:: shell-session

            ► composer global search --only-name python
            hiqdev/hidev-python
            aanro/pythondocx
            laravel-admin-ext/python-editor
            pythonphp/pythonphp
            blyxxyz/python-server
            nim-development/python-domotics
            rakshitbharat/pythoninphp
            tequilarapido/python-bridge

        .. code-block:: shell-session

            ► search global --only-name pythonphp/pythonphp
            pythonphp/pythonphp
        """
        matches = {}

        search_args = []
        if not extended:
            search_args.append("--only-name")

        output = self.run_cli("search", search_args, query)

        if output:

            regexp = re.compile(
                r"""
                ^(?P<package_id>\S+\/\S+)
                (?P<description> .*)?
                """,
                re.MULTILINE | re.VERBOSE,
            )

            for package_id, description in regexp.findall(output):

                # Filters out fuzzy matches, only keep stricly matching
                # packages.
                if exact and query != package_id:
                    continue

                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": None,
                }

        return matches

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► composer global install illuminate/contracts

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``composer global outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

        ► composer global outdated --format=json
        {
            "installed": [
                {
                    "name": "illuminate/contracts",
                    "version": "v5.7.2",
                    "latest": "v5.7.3",
                    "latest-status": "semver-safe-update",
                    "description": "The Illuminate Contracts package."
                },
                {
                    "name": "illuminate/support",
                    "version": "v5.7.2",
                    "latest": "v5.7.3",
                    "latest-status": "semver-safe-update",
                    "description": "The Illuminate Support package."
                }
            ]
        }
        """
        outdated = {}

        output = self.run_cli("outdated", "--format=json")

        if output:
            package_list = json.loads(output)
            for package in package_list["installed"]:
                package_id = package["name"]
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package["version"]),
                    "latest_version": parse_version(package["latest"]),
                }

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, self.global_args, "update"]
        if package_id:
            cmd.append(package_id)
        return cmd

    def cleanup(self):
        """Runs:

        .. code-block:: shell-session

            ► composer global clear-cache

        See: https://getcomposer.org/doc/03-cli.md#clear-cache-clearcache-cc
        """
        super().cleanup()
        self.run_cli("clear-cache")
