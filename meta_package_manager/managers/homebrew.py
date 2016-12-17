# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Kevin Deldycke <kevin@deldycke.com>
#                    and contributors.
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
from packaging.version import parse as parse_version

from ..base import PackageManager
from ..platform import MACOS


class Homebrew(PackageManager):

    cli_path = '/usr/local/bin/brew'

    platforms = frozenset([MACOS])

    requirement = '>= 1.0.*'

    @cachedproperty
    def id(self):
        return "brew"

    def get_version(self):
        return self.run(
            [self.cli_path] + self.cli_args + ['--version']).split()[1]

    def sync(self):
        """ Fetch latest Homebrew formulas.

        Sample of brew output:

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
        super(Homebrew, self).sync()

        self.run([self.cli_path] + self.cli_args + ['update'])

        # List available updates.
        output = self.run(
            [self.cli_path] + self.cli_args + ['outdated', '--json=v1'])
        if not output:
            return

        for pkg_info in json.loads(output):

            # Parse versions to avoid lexicographic sorting gotchas.
            version = None
            versions = set(pkg_info['installed_versions'])
            if versions:
                _, version = max([(parse_version(v), v) for v in versions])

            package_id = pkg_info['name']
            self.outdated[package_id] = {
                'id': package_id,
                'name': package_id,
                'installed_version': version,
                'latest_version': pkg_info['current_version']}

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['upgrade', '--cleanup']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()


class HomebrewCask(Homebrew):

    """ Cask is now part of Homebrew's core and extend it. """

    cli_args = ['cask']

    # 'cask install' doesn't upgrade to the latest package version, we need to
    # call 'cask reinstall' instead since 1.1.0.
    requirement = '>= 1.1.*'

    @cachedproperty
    def id(self):
        return "cask"

    @cachedproperty
    def name(self):
        return "Homebrew Cask"

    def sync(self):
        """ Fetch latest formulas and their metadata.

        Sample of brew cask output:

            $ brew cask list --versions
            aerial 1.2beta5
            android-file-transfer latest
            audacity 2.1.2-1453294898 2.1.2
            bitbar 1.9.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16
            tunnelblick 3.6.8_build_4625 3.6.9_build_4685
            virtualbox 5.1.8-111374 5.1.10-112026

            $ brew cask info aerial
            aerial: 1.2beta5
            https://github.com/JohnCoates/Aerial
            /usr/local/Caskroom/aerial/1.2beta5 (18 files, 6.6M)
            From: https://github.com/(...)/blob/master/Casks/aerial.rb
            ==> Name
            Aerial Screensaver
            ==> Artifacts
            Aerial.saver (screen_saver)

            $ brew cask info firefox
            firefox: 50.0.1
            https://www.mozilla.org/firefox/
            /usr/local/Caskroom/firefox/49.0.1 (107 files, 185.3M)
            From: https://github.com/(...)/blob/master/Casks/firefox.rb
            ==> Name
            Mozilla Firefox
            ==> Artifacts
            Firefox.app (app)

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

            $ brew cask info ubersicht
            ubersicht: 1.0.44
            http://tracesof.net/uebersicht/
            Not installed
            From: https://github.com/(...)/blob/master/Casks/ubersicht.rb
            ==> Name
            Übersicht
            ==> Artifacts
            Übersicht.app (app)
        """
        super(Homebrew, self).sync()

        # `brew cask update` is just an alias to `brew update`.
        self.run([self.cli_path] + self.cli_args + ['update'])

        # List installed packages.
        output = self.run(
            [self.cli_path] + self.cli_args + ['list', '--versions'])

        # Inspect package one by one as `brew cask list` is not reliable. See:
        # https://github.com/caskroom/homebrew-cask/blob/master/doc
        # /reporting_bugs/brew_cask_list_shows_wrong_information.md
        for installed_pkg in output.split('\n'):
            if not installed_pkg:
                continue
            infos = installed_pkg.split()
            package_id = infos[0]

            # Guess latest installed version.
            versions = set(infos[1:])
            # Discard generic 'latest' symbolic version if others are
            # available.
            if len(versions) > 1:
                versions.discard('latest')
            # Parse versions to avoid lexicographic sorting gotchas.
            version = None
            if versions:
                _, version = max([(parse_version(v), v) for v in versions])

            # TODO: Support packages removed from repository (reported with a
            # `(!)` flag). See: https://github.com/caskroom/homebrew-cask/blob
            # /master/doc/reporting_bugs
            # /uninstall_wrongly_reports_cask_as_not_installed.md

            # Inspect the package closer to evaluate its state.
            output = self.run([
                self.cli_path] + self.cli_args + ['info', package_id])

            latest_version = output.split('\n')[0].split(' ')[1]
            package_name = output.split('==> Name\n')[1].split('\n')[0]

            # Skip already installed packages.
            if version == latest_version:
                continue

            self.outdated[package_id] = {
                'id': package_id,
                'name': package_name,
                'installed_version': version,
                'latest_version': latest_version}

    def upgrade_cli(self, package_id):
        """ Install a package.

        TODO: wait for https://github.com/caskroom/homebrew-cask/issues/22647
        so we can force a cleanup in one go, as we do above with vanilla
        Homebrew.
        """
        return [self.cli_path] + self.cli_args + ['reinstall', package_id]

    def upgrade_all_cli(self):
        """ Cask has no way to upgrade all outdated packages.

        See: https://github.com/caskroom/homebrew-cask/issues/4678
        """
        raise NotImplementedError
