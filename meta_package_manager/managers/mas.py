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
from ..platform import MACOS


class MAS(PackageManager):

    platforms = frozenset([MACOS])

    # 'mas outdated' output has been changed in 1.3.1: https://github.com
    # /mas-cli/mas/commit/ca72ee42b1c5f482513b1d2fbf780b0bf3d9618b
    requirement = '>= 1.3.1'

    name = "Mac AppStore"

    def get_version(self):
        """ Fetch version from ``mas version`` output."""
        return self.run([self.cli_path, 'version'])

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``mas list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ mas list
            408981434 iMovie (10.1.4)
            747648890 Telegram (2.30)
        """
        installed = {}

        output = self.run([self.cli_path] + self.cli_args + ['list'])

        if output:
            regexp = re.compile(r'(\d+) (.*) \((\S+)\)$')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, package_name, installed_version = \
                        match.groups()
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_name,
                        # Normalize unknown version. See:
                        # https://github.com/mas-cli/mas/commit
                        # /1859eaedf49f6a1ebefe8c8d71ec653732674341
                        'installed_version': (
                            installed_version if installed_version != 'unknown'
                            else None)}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``mas search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ mas search python
            689176796 Python Runner
            630736088 Learning Python
            945397020 Run Python
            891162632 Python Lint
            1025391371 Tutorial for Python
            1164498373 PythonGames
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            regexp = re.compile(r'(\d+) (.*)$')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, package_name = match.groups()
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_name,
                        'latest_version': None,
                        'exact': self.exact_match(query, package_name)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``mas outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ mas outdated

        .. todo

            An example of ``mas outdated`` output is missing above.
        """
        outdated = {}

        output = self.run([self.cli_path] + self.cli_args + ['outdated'])

        if output:
            regexp = re.compile(r'(\d+) (.*) \((\S+) -> (\S+)\)$')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, package_name, installed_version, \
                        latest_version = match.groups()
                    outdated[package_id] = {
                        'id': package_id,
                        'name': package_name,
                        'latest_version': latest_version,
                        # Normalize unknown version. See:
                        # https://github.com/mas-cli/mas/commit
                        # /1859eaedf49f6a1ebefe8c8d71ec653732674341
                        'installed_version': (
                            installed_version if installed_version != 'unknown'
                            else None)}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['upgrade']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
