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

from ..base import PackageManager
from ..platform import MACOS


class APM(PackageManager):

    cli_path = '/usr/local/bin/apm'

    platforms = frozenset([MACOS])

    def get_version(self):
        return self.run([self.cli_path, '--version']).split('\n')[0].split()[1]

    @cachedproperty
    def name(self):
        return "Atom's apm"

    def sync(self):
        super(APM, self).sync()

        outdated_cmd = [self.cli_path] + self.cli_args + [
            'outdated', '--compatible', '--json']
        output = self.run(outdated_cmd)

        if not output:
            return

        for package in json.loads(output):
            package_id = package['name']
            self.outdated[package_id] = {
                'id': package_id,
                'name': package_id,
                'installed_version': package['version'],
                'latest_version': package['latestVersion']}

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update', '--no-confirm']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
