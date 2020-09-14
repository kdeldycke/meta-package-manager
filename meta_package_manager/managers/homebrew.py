# -*- coding: utf-8 -*-
#
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
from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import MACOS
from ..version import parse_version
from . import logger


class Homebrew(PackageManager):

    """Virutal package manager shared by brew and cask CLI defined below.

    Homebrew is the umbrella project providing both brew and brew cask
    commands.
    """

    platforms = frozenset([MACOS])

    # Vanilla brew and cask CLIs now shares the same version.
    # 2.5.0 is the first release to deprecate the use of --json=v1 option.
    requirement = "2.5.0"

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    cli_name = None

    def get_version(self):
        """Fetch version from ``brew --version`` output.

        .. code-block:: shell-session

            ► brew --version
            Homebrew 1.8.6-124-g6cd4c31
            Homebrew/homebrew-core (git revision 533d; last commit 2018-12-28)
            Homebrew/homebrew-cask (git revision 5095b; last commit 2018-12-28)

        """
        output = self.run_cli("--version")
        if output:
            return parse_version(output.split()[1])

    def sync(self):
        """`brew` and `cask` share the same command.

        .. code-block:: shell-session

            ► brew update --quiet
            Already up-to-date.
        """
        super().sync()
        self.run_cli("update", "--quiet")

    @property
    def installed(self):
        """Fetch installed packages from ``brew list`` output.

        .. note::

            This method is shared by ``brew`` and ``cask``, only that the
            latter adds its ``cask`` subcommand to the CLI call.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► brew list --versions
            ack 2.14
            apg 2.2.3
            audacity (!) 2.1.2
            apple-gcc42 4.2.1-5666.3
            atk 2.22.0
            bash 4.4.5
            bash-completion 1.3_1
            boost 1.63.0
            c-ares 1.12.0
            graphviz 2.40.1 2.40.20161221.0239
            quicklook-json latest

        .. code-block:: shell-session

            ► brew cask list --versions
            aerial 1.2beta5
            android-file-transfer latest
            audacity (!) 2.1.2
            bitbar 1.9.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16
            tunnelblick 3.6.8_build_4625 3.6.9_build_4685
            virtualbox 5.1.8-111374 5.1.10-112026

        Alternatives since 2.4.7 (see
        https://github.com/Homebrew/brew/pull/7949 and
        https://github.com/Homebrew/brew/pull/7966):

        .. code-block:: shell-session

            ► brew list --cask --versions
            aerial 1.2beta5
            android-file-transfer latest
            audacity (!) 2.1.2
            bitbar 1.9.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16
            tunnelblick 3.6.8_build_4625 3.6.9_build_4685
            virtualbox 5.1.8-111374 5.1.10-112026

            ► brew cask list --json --versions | jq
            [
              {
                "token": "aerial",
                "name": [
                  "Aerial Screensaver"
                ],
                "homepage": "https://github.com/JohnCoates/Aerial",
                "url": "https://github.com/(...)/download/v1.9.2/Aerial.zip",
                "appcast": "https://github.com/(...)/releases.atom",
                "version": "1.9.2",
                "sha256": "1d21511a31895ece4a18c93c779cbf4e35a611a27ba",
                "artifacts": [
                  [
                    "Aerial.saver"
                  ],
                  {
                    "trash": "~/Library/Caches/Aerial",
                    "signal": {}
                  }
                ],
                "caveats": null,
                "depends_on": {},
                "conflicts_with": null,
                "container": null,
                "auto_updates": null
              },
              {
                "token": "dropbox",
                "name": [
                  "Dropbox"
                ],
                "homepage": "https://www.dropbox.com/",
                "url": "https://www.dropbox.com/download?plat=mac&full=1",
                "appcast": null,
                "version": "latest",
                "sha256": "no_check",
                "artifacts": [
                  {
                    "launchctl": "com.dropbox.DropboxMacUpdate.agent",
                    "signal": {}
                  },
                  [
                    "Dropbox.app"
                  ],
                  {
                    "trash": [
                      "/Library/DropboxHelperTools",
                      "~/.dropbox",
                      "~/Library/Application Support/Dropbox",
                      "~/Library/Caches/com.dropbox.DropboxMacUpdate",
                      "~/Library/Caches/com.getdropbox.DropboxMetaInstaller",
                      "~/Library/Caches/com.getdropbox.dropbox",
                      "~/Library/Containers/com.dropbox.activityprovider",
                      "~/Library/Containers/com.dropbox.foldertagger",
                      "~/Library/Containers/com.getdropbox.dropbox.garcon",
                      "~/Library/Dropbox",
                      "~/Library/Group Containers/com.dropbox.client.crashpad",
                      "~/Library/Logs/Dropbox_debug.log",
                      "~/Library/Preferences/com.dropbox.DropboxMonitor.plist",
                      "~/Library/Preferences/com.getdropbox.dropbox.plist"
                    ],
                    "signal": {}
                  }
                ],
                "caveats": null,
                "depends_on": {},
                "conflicts_with": {
                  "cask": [
                    "dropbox-beta"
                  ]
                },
                "container": null,
                "auto_updates": null
              },
              (...)
            ]

        .. todo

            Use the ``removed`` variable to detect removed packages (which are
            reported with a ``(!)`` flag). See:
            https://github.com/caskroom/homebrew-cask/blob/master/doc
            /reporting_bugs/uninstall_wrongly_reports_cask_as_not_installed.md
            and https://github.com/kdeldycke/meta-package-manager/issues/17 .
        """
        installed = {}

        output = self.run_cli(self.global_args, "list", "--versions")

        if output:
            regexp = re.compile(r"(\S+)( \(!\))? (.+)")
            for pkg_info in output.splitlines():
                match = regexp.match(pkg_info)
                if match:
                    package_id, removed, versions = match.groups()
                    installed[package_id] = {
                        "id": package_id,
                        "name": package_id,
                        "installed_version":
                        # Keep highest version found.
                        max(map(parse_version, versions.split())),
                    }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages from ``brew search`` output.

        .. code-block:: shell-session

            ► brew search sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            ► brew search --formulae sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised

        .. code-block:: shell-session

            ► brew search --cask sed
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            ► brew search --formulae python
            ==> Formulae
            app-engine-python   boost-python3   python ✔          python-yq
            boost-python        gst-python      python-markdown   python@3.8 ✔

        .. code-block:: shell-session

            ► brew search --formulae "/^ssed$/"
            ==> Formulae
            ssed

        .. code-block:: shell-session

            ► brew search --formulae "/^sed$/"
            No formula or cask found for "/^sed$/".
            Closed pull requests:
            Merge ba7a794 (https://github.com/Homebrew/linuxbrew-core/pull/198)
            R: disable Tcl (https://github.com/Homebrew/homebrew-core/pull/521)
            (...)

        More doc at: https://docs.brew.sh/Manpage#search-texttext
        """
        matches = {}

        if extended:
            logger.warning(
                f"Extended search not supported for {self.id}. Fallback to Fuzzy."
            )

        # Use regexp for exact match.
        if exact:
            query = "/^{}$/".format(query)

        output = self.run_cli(self.search_args, query)

        if output:
            regexp = re.compile(
                r"""
                (?:==>\s\S+\s)?           # Ignore section starting with '==>'.
                (?P<package_id>[^\s✔]+)   # Anything not a whitespace or ✔.
                """,
                re.VERBOSE,
            )

            for package_id in regexp.findall(output):
                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": None,
                }

        return matches

    def upgrade_cli(self, package_id=None):
        """Returns the right CLI depending on weither formula or cask are
        concerned:

        .. code-block:: shell-session

            ► brew upgrade --formula
            ==> Upgrading 2 outdated packages:
            node 13.11.0 -> 13.12.0
            sdl2 2.0.12 -> 2.0.12_1
            ==> Upgrading node 13.11.0 -> 13.12.0
            ==> Downloading https://homebrew.bintray.com/bottles/node-13.tar.gz
            ==> Downloading from https://akamai.bintray.com/fc/fc0bfb42fe23e960
            ############################################################ 100.0%
            ==> Pouring node-13.12.0.catalina.bottle.tar.gz
            ==> Caveats
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d
            ==> Summary
            🍺  /usr/local/Cellar/node/13.12.0: 4,660 files, 60.3MB
            Removing: /usr/local/Cellar/node/13.11.0... (4,686 files, 60.4MB)
            ==> Upgrading sdl2 2.0.12 -> 2.0.12_1
            ==> Downloading https://homebrew.bintray.com/bottles/sdl2-2.tar.gz
            ==> Downloading from https://akamai.bintray.com/4d/4dcd635465d16372
            ############################################################ 100.0%
            ==> Pouring sdl2-2.0.12_1.catalina.bottle.tar.gz
            🍺  /usr/local/Cellar/sdl2/2.0.12_1: 89 files, 4.7MB
            Removing: /usr/local/Cellar/sdl2/2.0.12... (89 files, 4.7MB)
            ==> Checking for dependents of upgraded formulae...
            ==> No dependents found!
            ==> Caveats
            ==> node
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d

        .. code-block:: shell-session

            ► brew upgrade --cask
            Updating Homebrew...
            ==> Auto-updated Homebrew!
            Updated Homebrew from 1654de327 to cfa03c8cc.
            Updated 2 taps (homebrew/core and homebrew/cask).
            ==> Casks with `auto_updates` or `version :latest` will not be upgraded
            ==> Upgrading 1 outdated packages:
            aerial 2.0.7 -> 2.0.8
            ==> Upgrading aerial
            ==> Downloading https://github.com/Aerial/download/v2.0.8/Aerial.saver.zip
            ==> Downloading from https://65be.s3.amazonaws.com/44998092/29eb1e0
            ==> Verifying SHA-256 checksum for Cask 'aerial'.
            ==> Backing Screen Saver up to '/usr/local/Caskroom/Aerial.saver'.
            ==> Removing Screen Saver '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Moving Screen Saver to '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Purging files for version 2.0.7 of Cask aerial
            🍺  aerial was successfully upgraded!
        """
        cmd = [self.cli_path] + self.upgrade_args
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()

    def cleanup(self):
        """Scrub the cache, including downloads for even the latest versions.

        Note downloads for any installed formulae or casks will still not be
        deleted.

        .. code-block:: shell-session

            ► brew cleanup -s
            Removing: ~/Library/Caches/Homebrew/node--1.bottle.tar.gz... (9MB)
            Warning: Skipping sdl2: most recent version 2.0.12_1 not installed
            Removing: ~/Library/Caches/Homebrew/Cask/aerial--1.8.1.zip... (5MB)
            Removing: ~/Library/Caches/Homebrew/Cask/prey--1.9.pkg... (19.9MB)
            Removing: ~/Library/Logs/Homebrew/readline... (64B)
            Removing: ~/Library/Logs/Homebrew/libfido2... (64B)
            Removing: ~/Library/Logs/Homebrew/libcbor... (64B)

        More doc at: https://docs.brew.sh/Manpage#cleanup-options-formulacask
        """
        super().cleanup()
        self.run_cli("cleanup", "-s")


class Brew(Homebrew):

    name = "Homebrew Formulae"
    cli_name = "brew"

    @cachedproperty
    def search_args(self):
        """Returns arguments needed for search of Homebrew formulae.

        .. code-block:: shell-session

            ► brew search --formulae sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised
        """
        return [self.global_args, "search", "--formulae"]

    @property
    def outdated(self):
        """Fetch outdated formulae from ``brew outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            ► brew outdated --formula --json=v2 | jq
            {
              "formulae": [
                {
                  "name": "pygobject3",
                  "installed_versions": [
                    "3.36.1"
                  ],
                  "current_version": "3.38.0",
                  "pinned": false,
                  "pinned_version": null
                },
                {
                  "name": "rav1e",
                  "installed_versions": [
                    "0.3.3"
                  ],
                  "current_version": "0.3.4",
                  "pinned": false,
                  "pinned_version": null
                }
              ],
              "casks": []
            }
        """
        outdated = {}

        # List available updates.
        output = self.run_cli(self.global_args, "outdated", "--formula", "--json=v2")

        if output:
            for pkg_info in json.loads(output)["formulae"]:
                package_id = pkg_info["name"]
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": max(
                        map(parse_version, pkg_info["installed_versions"])
                    ),
                    "latest_version": parse_version(pkg_info["current_version"]),
                }

        return outdated

    @cachedproperty
    def upgrade_args(self):
        """Returns arguments needed for upgrade of Homebrew formulae.

        .. code-block:: shell-session

            ► brew upgrade --formula
            ==> Upgrading 2 outdated packages:
            node 13.11.0 -> 13.12.0
            sdl2 2.0.12 -> 2.0.12_1
            ==> Upgrading node 13.11.0 -> 13.12.0
            ==> Downloading https://homebrew.bintray.com/bottles/node-13.tar.gz
            ==> Downloading from https://akamai.bintray.com/fc/fc0bfb42fe23e960
            ############################################################ 100.0%
            ==> Pouring node-13.12.0.catalina.bottle.tar.gz
            ==> Caveats
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d
            ==> Summary
            🍺  /usr/local/Cellar/node/13.12.0: 4,660 files, 60.3MB
            Removing: /usr/local/Cellar/node/13.11.0... (4,686 files, 60.4MB)
            ==> Upgrading sdl2 2.0.12 -> 2.0.12_1
            ==> Downloading https://homebrew.bintray.com/bottles/sdl2-2.tar.gz
            ==> Downloading from https://akamai.bintray.com/4d/4dcd635465d16372
            ############################################################ 100.0%
            ==> Pouring sdl2-2.0.12_1.catalina.bottle.tar.gz
            🍺  /usr/local/Cellar/sdl2/2.0.12_1: 89 files, 4.7MB
            Removing: /usr/local/Cellar/sdl2/2.0.12... (89 files, 4.7MB)
            ==> Checking for dependents of upgraded formulae...
            ==> No dependents found!
            ==> Caveats
            ==> node
            Bash completion has been installed to:
              /usr/local/etc/bash_completion.d
        """
        return [self.global_args, "upgrade", "--formula"]


class Cask(Homebrew):

    """Cask is now part of Homebrew's core and extend it."""

    name = "Homebrew Cask"
    cli_name = "brew"

    global_args = ["cask"]

    @cachedproperty
    def search_args(self):
        """Returns arguments needed for search of Homebrew casks.

        .. code-block:: shell-session

            ► brew search --cask sed
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne
        """
        return ["search", "--cask"]

    @property
    def outdated(self):
        """Fetch outdated casks from ``brew outdated`` output.

        .. code-block:: shell-session

            ► brew outdated --cask --json=v2 | jq
            {
              "formulae": [],
              "casks": [
                {
                  "name": "electrum",
                  "installed_versions": "4.0.2",
                  "current_version": "4.0.3"
                },
                {
                  "name": "qlcolorcode",
                  "installed_versions": "3.0.2",
                  "current_version": "3.1.1"
                }
              ]
            }

        .. code-block:: shell-session

            ► brew outdated --cask --json=v2 --greedy | jq
            {
              "formulae": [],
              "casks": [
                {
                  "name": "amethyst",
                  "installed_versions": "0.14.3",
                  "current_version": "0.15.3"
                },
                {
                  "name": "balenaetcher",
                  "installed_versions": "1.5.106",
                  "current_version": "1.5.108"
                },
                {
                  "name": "caldigit-thunderbolt-charging",
                  "installed_versions": "latest",
                  "current_version": "latest"
                },
                {
                  "name": "electrum",
                  "installed_versions": "4.0.2",
                  "current_version": "4.0.3"
                },
                {
                  "name": "qlcolorcode",
                  "installed_versions": "3.0.2",
                  "current_version": "3.1.1"
                }
              ]
            }
        """
        outdated = {}

        # Build up the list of CLI options.
        options = ["--cask", "--json=v2"]
        # Includes auto-update packages or not.
        if not self.ignore_auto_updates:
            options.append("--greedy")

        # List available updates.
        output = self.run_cli("outdated", options)

        if output:
            for pkg_info in json.loads(output)["casks"]:
                package_id = pkg_info["name"]
                version = pkg_info["installed_versions"]
                latest_version = pkg_info["current_version"]

                # Skip packages in undetermined state.
                if version == latest_version:
                    continue

                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(version),
                    "latest_version": parse_version(latest_version),
                }

        return outdated

    @cachedproperty
    def upgrade_args(self):
        """Returns arguments needed for upgrade of Homebrew casks.

        .. code-block:: shell-session

            ► brew upgrade --cask
            Updating Homebrew...
            ==> Auto-updated Homebrew!
            Updated Homebrew from 1654de327 to cfa03c8cc.
            Updated 2 taps (homebrew/core and homebrew/cask).
            ==> Casks with `auto_updates` or `version :latest` will not be upgraded
            ==> Upgrading 1 outdated packages:
            aerial 2.0.7 -> 2.0.8
            ==> Upgrading aerial
            ==> Downloading https://github.com/Aerial/download/v2.0.8/Aerial.saver.zip
            ==> Downloading from https://65be.s3.amazonaws.com/44998092/29eb1e0
            ==> Verifying SHA-256 checksum for Cask 'aerial'.
            ==> Backing Screen Saver up to '/usr/local/Caskroom/Aerial.saver'.
            ==> Removing Screen Saver '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Moving Screen Saver to '/Users/kde/Library/Screen Savers/Aerial.saver'.
            ==> Purging files for version 2.0.7 of Cask aerial
            🍺  aerial was successfully upgraded!
        """
        return ["upgrade", "--cask"]
