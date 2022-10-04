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
import re
from operator import methodcaller
from typing import Iterator

from click_extra.platform import LINUX, MACOS

from .. import logger
from ..base import Package, PackageManager
from ..capabilities import version_not_implemented
from ..version import parse_version


class Homebrew(PackageManager):

    """Virtual package manager shared by brew and cask CLI defined below.

    Homebrew is the umbrella project providing both brew and brew cask commands.
    """

    platforms = frozenset({LINUX, MACOS})

    # Vanilla brew and cask CLIs now shares the same version.
    # 2.7.0 is the first release to enforce the use of --cask option.
    requirement = "2.7.0"

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    virtual = True

    extra_env = {
        # Disable analytics.
        "HOMEBREW_NO_ANALYTICS": "1",
        # Disable configuration hints to reduce verbosity.
        "HOMEBREW_NO_ENV_HINTS": "1",
        # Do not let brew mix the update operation with others. Mpm has a separate "sync" command for that.
        # This silo-ed behavior has been requested by user since the beginning of
        # mpm: https://github.com/kdeldycke/meta-package-manager/issues/36
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        # See: https://docs.brew.sh/FAQ#why-cant-i-open-a-mac-app-from-an-unidentified-developer
        # "HOMEBREW_CASK_OPTS": "--no-quarantine",
    }

    version_regex = r"Homebrew\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► brew --version
        Homebrew 1.8.6-124-g6cd4c31
        Homebrew/homebrew-core (git revision 533d; last commit 2018-12-28)
        Homebrew/homebrew-cask (git revision 5095b; last commit 2018-12-28)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► brew list --versions --formula
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

            ► brew list --versions --cask
            aerial 1.2beta5
            android-file-transfer latest
            audacity (!) 2.1.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16
            tunnelblick 3.6.8_build_4625 3.6.9_build_4685
            virtualbox 5.1.8-111374 5.1.10-112026

        .. todo::

            Use the ``removed`` variable to detect removed packages (which are
            reported with a ``(!)`` flag). See:
            https://github.com/caskroom/homebrew-cask/blob/master/doc
            /reporting_bugs/uninstall_wrongly_reports_cask_as_not_installed.md
            and https://github.com/kdeldycke/meta-package-manager/issues/17 .
        """
        output = self.run_cli("list", "--versions")

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)     # Any non-empty characters.
            (?P<removed> \(!\))?    # Package removed flag.
            \                       # A space.
            (?P<versions>.+)        # Versions.
            """,
            re.VERBOSE,
        )

        for package_id, removed, versions in map(
            methodcaller("groups"), regexp.finditer(output)
        ):
            # Keep highest version found.
            version = max(map(parse_version, versions.split()))
            yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► brew outdated --json=v2 --formula | jq
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

        .. code-block:: shell-session

            ► brew outdated --json=v2 --cask | jq
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

            ► brew outdated --json=v2 --greedy --cask | jq
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
                  "name": "lg-onscreen-control",
                  "installed_versions": "5.33,cV8xqv5TSZA.upgrading, 5.47,yi5XuIZw6hg",
                  "current_version": "5.48,uYXSwyUCNFBbSch9PFw"
                }
              ]
            }
        """
        # Build up the list of CLI options.
        options = ["--json=v2"]
        # Includes auto-update packages or not.
        if not self.ignore_auto_updates:
            options.append("--greedy")

        # List available updates.
        output = self.run_cli("outdated", options)

        if output:
            package_list = json.loads(output)
            for pkg_info in package_list["formulae"] + package_list["casks"]:

                # Interpret installed versions.
                versions = pkg_info["installed_versions"]
                if isinstance(versions, str):
                    versions = versions.split(", ")
                installed_version = max(map(parse_version, versions))

                latest_version = parse_version(pkg_info["current_version"])

                # Skip packages not offering upgradeable version.
                package_id = pkg_info["name"]
                if installed_version == latest_version:
                    logger.debug(
                        f"Ignore {package_id} upgrade from {installed_version} to {latest_version}."
                    )
                    continue

                yield self.package(
                    id=package_id,
                    installed_version=installed_version,
                    latest_version=latest_version,
                )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports extended mode.

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

            ► brew search sed --formulae
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised

        .. code-block:: shell-session

            ► brew search sed --cask
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            ► brew search python --formulae
            ==> Formulae
            app-engine-python   boost-python3   python ✔          python-yq
            boost-python        gst-python      python-markdown   python@3.8 ✔

        .. code-block:: shell-session

            ► brew search "/^ssed$/" --formulae
            ==> Formulae
            ssed

        .. code-block:: shell-session

            ► brew search "/^sed$/" --formulae
            Error: No formula or cask found for "/^sed$/".

        .. code-block:: shell-session

            ► brew search tetris --formulae --desc
            ==> Formulae
            bastet: Bastard Tetris
            netris: Networked variant of tetris
            vitetris: Terminal-based Tetris clone
            yetris: Customizable Tetris for the terminal

        .. code-block:: shell-session

            ► brew search tetris --cask --desc
            ==> Casks
            not-tetris: (Not Tetris) [no description]
            tetrio: (TETR.IO) Free-to-play Tetris clone

        More doc at: https://docs.brew.sh/Manpage#search--s-options-textregex-
        """
        # Keep track of package IDs already matched by the first extended search pass.
        matched_ids = set()

        # Additional search on description only.
        if extended:
            output = self.run_cli("search", query, "--desc")

            regexp = re.compile(
                r"""
                (?:==>\s\S+\s)?           # Ignore section starting with '==>'.
                (?P<package_id>\S+)       # Any non-empty characters.
                :                         # Semi-colon.
                (                         # Optional group start (ignored below with "_" variable).
                    \s+                   # Blank characters.
                    \(                    # Opening parenthesis.
                    (?P<package_name>.+)  # Any string.
                    \)                    # Closing parenthesis.
                )?                        # Optional group end.
                \s+                       # Blank characters.
                (?P<description>.+)       # Any string.
                """,
                re.VERBOSE,
            )

            for package_id, _, package_name, description in regexp.findall(output):
                matched_ids.add(package_id)
                pkg = self.package(id=package_id, name=package_name)
                if description != "[no description]":
                    pkg.description = description
                yield pkg

        # Use regexp if exact match is requested.
        if exact:
            query = f"/^{query}$/"

        output = self.run_cli("search", query)

        regexp = re.compile(
            r"""
            (?:==>\s\S+\s)?           # Ignore section starting with '==>'.
            (?P<package_id>[^\s✔]+)   # Anything not a whitespace or ✔.
            """,
            re.VERBOSE,
        )

        for package_id in regexp.findall(output):
            # Deduplicate search results.
            if package_id not in matched_ids:
                yield self.package(id=package_id)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► brew install jpeginfo --formula
            ==> Downloading https://ghcr.io/core/jpeginfo/manifests/1.6.1_1-1
            ############################################################## 100.0%
            ==> Downloading https://ghcr.io/core/jpeginfo/blobs/sha256:27bb35884368b83
            ==> Downloading from https://pkg.githubcontent.com/ghcr1/blobs/sha256:27bb3
            ############################################################## 100.0%
            ==> Pouring jpeginfo--1.6.1_1.big_sur.bottle.1.tar.gz
            🍺  /usr/local/Cellar/jpeginfo/1.6.1_1: 7 files, 77.6KB

        .. code-block:: shell-session

            ► brew install pngyu --cask
            ==> Downloading https://nukesaq.github.io/Pngyu/download/Pngyu_mac_101.zip
            ################################################################## 100.0%
            ==> Installing Cask pngyu
            ==> Moving App 'Pngyu.app' to '/Applications/Pngyu.app'
            🍺  pngyu was successfully installed!
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        ``brew`` and ``cask`` share the same command.

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
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        ``brew`` and ``cask`` share the same command.

        .. code-block:: shell-session

            ► brew upgrade dupeguru --cask
            ==> Upgrading 1 outdated package:
            dupeguru 4.2.0 -> 4.2.1
            ==> Upgrading dupeguru
            ==> Downloading https://github.com/arsenetar/dupeguru/releases/download/4.2.1/dupeguru_macOS_Qt_4.2.1.zi
            ==> Downloading from https://objects.githubusercontent.com/github-production-release-asset-2e65be/108563
            ######################################################################## 100.0%
            ==> Backing App 'dupeguru.app' up to '/opt/homebrew/Caskroom/dupeguru/4.2.0/dupeguru.app'
            ==> Removing App '/Applications/dupeguru.app'
            ==> Moving App 'dupeguru.app' to '/Applications/dupeguru.app'
            ==> Purging files for version 4.2.0 of Cask dupeguru
            🍺  dupeguru was successfully upgraded!
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        .. code-block:: shell-session

            ► brew uninstall bat
            Uninstalling /usr/local/Cellar/bat/0.21.0... (14 files, 5MB)
        """
        return self.run_cli("uninstall", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► brew update --quiet
            Already up-to-date.
        """
        self.run_cli("update", "--quiet", auto_post_args=False)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        Scrub the cache, including latest version's downloads. Also remove unused
        dependencies.

        Downloads for all installed formulae and casks will not be deleted.

        .. code-block:: shell-session

            ► brew cleanup -s --prune=all
            Removing: ~/Library/Caches/Homebrew/node--1.bottle.tar.gz... (9MB)
            Warning: Skipping sdl2: most recent version 2.0.12_1 not installed
            Removing: ~/Library/Caches/Homebrew/Cask/aerial--1.8.1.zip... (5MB)
            Removing: ~/Library/Caches/Homebrew/Cask/prey--1.9.pkg... (19.9MB)
            Removing: ~/Library/Logs/Homebrew/readline... (64B)
            Removing: ~/Library/Logs/Homebrew/libfido2... (64B)
            Removing: ~/Library/Logs/Homebrew/libcbor... (64B)

        More doc at: https://docs.brew.sh/Manpage#cleanup-options-formulacask

        .. code-block:: shell-session

            ► brew autoremove
            ==> Uninstalling 17 unneeded formulae:
            gtkmm3
            highlight
            lua@5.1
            nasm
            nghttp2
            texi2html
            Uninstalling /usr/local/Cellar/nghttp2/1.41.0_1... (26 files, 2.7MB)
            Uninstalling /usr/local/Cellar/highlight/3.59... (558 files, 3.5MB)

            Warning: The following highlight configuration files have not been removed!
            If desired, remove them manually with `rm -rf`:
              /usr/local/etc/highlight
              /usr/local/etc/highlight/filetypes.conf
              /usr/local/etc/highlight/filetypes.conf.default
            Uninstalling /usr/local/Cellar/gtkmm3/3.24.2_1... (1,903 files, 173.7MB)
            Uninstalling /usr/local/Cellar/texi2html/5.0... (279 files, 6.2MB)
            Uninstalling /usr/local/Cellar/lua@5.1/5.1.5_8... (22 files, 245.6KB)
            Uninstalling /usr/local/Cellar/nasm/2.15.05... (29 files, 2.9MB)
        """
        self.run_cli("autoremove", auto_post_args=False)
        self.run_cli("cleanup", "-s", "--prune=all", auto_post_args=False)


class Brew(Homebrew):

    name = "Homebrew Formulae"

    homepage_url = "https://brew.sh"

    cli_names = ("brew",)

    post_args = ("--formula",)


class Cask(Homebrew):

    name = "Homebrew Cask"

    homepage_url = "https://caskroom.github.io"

    # Casks are only available on macOS, not Linux.
    platforms = frozenset({MACOS})

    cli_names = ("brew",)

    post_args = ("--cask",)
