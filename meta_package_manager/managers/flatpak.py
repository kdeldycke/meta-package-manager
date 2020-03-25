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


class Flatpak(PackageManager):

    platforms = frozenset([LINUX])

    requirement = '>= 1.2.*'

    name = "Flatpak"

    def get_version(self):
        """ Fetch version from ``flatpak --version`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ flatpak --version
            Flatpak 1.4.2
        """
        output = self.run([self.cli_path, '--version'])
        if output:
            return output.strip().split()[1]

    @cachedproperty
    def installed(self):
        """Fetch installed packages from ``flatpak list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ flatpak list --app --columns=name,application,version \
            > --ostree-verbose
            Name                      Application ID                   Version
            Peek                      com.uploadedlobster.peek         1.3.1
            Fragments                 de.haeckerfelix.Fragments        1.4
            GNOME MPV                 io.github.GnomeMpv               0.16
            Syncthing GTK             me.kozec.syncthingtk             v0.9.4.3
            Builder                   org.flatpak.Builder
        """
        installed = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'list', '--app', '--columns=name,application,version',
            '--ostree-verbose'])

        if output:
            regexp = re.compile(
                r'(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    name, package_id, installed_version = match.groups()
                    installed[package_id] = {
                        'id': package_id,
                        'name': name,
                        'installed_version': installed_version}
        return installed

    def search(self, query):
        """ Fetch matching packages from ``flatpak search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ flatpak search gitg --ostree-verbose
            gitg    GUI for git        org.gnome.gitg  3.32.1  stable  flathub
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query, '--ostree-verbose'])

        if output:
            for package in output.splitlines():
                match_attrs = package.split('\t')
                if len(match_attrs) > 1:
                    name, description, package_id, latest_version, branch, \
                            remotes = match_attrs
                    matches[package_id] = {
                        'id': package_id,
                        'name': name,
                        'latest_version': latest_version,
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``flatpak remote-ls`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ flatpak remote-ls --app --updates --ostree-verbose
            GNOME Dictionary    org.gnome.Dictionary    3.26.0  stable  x86_64
        """
        outdated = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'remote-ls', '--app', '--updates',
            '--columns=name,application,version', '--ostree-verbose'])

        if output:
            regexp = re.compile(
                r'(?P<name>.+?)\t(?P<package_id>\S+)\t?(?P<latest_version>.*)')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    name, package_id, latest_version = match.groups()

                    info_installed__output = self.run(
                        [self.cli_path] + self.cli_args +
                        ['info', '--ostree-verbose', package_id])
                    current_version = re.search(
                        r'version:\s(?P<version>\S.*?)\n',
                        info_installed__output, re.IGNORECASE)

                    installed_version = current_version.group(
                        'version') if current_version else 'unknow'

                    outdated[package_id] = {
                        'id': package_id,
                        'name': name,
                        'latest_version': latest_version,
                        'installed_version': installed_version}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update', '--noninteractive']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
