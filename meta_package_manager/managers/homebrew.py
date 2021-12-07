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
from click_extra.logging import logger
from click_extra.platform import LINUX, MACOS

from ..base import PackageManager
from ..version import parse_version


class Homebrew(PackageManager):

    """Virtual package manager shared by brew and cask CLI defined below.

    Homebrew is the umbrella project providing both brew and brew cask
    commands.
    """

    platforms = frozenset({LINUX, MACOS})

    # Vanilla brew and cask CLIs now shares the same version.
    # 2.7.0 is the first release to enforce the use of --cask option.
    requirement = "2.7.0"

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    cli_names = None

    version_regex = r"Homebrew\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► brew --version
        Homebrew 1.8.6-124-g6cd4c31
        Homebrew/homebrew-core (git revision 533d; last commit 2018-12-28)
        Homebrew/homebrew-cask (git revision 5095b; last commit 2018-12-28)
    """

    prepend_global_args = False

    def sync(self):
        """Fetch content of remote taps.

        .. code-block:: shell-session

            ► brew update --quiet
            Already up-to-date.
        """
        super().sync()
        self.run_cli("update", "--quiet", skip_globals=True)

    @property
    def installed(self):
        """List installed packages from ``brew list`` output.

        Raw CLI output samples:

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

        .. todo

            Use the ``removed`` variable to detect removed packages (which are
            reported with a ``(!)`` flag). See:
            https://github.com/caskroom/homebrew-cask/blob/master/doc
            /reporting_bugs/uninstall_wrongly_reports_cask_as_not_installed.md
            and https://github.com/kdeldycke/meta-package-manager/issues/17 .
        """
        installed = {}

        output = self.run_cli("list", "--versions")

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
            query = f"/^{query}$/"

        output = self.run_cli("search", query)

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

    def install(self, package_id):
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
            Updating Homebrew...
            ==> Downloading https://nukesaq.github.io/Pngyu/download/Pngyu_mac_101.zip
            ################################################################## 100.0%
            ==> Installing Cask pngyu
            ==> Moving App 'Pngyu.app' to '/Applications/Pngyu.app'
            🍺  pngyu was successfully installed!

        """
        super().install(package_id)
        return self.run_cli("install", package_id)

    @property
    def outdated(self):
        """Fetch outdated packages from ``brew outdated`` output.

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
                  "name": "qlcolorcode",
                  "installed_versions": "3.0.2",
                  "current_version": "3.1.1"
                }
              ]
            }
        """
        outdated = {}

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
                package_id = pkg_info["name"]
                version = pkg_info["installed_versions"]
                if not isinstance(version, str):
                    version = max(map(parse_version, version))
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

    def upgrade_cli(self, package_id=None):
        """Returns the right CLI depending on weither formula or cask are
        concerned:

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
        cmd = [self.cli_path, "upgrade", self.global_args]
        if package_id:
            cmd.append(package_id)
        return cmd

    def cleanup(self):
        """Scrub the cache, including latest version's downloads. Also remove unused
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
        super().cleanup()
        self.run_cli("autoremove", skip_globals=True)
        self.run_cli("cleanup", "-s", "--prune=all", skip_globals=True)


class Brew(Homebrew):

    name = "Homebrew Formulae"
    cli_names = ("brew",)

    global_args = ("--formula",)


class Cask(Homebrew):

    # Casks are only available on macOS, not Linux.
    platforms = frozenset({MACOS})
    name = "Homebrew Cask"
    cli_names = ("brew",)

    global_args = ("--cask",)
