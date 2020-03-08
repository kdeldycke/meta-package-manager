# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2018 Kevin Deldycke <kevin@deldycke.com>
#                         and contributors.
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

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import re

import simplejson as json
from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX, MACOS, WINDOWS


class Composer(PackageManager):

    name = "PHP's Composer"
    cli_args = ['global']
    platforms = frozenset([LINUX, MACOS, WINDOWS])
    requirement = '>= 1.4.*'

    def get_version(self):
        """ Fetch version from ``composer --version`` output."""
        output = self.run([self.cli_path, '--version'])
        if output:
            return output.split()[2]

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``composer global show`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ composer global show --format=json | jq
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

        output = self.run([self.cli_path] + self.cli_args + [
            'show', '--format=json'])

        if output:

            package_list = json.loads(output)
            for package in package_list['installed']:
                package_id = package['name']
                installed[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': package['version']}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``composer search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ composer search symfony
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
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            regexp = re.compile(r'(\S+\/\S+) .*')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id = match.group(1)
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': None,
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``composer global outdated`` output.

            Raw CLI output samples:

            .. code-block:: shell-session

            $ composer global outdated --format=json
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

        output = self.run([self.cli_path] + self.cli_args + [
            'outdated', '--format=json', ])

        if output:
            package_list = json.loads(output)
            for package in package_list['installed']:
                package_id = package['name']
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': package['version'],
                    'latest_version': package['latest']}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + [
            'update']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
