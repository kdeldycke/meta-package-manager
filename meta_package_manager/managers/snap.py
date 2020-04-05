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

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX
from ..version import TokenizedString, parse_version


class Snap(PackageManager):

    platforms = frozenset([LINUX])

    requirement = '2.0.0'

    def get_version(self):
        """ Fetch version from ``snap --version`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ snap --version
            snap       2.44.1
            snapd      2.44.1
            series     16
            linuxmint  19.3
            kernel     4.15.0-91-generic
        """
        output = self.run([self.cli_path, '--version'])
        if output:
            return parse_version(output.splitlines()[0].split()[1])

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``snap list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session
            $ snap list
            Name               Version    Rev   Aufzeichnung   Herausgeber     Hinweise
            core               16-2.44.1  8935  latest/stable  canonical✓      core
            electronic-wechat  2.0        7     latest/stable  ubuntu-dawndiy  -
            pdftk              2.02-4     9     latest/stable  smoser          -
        """
        installed = {}

        output = self.run([self.cli_path] + self.global_args + [
            'list'])

        if output:
            for package in output.splitlines():
                package_id = package.split()[0]
                installed_version = package.split()[1]
                installed[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': parse_version(installed_version)}

        return installed

    def search(self, query, extended, exact):
        """ Fetch matching packages from ``snap find`` output.
        
        .. code-block:: shell-session
            $ snap find doc
            Name                       Version                  Herausgeber               Hinweise  Zusammenfassung
            journey                    2.14.3                   2appstudio✓               -         Your private diary, journal & companion.
            telegram-desktop           2.0.1                    telegram.desktop          -         Official desktop client for the Telegram messenger
            nextcloud                  17.0.5snap1              nextcloud✓                -         Nextcloud Server - A safe home for all your data
            kata-containers            1.10.2                   katacontainers✓           classic   Lightweight virtual machines that seamlessly plug into the containers ecosystem
            skype                      8.58.0.93                skype✓                    classic   One Skype for all your devices. New features. New look. All Skype.
        """
        matches = {}

        output = self.run([self.cli_path] + self.global_args + ['find', query])

        if output:

            for package in output.splitlines()[1:]:

                package_id = package.split()[0]
                version = package.split()[1]
                description = ' '.join(map(str, package.split()[4:]))

                # Skip all non-stricly matching package IDs in exact mode.
                if exact:
                    if query != package_id:
                        continue

                else:
                    # Exclude packages not featuring the search query in their ID
                    # or name.
                    if not extended:
                        query_parts = set(map(str, TokenizedString(query)))
                        pkg_parts = set(map(str, TokenizedString(package_id)))
                        if not query_parts.issubset(pkg_parts):
                            continue

                matches[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'latest_version': parse_version(version)}
        return matches

    def upgrade_cli(self, package_id):
        """snap has an auto-update function, but snaps can be updated manually."""
        return [
            self.cli_path] + self.global_args + [
                'refresh', package_id]

    def upgrade_all_cli(self):
        """snap has an auto-update function, but snaps can be updated manually."""
        return [
            self.cli_path] + self.global_args + [
                'refresh']