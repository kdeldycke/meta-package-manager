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

        Raw CLI output sample:

        .. code-block:: shell-session
            $ apm list --json | jq
            {
              "core": [
                {
                  "_args": [
                    [
                      {
                        "raw": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                        "scope": null,
                        "escapedName": null,
                        "name": null,
                        "rawSpec": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                        "spec": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
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
                    "raw": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                    "scope": null,
                    "escapedName": null,
                    "name": null,
                    "rawSpec": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                    "spec": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                    "type": "local"
                  },
                  "_requiredBy": [
                    "#USER"
                  ],
                  "_resolved": "file:../../../private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                  "_shasum": "7978e4fdab3b162d93622fc64d012df7a92aa569",
                  "_shrinkwrap": null,
                  "_spec": "/private/var/folders/jm/fw86rxds0xn69sk40d18y69m0000gp/T/d-116109-34686-t88dqy/package.tgz",
                  "_where": "/Users/distiller/atom",
                  "bugs": {
                    "url": "https://github.com/atom/background-tips/issues"
                  },
                  "dependencies": {
                    "underscore-plus": "1.x"
                  },
                  "description": "Displays tips about Atom in the background when there are no editors open.",
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

        Raw CLI output sample:

        .. code-block:: shell-session
            $ apm outdated --compatible --json | jq
            [
              {
                "_args": [
                  [
                    {
                      "raw": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                      "scope": null,
                      "escapedName": null,
                      "name": null,
                      "rawSpec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                      "spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                      "type": "local"
                    },
                    "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/apm-install-dir-117017-63821-55dy2i"
                  ]
                ],
                "_from": "../d-117017-63821-1laqt9k/package.tgz",
                "_id": "autocomplete-python@1.8.26",
                "_inCache": true,
                "_installable": true,
                "_location": "/autocomplete-python",
                "_phantomChildren": {},
                "_requested": {
                  "raw": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                  "scope": null,
                  "escapedName": null,
                  "name": null,
                  "rawSpec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                  "spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                  "type": "local"
                },
                "_requiredBy": [
                  "#USER"
                ],
                "_resolved": "file:../d-117017-63821-1laqt9k/package.tgz",
                "_shasum": "3a350b4952f9b3e8a7761ea9dbd5f4e0d8350bce",
                "_shrinkwrap": null,
                "_spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63821-1laqt9k/package.tgz",
                "_where": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/apm-install-dir-117017-63821-55dy2i",
                "bugs": {
                  "url": "https://github.com/autocomplete-python/autocomplete-python/issues"
                },
                "consumedServices": {
                  "snippets": {
                    "versions": {
                      "0.1.0": "consumeSnippets"
                    }
                  }
                },
                "contributors": [
                  {
                    "name": "Dmitry Sadovnychyi",
                    "email": "autocomplete-python@dmit.ro"
                  },
                  {
                    "name": "Daniel Hung",
                    "email": "daniel@kite.com"
                  }
                ],
                "dependencies": {
                  "atom-slick": "^2.0.0",
                  "atom-space-pen-views": "~2.1.0",
                  "fuzzaldrin-plus": "^0.3.1",
                  "kite-installer": "0.7.0",
                  "mixpanel": "^0.5.0",
                  "selector-kit": "^0.1",
                  "space-pen": "^5.1.2",
                  "underscore": "^1.8.3"
                },
                "description": "Python completions for packages, variables, methods, functions, with their arguments. Powered by your choice of Jedi or Kite.",
                "devDependencies": {},
                "engines": {
                  "atom": ">=0.194.0 <2.0.0"
                },
                "homepage": "https://github.com/autocomplete-python/autocomplete-python#readme",
                "keywords": [
                  "python",
                  "autocomplete",
                  "jedi"
                ],
                "license": "GPL",
                "main": "./lib/main",
                "name": "autocomplete-python",
                "optionalDependencies": {},
                "package-dependencies": {},
                "providedServices": {
                  "autocomplete.provider": {
                    "versions": {
                      "2.0.0": "getProvider"
                    }
                  },
                  "hyperclick.provider": {
                    "versions": {
                      "0.0.0": "getHyperclickProvider"
                    }
                  }
                },
                "readme": "# Python Autocomplete Package [![Build Status](https://travis-ci.org/autocomplete-python/autocomplete-python.svg?branch=master)](https://travis-ci.org/autocomplete-python/autocomplete-python)\n\nPython packages, variables, methods and functions with their arguments autocompletion in [Atom](http://atom.io) powered by [Jedi](https://github.com/davidhalter/jedi).\n\nSee [releases](https://github.com/sadovnychyi/autocomplete-python/releases) for release notes.\n\n![Demo](https://cloud.githubusercontent.com/assets/193864/12288427/61fe2114-ba0f-11e5-9832-98869180d87f.gif)\n\n# Features\n\n* Works with :apple: Mac OSX, :penguin: Linux and :checkered_flag: Windows.\n* Works with both :snake: Python 2 and 3.\n* Automatic lookup of virtual environments inside of your projects.\n* Configurable additional packages to include for completions.\n* Prints first N characters of statement value while completing variables.\n* Prints function arguments while completing functions.\n* Go-to-definition functionality, by default on `Alt+Cmd+G`/`Ctrl+Alt+G`. Thanks to [@patrys](https://github.com/patrys) for idea and implementation.\n* Method override functionality. Available as `override-method` command. Thanks to [@pchomik](https://github.com/pchomik) for idea and help.\n* If you have [Hyperclick](https://atom.io/packages/hyperclick) installed – you can click on anything to go-to-definition\n  ![sample](https://cloud.githubusercontent.com/assets/193864/10814177/17fb8bce-7e5f-11e5-8285-6b0100b3a0f8.gif)\n\n* Show usages of selected object\n  ![sample](https://cloud.githubusercontent.com/assets/193864/12263525/aff07ad4-b96a-11e5-949e-598e943b0190.gif)\n\n* Rename across multiple files. It will not touch files outside of your project, but it will change VCS ignored files. I'm not responsible for any broken projects without VCS because of this.\n  ![sample](https://cloud.githubusercontent.com/assets/193864/12288191/f448b55a-ba0c-11e5-81d7-31289ef5dbba.gif)\n\n# Configuration\n\n* If using a [virtualenv](https://virtualenv.pypa.io/en/latest/) with third-party packages, everything should \"just work\", but if it's not – use the `Python Executable Paths` and/or `Extra Paths For Packages` configuration options to specify the virtualenv's site-packages. Or launch Atom from the [activated virtualenv](https://virtualenv.pypa.io/en/latest/userguide.html#activate-script) to get completion for your third-party packages\n* Be sure to check package settings and adjust them. Please read them carefully before creating any new issues\n  * Set path to python executable if package cannot find it automatically\n  * Set extra path if package cannot autocomplete external python libraries\n  * Select one of autocomplete function parameters if you want function arguments to be completed\n\n  ![image](https://cloud.githubusercontent.com/assets/193864/11631369/aafb34b4-9d3c-11e5-9a06-e8712a21474e.png)\n\n\n# Common problems\n\n* \"Error: spawn UNKNOWN\" on Windows\n  * Solution: Find your python executable and uncheck the \"Run this program as an administrator\". See issue [#22](https://github.com/sadovnychyi/autocomplete-python/issues/22)\n* You have a separated folder for virtualenvs (e.g. by using `virtualenvwrapper`) and all your virtualenvs are stored in e.g. `~/.virtualenvs/`\n  * Create symlink to venv from your project root\n    * OR\n  * Add virtualenv folder as additional project root\n    * OR\n  * Use a virtualenv with the same name as the folder name of your project and use $PROJECT_NAME variable to set path to python executable.\n  You can use same variable to set extra paths as well. For example:\n  ```\n  /Users/name/.virtualenvs/$PROJECT_NAME/bin/python3.4\n  ```\n  * See issue [#143](https://github.com/sadovnychyi/autocomplete-python/issues/143)\n* No argument completion after I type left parenthesis character\n  * Likely this is because you have non standard keyboard layout.\n  Try to install the keyboard-localization package from: https://atom.io/packages/keyboard-localization\n  and use keymap generator to check what unicode character being generated after you type `(`.\n  Currently we trigger argument completion only on `U+0028`, `U+0038` and `U+0039`.\n",
                "readmeFilename": "README.md",
                "repository": {
                  "type": "git",
                  "url": "git+https://github.com/autocomplete-python/autocomplete-python.git"
                },
                "version": "1.8.26",
                "latestVersion": "1.8.27"
              },
              {
                "_args": [
                  [
                    {
                      "raw": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                      "scope": null,
                      "escapedName": null,
                      "name": null,
                      "rawSpec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                      "spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                      "type": "local"
                    },
                    "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/apm-install-dir-117017-63877-1aq1ykh"
                  ]
                ],
                "_from": "../d-117017-63877-vcgh4t/package.tgz",
                "_id": "file-icons@2.0.9",
                "_inCache": true,
                "_installable": true,
                "_location": "/file-icons",
                "_phantomChildren": {},
                "_requested": {
                  "raw": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                  "scope": null,
                  "escapedName": null,
                  "name": null,
                  "rawSpec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                  "spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                  "type": "local"
                },
                "_requiredBy": [
                  "#USER"
                ],
                "_resolved": "file:../d-117017-63877-vcgh4t/package.tgz",
                "_shasum": "8b2df93ad752af1676d91c12afa068f2000b864c",
                "_shrinkwrap": null,
                "_spec": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/d-117017-63877-vcgh4t/package.tgz",
                "_where": "/private/var/folders/3w/6wwjp8ps4h32xcxyw0shbkt80000gn/T/apm-install-dir-117017-63877-1aq1ykh",
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
                    "description": "Show different icon colours for modified files only. Requires that project be a Git repository.",
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
                    "description": "CSS class added to files that lack an icon.",
                    "order": 4
                  },
                  "strategies": {
                    "type": "object",
                    "title": "Match strategies",
                    "description": "Advanced settings for dynamic icon assignment.",
                    "order": 5,
                    "properties": {
                      "grammar": {
                        "type": "boolean",
                        "default": true,
                        "order": 1,
                        "title": "Change on grammar override",
                        "description": "Change a file's icon when manually setting its language."
                      },
                      "hashbangs": {
                        "type": "boolean",
                        "default": true,
                        "order": 2,
                        "title": "Check hashbangs",
                        "description": "Allow lines like `#!/usr/bin/perl` to affect icons."
                      },
                      "modelines": {
                        "type": "boolean",
                        "default": true,
                        "order": 3,
                        "title": "Check modelines",
                        "description": "Allow [Vim](http://vim.wikia.com/wiki/Modeline_magic) and [Emacs](https://www.gnu.org/software/emacs/manual/html_node/emacs/Specifying-File-Variables.html#Specifying-File-Variables) modelines to change icons."
                      },
                      "usertypes": {
                        "type": "boolean",
                        "default": true,
                        "order": 4,
                        "title": "Use custom file-types",
                        "description": "Respect the user's [custom language-type settings](http://flight-manual.atom.io/using-atom/sections/basic-customization/#customizing-language-recognition)."
                      },
                      "linguist": {
                        "type": "boolean",
                        "default": true,
                        "order": 5,
                        "title": "Use .gitattributes",
                        "description": "Honour [`linguist-language`](https://github.com/github/linguist#using-gitattributes) attributes in local `.gitattributes` files."
                      }
                    }
                  }
                },
                "dependencies": {
                  "micromatch": "*"
                },
                "description": "Assign file extension icons and colours for improved visual grepping",
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
                "readme": "File Icons\n==========\nFile-specific icons in Atom for improved visual grepping.\n\n<img alt=\"Icon previews\" width=\"850\" src=\"https://raw.githubusercontent.com/file-icons/atom/6714706f268e257100e03c9eb52819cb97ad570b/preview.png\" />\n\nSupports the following packages:\n\n* [`tree-view`](https://atom.io/packages/tree-view)\n* [`tabs`](https://atom.io/packages/tabs)\n* [`fuzzy-finder`](https://atom.io/packages/fuzzy-finder)\n* [`find-and-replace`](https://atom.io/packages/find-and-replace)\n* [`archive-view`](https://atom.io/packages/archive-view)\n\n\nInstallation\n------------\nOpen **Settings** → **Install** and search for `file-icons`.\n\nAlternatively, install through command-line:\n\n\tapm install file-icons\n\n\nCustomisation\n-------------\nEverything is handled using CSS classes. Use your [stylesheet][1] to change or tweak icons.\n\nConsult the package stylesheets to see what classes are used:\n\n* **Icons:**   [`styles/icons.less`](./styles/icons.less)\n* **Colours:** [`styles/colours.less`](./styles/colours.less)\n* **Fonts:**   [`styles/fonts.less`](./styles/fonts.less)\n\n\n#### Icon reference\n* [**File-Icons**](https://github.com/file-icons/source/blob/master/charmap.md) \n* [**FontAwesome**](http://fontawesome.io/cheatsheet/)\n* [**Mfizz**](https://github.com/file-icons/MFixx/blob/master/charmap.md)\n* [**Devicons**](https://github.com/file-icons/DevOpicons/blob/master/charmap.md)\n\n\n#### Examples\n\n* <a name=\"resize-an-icon\"></a>\n**Resize an icon:**\n\t~~~less\n\t.html5-icon:before{\n\t\tfont-size: 18px;\n\t}\n\t\n\t// Resize in tab-pane only:\n\t.tab > .html5-icon:before{\n\t\tfont-size: 18px;\n\t\ttop: 3px;\n\t}\n\t~~~\n\n\n* <a name=\"choose-your-own-shades-of-orange\"></a>\n**Choose your own shades of orange:**\n\t~~~css\n\t.dark-orange   { color: #6a1e05; }\n\t.medium-orange { color: #b8743d; }\n\t.light-orange  { color: #cf9b67; }\n\t~~~\n\n\n* <a name=\"bring-back-the-blue-shield-php-icon\"></a>\n**Bring back PHP's blue-shield icon:**\n\t~~~css\n\t.php-icon:before{\n\t\tfont-family: MFizz;\n\t\tcontent: \"\\f147\";\n\t}\n\t~~~\n\n\n* <a name=\"assign-icons-by-file-extension\"></a>\n**Assign icons by file extension:**\n\t~~~css\n\t.icon[data-name$=\".js\"]:before{\n\t\tfont-family: Devicons;\n\t\tcontent: \"\\E64E\";\n\t}\n\t~~~\n\n\n* <a name=\"assign-icons-to-directories\"></a>\n**Assign icons to directories:**\n\t~~~less\n\t.directory > .header > .icon{\n\t\t\n\t\t&[data-path$=\".atom/packages\"]:before{\n\t\t\tfont-family: \"Octicons Regular\";\n\t\t\tcontent: \"\\f0c4\";\n\t\t}\n\t}\n\t~~~\n\n\n\nTroubleshooting\n---------------\n\n<a name=\"an-icon-has-stopped-updating\"></a>\n**An icon has stopped updating:**  \nIt's probably a caching issue. Do the following:\n\n1. Open the command palette: <kbd>Cmd/Ctrl + Shift + P</kbd>\n2. Run `file-icons:clear-cache`\n3. Reload the window, or restart Atom\n\n\n<a name=\"the-tree-views-files-are-borked\"></a>\n**The tree-view's files are borked and [look like this][6]:**  \nIf you haven't restarted Atom since upgrading to [File-Icons v2][v2.0], do so now.\n\nIf restarting doesn't help, your stylesheet probably needs updating. See below.\n\n\n<a name=\"my-stylesheet-has-errors-since-updating\"></a>\n**My stylesheet has errors since updating:**  \nAs of [v2.0][], classes are used for displaying icons instead of mixins. Delete lines like these from your stylesheet:\n\n~~~diff\n-@import \"packages/file-icons/styles/icons\";\n-@import \"packages/file-icons/styles/items\";\n-@{pane-tab-selector},\n.icon-file-directory {\n\t&[data-name=\".git\"]:before {\n-\t\t.git-icon;\n+\t\tfont-family: Devicons;\n+\t\tcontent: \"\\E602\";\n\t}\n}\n~~~\n\nInstead of `@pane-tab…` variables, use `.tab > .icon[data-path]`:\n\n~~~diff\n-@pane-tab-selector,\n-@pane-tab-temp-selector,\n-@pane-tab-override {\n+.tab > .icon {\n \t&[data-path$=\".to.file\"] {\n \t\t\n \t}\n}\n~~~\n\nThese CSS classes are no longer used, so delete them:\n\n~~~diff\n-.file-icons-force-show-icons,\n-.file-icons-tab-pane-icon,\n-.file-icons-on-changes\n~~~\n\n\n**It's something else.**  \nPlease [file an issue][7]. Include screenshots if necessary.\n\n\nIntegration with other packages\n-------------------------------\nIf you're a package author, you can integrate File-Icons using Atom's services API:\n\nFirst, add this to your `package.json` file:\n\n```json\n\"consumedServices\": {\n\t\"file-icons.element-icons\": {\n\t\t\"versions\": {\n\t\t\t\"1.0.0\": \"consumeElementIcons\"\n\t\t}\n\t}\n}\n```\n\nSecondly, add a function named `consumeElementIcons` (or whatever you named it) to your package's main export:\n\n```js\nlet addIconToElement;\nmodule.exports.consumeElementIcons = function(func){\n\taddIconToElement = func;\n};\n```\n\nThen call the function it gets passed to display icons in the DOM:\n\n```js\nlet fileIcon = document.querySelector(\"li.file-entry > span.icon\");\naddIconToElement(fileIcon, \"/path/to/file.txt\");\n```\n\nThe returned value is a [`Disposable`][10] which clears the icon from memory once it's no longer needed:\n\n```js\nconst disposable = addIconToElement(fileIcon, \"/path/to/file.txt\");\nfileIcon.onDestroy(() => disposable.dispose());\n```\n\n**NOTE:** Remember to remove any default icon-classes before calling the service handler.\n\n```diff\n let fileIcon = document.querySelector(\"li.file-entry > span.icon\");\n+fileIcon.classList.remove(\"icon-file-text\");\n const disposable = addIconToElement(fileIcon, \"/path/to/file.txt\");\n```\n\n\nAcknowledgements\n----------------\nOriginally based on [sommerper/filetype-color][8], but now sporting a shiny new file-icons API in `v2` thanks to [Alhadis][11]!\nAlso thanks to all the [contributors][9]\n\n\n[Referenced links]: ____________________________________________________\n[1]: http://flight-manual.atom.io/using-atom/sections/basic-customization/#style-tweaks\n[4]: https://developer.mozilla.org/en-US/docs/Web/CSS/Attribute_selectors\n[5]: https://github.com/Alhadis/DevOpicons/blob/master/charmap.md#JavaScript\n[6]: https://cloud.githubusercontent.com/assets/714197/21516010/4b79a8a8-cd39-11e6-8394-1e3ab778af92.png\n[7]: https://github.com/file-icons/atom/issues/new\n[8]: https://github.com/sommerper/filetype-color\n[9]: https://github.com/file-icons/atom/graphs/contributors\n[10]: https://atom.io/docs/api/latest/Disposable\n[11]: https://github.com/Alhadis\n[v2.0]: https://github.com/file-icons/atom/releases/tag/v2.0.0\n",
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
