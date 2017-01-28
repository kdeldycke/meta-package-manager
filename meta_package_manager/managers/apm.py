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

from ..base import PackageManager
from ..platform import MACOS


class APM(PackageManager):

    cli_path = '/usr/local/bin/apm'

    platforms = frozenset([MACOS])

    def get_version(self):
        """ Fetch version from ``apm --version`` output."""
        return self.run([self.cli_path, '--version']).split('\n')[0].split()[1]

    name = "Atom's apm"

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``apm list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apm list --json | jq
            {
              "core": [
                {
                  "_args": [
                    [
                      {
                        "raw": "/private/var/folders/(...)/package.tgz",
                        "scope": null,
                        "escapedName": null,
                        "name": null,
                        "rawSpec": "/private/var/folders/(...)/package.tgz",
                        "spec": "/private/var/folders/(...)/package.tgz",
                        "type": "local"
                      },
                      "/Users/distiller/atom"
                    ]
                  ],
                  "_inCache": true,
                  "_installable": true,
                  "_location": "/background-tips",
                  "_phantomChildren": {},
                  "_requested": {
                    "raw": "/private/var/folders/(...)/package.tgz",
                    "scope": null,
                    "escapedName": null,
                    "name": null,
                    "rawSpec": "/private/var/folders/(...)/package.tgz",
                    "spec": "/private/var/folders/(...)/package.tgz",
                    "type": "local"
                  },
                  "_requiredBy": [
                    "#USER"
                  ],
                  "_resolved": "file:../../../private/var/(...)/package.tgz",
                  "_shasum": "7978e4fdab3b162d93622fc64d012df7a92aa569",
                  "_shrinkwrap": null,
                  "_spec": "/private/var/folders/(...)/package.tgz",
                  "_where": "/Users/distiller/atom",
                  "bugs": {
                    "url": "https://github.com/atom/background-tips/issues"
                  },
                  "dependencies": {
                    "underscore-plus": "1.x"
                  },
                  "description": "Displays tips about Atom in the background.",
                  "devDependencies": {
                    "coffeelint": "^1.9.7"
                  },
                  "engines": {
                    "atom": ">0.42.0"
                  },
                  "homepage": "https://github.com/atom/background-tips#readme",
                  "license": "MIT",
                  "main": "./lib/background-tips",
                  "name": "background-tips",
                  "optionalDependencies": {},
                  "private": true,
                  "repository": {
                    "type": "git",
                    "url": "https://github.com/atom/background-tips.git"
                  },
                  "version": "0.26.1",
                  "_atomModuleCache": {
                    "version": 1,
                    "dependencies": [],
                    "extensions": {
                      ".js": [
                        "lib/background-tips-view.js",
                        "lib/background-tips.js",
                        "lib/tips.js"
                      ]
                    },
                    "folders": [
                      {
                        "paths": [
                          "lib",
                          ""
                        ],
                        "dependencies": {
                          "underscore-plus": "1.x"
                        }
                      }
                    ]
                  }
                },
                (...)
              ]
            }
        """
        installed = {}

        installed_cmd = [self.cli_path] + self.cli_args + ['list', '--json']
        output = self.run(installed_cmd)

        if output:
            for package_list in json.loads(output).values():
                for package in package_list:
                    package_id = package['name']
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': package['version']}

        return installed

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``apm outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apm outdated --compatible --json | jq
            [
              {
                "_args": [
                  [
                    {
                      "raw": "/private/var/folders/(...)/package.tgz",
                      "scope": null,
                      "escapedName": null,
                      "name": null,
                      "rawSpec": "/private/var/folders/(...)/package.tgz",
                      "spec": "/private/var/folders/(...)/package.tgz",
                      "type": "local"
                    },
                    "/private/var/folders/(...)/apm-install-dir-117017"
                  ]
                ],
                "_from": "../d-117017-63877-vcgh4t/package.tgz",
                "_id": "file-icons@2.0.9",
                "_inCache": true,
                "_installable": true,
                "_location": "/file-icons",
                "_phantomChildren": {},
                "_requested": {
                  "raw": "/private/var/folders/(...)/package.tgz",
                  "scope": null,
                  "escapedName": null,
                  "name": null,
                  "rawSpec": "/private/var/folders/(...)/package.tgz",
                  "spec": "/private/var/folders/(...)/package.tgz",
                  "type": "local"
                },
                "_requiredBy": [
                  "#USER"
                ],
                "_resolved": "file:../d-117017-63877-vcgh4t/package.tgz",
                "_shasum": "8b2df93ad752af1676d91c12afa068f2000b864c",
                "_shrinkwrap": null,
                "_spec": "/private/var/folders/(...)/package.tgz",
                "_where": "/private/var/folders/(...)/apm-install-dir-117017",
                "atom-mocha": {
                  "interactive": {
                    "mocha": {
                      "bail": true
                    }
                  }
                },
                "atomTestRunner": "./node_modules/.bin/atom-mocha",
                "bugs": {
                  "url": "https://github.com/file-icons/atom/issues"
                },
                "configSchema": {
                  "coloured": {
                    "type": "boolean",
                    "default": true,
                    "description": "Untick this for colourless icons",
                    "order": 1
                  },
                  "onChanges": {
                    "type": "boolean",
                    "default": false,
                    "title": "Only colour when changed",
                    "description": "Show different icon.",
                    "order": 2
                  },
                  "tabPaneIcon": {
                    "type": "boolean",
                    "default": true,
                    "title": "Show icons in file tabs",
                    "order": 3
                  },
                  "defaultIconClass": {
                    "type": "string",
                    "default": "default-icon",
                    "title": "Default icon class",
                    "description": "CSS added to files that lack an icon.",
                    "order": 4
                  },
                  "strategies": {
                    "type": "object",
                    "title": "Match strategies",
                    "description": "Advanced settings for icon assignment.",
                    "order": 5,
                    "properties": {
                      "grammar": {
                        "type": "boolean",
                        "default": true,
                        "order": 1,
                        "title": "Change on grammar override",
                        "description": "Change a file's icon when setting."
                      },
                      "hashbangs": {
                        "type": "boolean",
                        "default": true,
                        "order": 2,
                        "title": "Check hashbangs",
                        "description": "Allow lines like `#!/usr/bin/perl`."
                      }
                    }
                  }
                },
                "dependencies": {
                  "micromatch": "*"
                },
                "description": "Assign file extension icons",
                "devDependencies": {
                  "atom-mocha": "*",
                  "coffee-script": "*",
                  "get-options": "*",
                  "rimraf": "*",
                  "tmp": "*",
                  "unzip": "*"
                },
                "engines": {
                  "atom": ">1.11.0"
                },
                "homepage": "https://github.com/file-icons/atom",
                "license": "MIT",
                "main": "lib/main.js",
                "name": "file-icons",
                "optionalDependencies": {},
                "private": true,
                "providedServices": {
                  "file-icons.element-icons": {
                    "versions": {
                      "1.0.0": "provideService"
                    }
                  },
                  "atom.file-icons": {
                    "versions": {
                      "1.0.0": "suppressFOUC"
                    }
                  }
                },
                "readme": "Blah blah",
                "readmeFilename": "README.md",
                "repository": {
                  "type": "git",
                  "url": "git+https://github.com/file-icons/atom.git"
                },
                "version": "2.0.9",
                "latestVersion": "2.0.10"
              }
            ]
        """
        outdated = {}

        outdated_cmd = [self.cli_path] + self.cli_args + [
            'outdated', '--compatible', '--json']
        output = self.run(outdated_cmd)

        if output:
            for package in json.loads(output):
                package_id = package['name']
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': package['version'],
                    'latest_version': package['latestVersion']}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update', '--no-confirm']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
