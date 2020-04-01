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


class Homebrew(PackageManager):

    """ Virutal package manager shared by brew and cask CLI defined below.

    Homebrew is the umbrella project providing both brew and brew cask
    commands.
    """

    platforms = frozenset([MACOS])

    # Vanilla brew and cask CLIs now shares the same version.
    # 2.2.9 is the first release to support --formulae option in search.
    requirement = '2.2.9'

    # Declare this manager as virtual, i.e. not tied to a real CLI.
    cli_name = None

    def get_version(self):
        """ Fetch version from ``brew --version`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew --version
            Homebrew 1.8.6-124-g6cd4c31
            Homebrew/homebrew-core (git revision 533d; last commit 2018-12-28)
            Homebrew/homebrew-cask (git revision 5095b; last commit 2018-12-28)

        """
        output = self.run([self.cli_path] + ['--version'])
        if output:
            return parse_version(output.split()[1])

    def sync(self):
        """ `brew` and `cask` share the same command. """
        super(Homebrew, self).sync()
        self.run([self.cli_path] + ['update', '--quiet'])

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``brew list`` output.

        .. note::

            This method is shared by ``brew`` and ``cask``, only that the
            latter adds its ``cask`` subcommand to the CLI call.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew list --versions
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

            $ brew cask list --versions
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

        .. todo

            Use the ``removed`` variable to detect removed packages (which are
            reported with a ``(!)`` flag). See:
            https://github.com/caskroom/homebrew-cask/blob/master/doc
            /reporting_bugs/uninstall_wrongly_reports_cask_as_not_installed.md
            and https://github.com/kdeldycke/meta-package-manager/issues/17 .
        """
        installed = {}

        output = self.run(
            [self.cli_path] + self.global_args + ['list', '--versions'])

        if output:
            regexp = re.compile(r'(\S+)( \(!\))? (.+)')
            for pkg_info in output.splitlines():
                match = regexp.match(pkg_info)
                if match:
                    package_id, removed, versions = match.groups()
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version':
                            # Keep highest version found.
                            max(map(parse_version, versions.split()))}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``brew search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew search sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne

        .. code-block:: shell-session

            $ brew search --formulae sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised

        .. code-block:: shell-session

            $ brew search --cask sed
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne
        """
        matches = {}

        output = self.run(self.search_cli + [query])

        if output:
            lines = [
                l for l in output.splitlines()
                if l and not l.startswith('==>')]
            for package_id in re.compile(r'[\s✔]+').split(' '.join(lines)):
                if package_id:
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': None,
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``brew outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew outdated --json=v1
            [
              {
                "name": "cassandra",
                "installed_versions": [
                  "3.5"
                ],
                "current_version": "3.7"
              },
              {
                "name": "vim",
                "installed_versions": [
                  "7.4.1967"
                ],
                "current_version": "7.4.1993"
              },
              {
                "name": "youtube-dl",
                "installed_versions": [
                  "2016.07.06"
                ],
                "current_version": "2016.07.09.1"
              }
            ]
        """
        outdated = {}

        # List available updates.
        output = self.run(
            [self.cli_path] + self.global_args + ['outdated', '--json=v1'])

        if output:
            for pkg_info in json.loads(output):
                package_id = pkg_info['name']
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': max(map(
                        parse_version, pkg_info['installed_versions'])),
                    'latest_version':
                        parse_version(pkg_info['current_version'])}

        return outdated

    def upgrade_cli(self, package_id=None):
        """ Runs:

        .. code-block:: shell-session

            $ brew upgrade
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
        cmd = [self.cli_path] + self.global_args + ['upgrade']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()

    def cleanup(self):
        """ Scrub the cache, including downloads for even the latest versions.

        Note downloads for any installed formulae or casks will still not be
        deleted.

        .. code-block:: shell-session

            $ brew cleanup -s
            Removing: ~/Library/Caches/Homebrew/node--1.bottle.tar.gz... (9MB)
            Warning: Skipping sdl2: most recent version 2.0.12_1 not installed
            Removing: ~/Library/Caches/Homebrew/Cask/aerial--1.8.1.zip... (5MB)
            Removing: ~/Library/Caches/Homebrew/Cask/prey--1.9.pkg... (19.9MB)
            Removing: ~/Library/Logs/Homebrew/readline... (64B)
            Removing: ~/Library/Logs/Homebrew/libfido2... (64B)
            Removing: ~/Library/Logs/Homebrew/libcbor... (64B)

        More doc at: https://docs.brew.sh/Manpage#cleanup-options-formulacask
        """
        super(Homebrew, self).cleanup()
        self.run([self.cli_path, 'cleanup', '-s'])


class Brew(Homebrew):

    name = "Homebrew Formulae"
    cli_name = 'brew'

    @cachedproperty
    def search_cli(self):
        """ Returns the CLI to run search on Homebrew formulae.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew search --formulae sed
            ==> Formulae
            gnu-sed ✔                    libxdg-basedir               minised
        """
        return [self.cli_path] + self.global_args + ['search', '--formulae']


class Cask(Homebrew):

    """ Cask is now part of Homebrew's core and extend it.
    """

    name = "Homebrew Cask"
    cli_name = 'brew'

    global_args = ['cask']

    @cachedproperty
    def search_cli(self):
        """ Returns the CLI to run search on Homebrew casks.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew search --cask sed
            ==> Casks
            eclipse-dsl                       marsedit
            focused                           physicseditor
            google-adwords-editor             prefs-editor
            licensed                          subclassed-mnemosyne
        """
        return [self.cli_path, 'search', '--cask']

    @cachedproperty
    def outdated(self):
        """ Search for outdated packages among installed one.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew cask outdated
            google-play-music-desktop-player (4.4.0) != 4.4.1

        .. code-block:: shell-session

            $ brew cask outdated --verbose
            java (9.0.1,11) != 10,46:76eac37278c24557a3c4199677f19b62
            prey (1.7.2) != 1.7.3
            qlvideo (1.90) != 1.91
            virtualbox (5.2.4-119785) != 5.2.8,121009

        .. code-block:: shell-session

            $ brew cask outdated --greedy --verbose
            android-file-transfer (latest) != latest
            atom (1.19.3) != 1.19.4
            dropbox (latest) != latest
            google-chrome (latest) != latest
            google-drive (latest) != latest
            google-play-music-desktop-player (4.4.0) != 4.4.1
            karabiner-elements (0.90.92) != 0.91.13
            osxfuse (3.5.6) != 3.6.3
            qlimagesize (latest) != latest
            qlrest (latest) != latest
            quicklook-json (latest) != latest
            steam (latest) != latest
        """
        outdated = {}

        # Build up the list of CLI options.
        options = ['--verbose']
        # Includes auto-update packages or not.
        if not self.ignore_auto_updates:
            options.append('--greedy')

        # List available updates.
        output = self.run(
            [self.cli_path] + self.global_args + ['outdated'] +
            options)

        if output:
            regexp = re.compile(r'(\S+) \((.*)\) != (.*)')
            for outdated_pkg in output.strip().splitlines():
                package_id, version, latest_version = regexp.match(
                    outdated_pkg).groups()

                # Skip packages in undetermined state.
                if version == latest_version:
                    continue

                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': parse_version(version),
                    'latest_version': parse_version(latest_version)}

        return outdated

    def upgrade_cli(self, package_id=None):
        """ Install a package. """
        cmd = [self.cli_path] + self.global_args + ['upgrade']
        if package_id:
            cmd.append(package_id)
        return cmd
