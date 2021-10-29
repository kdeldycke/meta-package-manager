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
from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..version import TokenizedString, parse_version


class APM(PackageManager):

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    name = "Atom's apm"

    requirement = "1.0.0"

    version_regex = r"apm\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► apm --version
        apm  2.6.2
        npm  6.14.13
        node 12.14.1 x64
        atom 1.58.0
        python 2.7.16
        git 2.33.0
    """

    @property
    def installed(self):
        """Fetch installed packages from ``apm list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► apm list --json | jq
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

        output = self.run_cli("list", "--json")

        if output:
            for package_list in json.loads(output).values():
                for package in package_list:
                    package_id = package["name"]
                    installed[package_id] = {
                        "id": package_id,
                        "name": package_id,
                        "installed_version": parse_version(package["version"]),
                    }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``apm search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► apm search python --json | jq
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
        """
        matches = {}

        search_args = []
        if not extended:
            search_args.append("--no-description")

        output = self.run_cli("search", "--json", search_args, query)

        if output:
            for package in json.loads(output):
                package_id = package["name"]

                # Exclude packages not featuring the search query in their ID
                # or name.
                if not extended:
                    query_parts = set(map(str, TokenizedString(query)))
                    pkg_parts = set(map(str, TokenizedString(package_id)))
                    if not query_parts.issubset(pkg_parts):
                        continue

                # Filters out fuzzy matches, only keep stricly matching
                # packages.
                if exact and query != package_id:
                    continue

                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(package["version"]),
                }

        return matches

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► apm install image-view
            The image-view package is bundled with Atom and should not be explicitly installed.
            You can run `apm uninstall image-view` to uninstall it and then the version bundled
            with Atom will be used.
            Installing image-view to /Users/kde/.atom/packages ✓

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``apm outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► apm outdated --compatible --json | jq
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

        output = self.run_cli("outdated", "--compatible", "--json")

        if output:
            for package in json.loads(output):
                package_id = package["name"]
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package["version"]),
                    "latest_version": parse_version(package["latestVersion"]),
                }

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, "update", "--no-confirm"]
        if package_id:
            cmd.append(package_id)
        return cmd
