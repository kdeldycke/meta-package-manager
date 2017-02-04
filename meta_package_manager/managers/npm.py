# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2017 Kevin Deldycke <kevin@deldycke.com>
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

import json

from boltons.cacheutils import cachedproperty
from boltons.iterutils import remap

from ..base import PackageManager
from ..platform import MACOS


class NPM(PackageManager):

    cli_path = '/usr/local/bin/npm'

    platforms = frozenset([MACOS])

    def get_version(self):
        """ Fetch version from ``npm --version`` output."""
        return self.run([self.cli_path, '--version'])

    name = "Node's npm"

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``npm list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ npm list -g --json
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

        output = self.run([self.cli_path] + self.cli_args + [
            '-g', '--json', 'list'])

        if output:

            def visit(path, key, value):
                if key == 'version':
                    package_id = path[-1]
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': value}
                return True

            remap(json.loads(output), visit=visit)

        return installed

    def search(self, query):
        """ Fetch matching packages from ``npm search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ npm search python --json | jq
            [
              {
                "name": "angularjs-simplest-structure",
                "time": {
                  "modified": "2016-06-01T09:15:16.502Z"
                }
              },
              (...)
              {
                "name": "zip-array",
                "description": "A javascript equivalent of Python's zip",
                "dist-tags": {
                  "latest": "1.0.1"
                },
                "maintainers": [
                  {
                    "name": "vikramcse",
                    "email": "vikramcse.10@gmail.com"
                  }
                ],
                "homepage": "https://github.com/vikramcse/zip-array#readme",
                "keywords": [
                  "zip",
                  "combine",
                  "array",
                  "python",
                  "merge",
                  "longest",
                  "shortest"
                ],
                "repository": {
                  "type": "git",
                  "url": "git+https://github.com/vikramcse/zip-array.git"
                },
                "author": {
                  "name": "Vikram",
                  "email": "vikramcse.10@gmail.com"
                },
                "bugs": {
                  "url": "https://github.com/vikramcse/zip-array/issues"
                },
                "license": "ISC",
                "readmeFilename": "README.md",
                "time": {
                  "modified": "2016-02-12T06:45:17.083Z"
                },
                "versions": {
                  "1.0.1": "latest"
                }
              },
              {
                "name": "zpt",
                "description": "Zenon Page Templates - JS (ZPT-JS)",
                "dist-tags": {
                  "latest": "0.6.0"
                },
                "maintainers": [
                  {
                    "name": "davidcana",
                    "email": "david.javapagetemplates@gmail.com"
                  }
                ],
                "homepage": "https://github.com/davidcana/ZPT-JS",
                "keywords": [
                  "jquery-plugin",
                  "ecosystem:jquery",
                  "template",
                  "templates",
                  "templating",
                  "python",
                  "zpt",
                  "zope",
                  "page"
                ],
                "contributors": [
                  {}
                ],
                "author": {
                  "name": "David Cana Lopez"
                },
                "bugs": {
                  "email": "david.javapagetemplates@gmail.com"
                },
                "license": "AGPL-3.0",
                "readmeFilename": "README.md",
                "repository": {
                  "type": "git",
                  "url": "git+https://github.com/davidcana/ZPT-JS.git"
                },
                "time": {
                  "modified": "2016-11-16T17:55:29.646Z"
                },
                "versions": {
                  "0.6.0": "latest"
                }
              }
            ]
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query, '--json'])

        if output:
            for package in json.loads(output):
                package_id = package['name']
                matches[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'latest_version': package.get(
                        'dist-tags', {}).get('latest', None),
                    'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``npm outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ npm -g --progress=false --json outdated
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

        output = self.run([self.cli_path] + self.cli_args + [
            '-g', '--progress=false', '--json', 'outdated'])

        if output:
            for package_id, values in json.loads(output).items():
                if values['wanted'] == 'linked':
                    continue
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version':
                        values['current'] if 'current' in values else None,
                    'latest_version': values['latest']}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + [
            '-g', '--progress=false', 'update']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
