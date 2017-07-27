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
import re

from boltons.cacheutils import cachedproperty
from packaging.version import parse as parse_version

from ..base import PackageManager
from ..platform import MACOS


class Homebrew(PackageManager):

    platforms = frozenset([MACOS])

    requirement = '>= 1.0.*'

    id = "brew"

    def get_version(self):
        """ Fetch version from ``brew --version`` output."""
        output = self.run([self.cli_path] + self.cli_args + ['--version'])
        if output:
            return output.split()[1]

    @cachedproperty
    def sync(self):
        super(Homebrew, self).sync
        self.run([self.cli_path] + self.cli_args + ['update'])

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
            [self.cli_path] + self.cli_args + ['list', '--versions'])

        if output:
            regexp = re.compile(r'(\S+)( \(!\))? (.+)')
            for pkg_info in output.split('\n'):
                match = regexp.match(pkg_info)
                if match:
                    package_id, removed, versions = match.groups()

                    # Guess latest installed version.
                    versions = set(versions.split())
                    # Discard generic 'latest' symbolic version if others are
                    # available.
                    if len(versions) > 1:
                        versions.discard('latest')
                    # Parse versions to avoid lexicographic sorting gotchas.
                    version = None
                    if versions:
                        _, version = max(
                            [(parse_version(v), v) for v in versions])

                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': version}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``brew search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew search sed
            gnu-sed ✔                    libxdg-basedir               minised
            Caskroom/cask/focused                  Caskroom/cask/marsedit
            Caskroom/cask/licensed                 Caskroom/cask/physicseditor
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            for package_id in re.compile(r'[\s✔]+').split(output):
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
            [self.cli_path] + self.cli_args + ['outdated', '--json=v1'])

        if output:
            for pkg_info in json.loads(output):

                # Parse versions to avoid lexicographic sorting gotchas.
                version = None
                versions = set(pkg_info['installed_versions'])
                if versions:
                    _, version = max([(parse_version(v), v) for v in versions])

                package_id = pkg_info['name']
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': version,
                    'latest_version': pkg_info['current_version']}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['upgrade', '--cleanup']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()


