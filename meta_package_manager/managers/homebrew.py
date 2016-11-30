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
from subprocess import PIPE, Popen

from boltons.cacheutils import cachedproperty
from packaging.version import parse as parse_version

from ..base import PackageManager


class Homebrew(PackageManager):

    cli_path = '/usr/local/bin/brew'

    @cachedproperty
    def id(self):
        return "brew"

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
            self.updates.append({
                'name': pkg_info['name'],
                # Only keeps the highest installed version.
                'installed_version': max(pkg_info['installed_versions']),
                'latest_version': pkg_info['current_version']})

    def update_cli(self, package_name=None):
        cmd = [self.cli_path] + self.cli_args + ['upgrade', '--cleanup']
        if package_name:
            cmd.append(package_name)
        return cmd

    def update_all_cli(self):
        return self.update_cli()


class Cask(PackageManager):

    # Cask extends Homebrew.
    cli_path = Homebrew.cli_path

    cli_args = ['cask']

    @cachedproperty
    def name(self):
        return "Homebrew Cask"

    @cachedproperty
    def version(self):
        metadata = self.run([self.cli_path] + self.cli_args + ['--version'])
        return parse_version(metadata.split()[1])

    def sync(self):
        """ Fetch latest formulas and their metadata.

        Sample of brew cask output:

            $ brew cask list --versions
            aerial 1.2beta5
            android-file-transfer latest
            audacity 2.1.2
            bitbar 1.9.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16

            $ brew cask info aerial
            aerial: 1.2beta5
            https://github.com/JohnCoates/Aerial
            /usr/local/Caskroom/aerial/1.2beta5 (18 files, 6.6M)
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/aerial.rb
            ==> Name
            Aerial Screensaver
            ==> Artifacts
            Aerial.saver (screen_saver)

            $ brew cask info firefox
            firefox: 50.0.1
            https://www.mozilla.org/firefox/
            /usr/local/Caskroom/firefox/49.0.1 (107 files, 185.3M)
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/firefox.rb
            ==> Name
            Mozilla Firefox
            ==> Artifacts
            Firefox.app (app)

            $ brew cask info prey
            prey: 1.6.3
            https://preyproject.com/
            Not installed
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/prey.rb
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
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/ubersicht.rb
            ==> Name
            Übersicht
            ==> Artifacts
            Übersicht.app (app)
        """
        super(Cask, self).sync()

        # `brew cask update` is just an alias to `brew update`. Perform the
        # action anyway to make it future proof.
        self.run([self.cli_path] + self.cli_args + ['update'])

        # List installed packages.
        output = self.run(
            [self.cli_path] + self.cli_args + ['list', '--versions'])

        # Inspect package one by one as `brew cask list` is not reliable. See:
        # https://github.com/caskroom/homebrew-cask/blob/master/doc
        # /reporting_bugs/brew_cask_list_shows_wrong_information.md
        for installed_pkg in output.strip().split('\n'):
            if not installed_pkg:
                continue
            infos = installed_pkg.split(' ', 1)
            name = infos[0]

            # Use heuristics to guess installed version.
            versions = infos[1] if len(infos) > 1 else ''
            versions = sorted([
                v.strip() for v in versions.split(',') if v.strip()])
            if len(versions) > 1 and 'latest' in versions:
                versions.remove('latest')
            version = versions[-1] if versions else '?'

            # TODO: Support packages removed from repository (reported with a
            # `(!)` flag). See: https://github.com/caskroom/homebrew-cask/blob
            # /master/doc/reporting_bugs
            # /uninstall_wrongly_reports_cask_as_not_installed.md

            # Inspect the package closer to evaluate its state.
            output = self.run([self.cli_path] + self.cli_args + ['info', name])

            # Consider package as up-to-date if installed.
            if output.find('Not installed') == -1:
                continue

            latest_version = output.split('\n')[0].split(' ')[1]

            self.updates.append({
                'name': name,
                'installed_version': version,
                'latest_version': latest_version})

    def update_cli(self, package_name):
        """ Install a package.

        TODO: wait for https://github.com/caskroom/homebrew-cask/issues/22647
        so we can force a cleanup in one go, as we do above with vanilla
        Homebrew.
        """
        return [self.cli_path] + self.cli_args + ['install', package_name]

    def update_all_cli(self):
        """ Cask has no way to update all outdated packages.

        See: https://github.com/caskroom/homebrew-cask/issues/4678
        """
        raise NotImplementedError
