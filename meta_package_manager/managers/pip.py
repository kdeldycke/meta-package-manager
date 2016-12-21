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

import re

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX, MACOS


class Pip(PackageManager):

    platforms = frozenset([MACOS, LINUX])

    def get_version(self):
        return self.run([self.cli_path, '--version']).split()[1]

    def sync(self):
        """ List outdated packages and their metadata.

        Sample of pip output:

            $ pip list --outdated
            ccm (2.1.8, /Users/kdeldycke/ccm) - Latest: 2.1.11 [sdist]
            coverage (4.0.3) - Latest: 4.1 [wheel]
            IMAPClient (0.13) - Latest: 1.0.1 [wheel]
            Logbook (0.10.1) - Latest: 1.0.0 [sdist]
            mccabe (0.4.0) - Latest: 0.5.0 [wheel]
            mercurial (3.8.3) - Latest: 3.8.4 [sdist]
            pylint (1.5.6) - Latest: 1.6.1 [wheel]
        """
        super(Pip, self).sync()

        output = self.run([
            self.cli_path] + self.cli_args + ['list', '--outdated'])

        if not output:
            return

        regexp = re.compile(r'(\S+) \((.*)\) - Latest: (\S+)')
        for outdated_pkg in output.split('\n'):
            if not outdated_pkg:
                continue

            matches = regexp.match(outdated_pkg)
            if not matches:
                continue

            package_id, installed_info, latest_version = matches.groups()

            # Extract current non-standard location if found.
            installed_info = installed_info.split(',', 1)
            version = installed_info[0]
            special_location = " ({})".format(
                installed_info[1].strip()) if len(installed_info) > 1 else ''

            self.outdated[package_id] = {
                'id': package_id,
                'name': package_id + special_location,
                'installed_version': version,
                'latest_version': latest_version}

    def upgrade_cli(self, package_id):
        return [
            self.cli_path] + self.cli_args + [
                'install', '--upgrade', package_id]

    def upgrade_all_cli(self):
        """ Pip lacks support of a proper full upgrade command.

        See: https://github.com/pypa/pip/issues/59
        """
        raise NotImplementedError


class Pip2(Pip):

    cli_path = '/usr/local/bin/pip2'

    @cachedproperty
    def name(self):
        return "Python 2's Pip"


class Pip3(Pip):

    cli_path = '/usr/local/bin/pip3'

    @cachedproperty
    def name(self):
        return "Python 3's Pip"