class HomebrewCask(Homebrew):

    """ Cask is now part of Homebrew's core and extend it.
    """

    cli_args = ['cask']

    # 'cask install' doesn't upgrade to the latest package version, we need to
    # call 'cask reinstall' instead since 1.1.0.
    # 1.1.6 is the lowest requirement as it is the version from which `brew
    # cask update` command gets properly deprecated.
    requirement = '>= 1.1.6'

    id = "cask"

    name = "Homebrew Cask"

    cli_name = "brew"

    # Call homebrew's own update: `brew cask update` is now deprecated. See:
    # https://github.com/kdeldycke/meta-package-manager/issues/28
    sync = Homebrew().sync

    def search(self, query):
        """ Fetch matching packages from ``brew cask search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew cask search tableau
            ==> Exact match
            tableau
            ==> Partial matches
            tableau-public           tableau-reader
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            lines = [
                l for l in output.split('\n') if l and not l.startswith('==>')]
            for package_id in re.compile(r'\s+').split('\n'.join(lines)):
                matches[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'latest_version': None,
                    'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Search for outdated packages among installed one.

        Cask doesn't provides an ``outdated`` subcommand contrary to ``brew``.
        We have no other alternative but to fetch the list of currently
        installed packages and inspect them one by one to search for outdated
        ones.

        Also, `brew cask list` is `not reliable <https://github.com/caskroom
        /homebrew-cask/blob/master/doc/reporting_bugs
        /brew_cask_list_shows_wrong_information.md>`_.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ brew cask info aerial
            aerial: 1.2beta5
            https://github.com/JohnCoates/Aerial
            /usr/local/Caskroom/aerial/1.2beta5 (18 files, 6.6M)
            From: https://github.com/(...)/blob/master/Casks/aerial.rb
            ==> Name
            Aerial Screensaver
            ==> Artifacts
            Aerial.saver (screen_saver)

        .. code-block:: shell-session

            $ brew cask info firefox
            firefox: 50.0.1
            https://www.mozilla.org/firefox/
            /usr/local/Caskroom/firefox/49.0.1 (107 files, 185.3M)
            From: https://github.com/(...)/blob/master/Casks/firefox.rb
            ==> Name
            Mozilla Firefox
            ==> Artifacts
            Firefox.app (app)

        .. code-block:: shell-session

            $ brew cask info virtualbox
            virtualbox: 5.1.10-112026
            https://www.virtualbox.org
            /usr/local/Caskroom/virtualbox/5.1.8-111374 (3 files, 88.8M)
            /usr/local/Caskroom/virtualbox/5.1.10-112026 (3 files, 89.3M)
            From: https://github.com/(...)/blob/master/Casks/virtualbox.rb
            ==> Name
            Oracle VirtualBox
            ==> Artifacts
            VirtualBox.pkg (pkg)

        .. code-block:: shell-session

            $ brew cask info prey
            prey: 1.6.3
            https://preyproject.com/
            Not installed
            From: https://github.com/(...)/blob/master/Casks/prey.rb
            ==> Name
            Prey
            ==> Artifacts
            prey-mac-1.6.3-x86.pkg (pkg)
            ==> Caveats
            Prey requires your API key, found in the bottom-left corner of
            the Prey web account Settings page, to complete installation.
            The API key may be set as an environment variable as follows:

              API_KEY="abcdef123456" brew cask install prey

        .. code-block:: shell-session

            $ brew cask info ubersicht
            ubersicht: 1.0.44
            http://tracesof.net/uebersicht/
            Not installed
            From: https://github.com/(...)/blob/master/Casks/ubersicht.rb
            ==> Name
            Übersicht
            ==> Artifacts
            Übersicht.app (app)

        .. code-block:: shell-session

            $ brew cask info xld
            xld: 2016.10.07
            http://tmkk.undo.jp/xld/index_e.html
            /usr/local/Caskroom/xld/2016.10.07 (45 files, 221.6K)
            From: https://github.com/(...)/blob/master/Casks/xld.rb
            ==> Names
            X Lossless Decoder
            XLD
            ==> Artifacts
            XLD.app (app)
        """
        outdated = {}

        for installed_pkg in self.installed.values():
            package_id = installed_pkg['id']
            version = installed_pkg['installed_version']

            # Inspect the package closer to evaluate its state.
            output = self.run([
                self.cli_path] + self.cli_args + ['info', package_id])

            latest_version = output.split('\n')[0].split(' ')[1]

            # Skip already installed packages.
            if version == latest_version:
                continue

            # Casks are allowed to provide several names. See:
            # https://github.com/kdeldycke/meta-package-manager/issues/26 .
            package_names = re.search(
                '==> Names?(.*?)(==>|$)', output, re.DOTALL)
            if package_names:
                # Choose the longuest name as canonical.
                package_name = None
                for name in package_names.groups()[0].strip().split('\n'):
                    if not package_name or len(name) > len(package_name):
                        package_name = name

                outdated[package_id] = {
                    'id': package_id,
                    'name': package_name,
                    'installed_version': version,
                    'latest_version': latest_version}

        return outdated

    def upgrade_cli(self, package_id):
        """ Install a package.

        .. todo::

            Wait for https://github.com/caskroom/homebrew-cask/issues/22647
            so we can force a cleanup in one go, as we do above with vanilla
            Homebrew.
        """
        return [self.cli_path] + self.cli_args + ['reinstall', package_id]

    def upgrade_all_cli(self):
        """ Cask has no way to upgrade all outdated packages.

        See: https://github.com/caskroom/homebrew-cask/issues/4678
        """
        raise NotImplementedError
