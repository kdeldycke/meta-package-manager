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

from ..base import PackageManager


class APM(PackageManager):

    cli_path = '/usr/local/bin/apm'

    @property
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
            self.updates.append({
                'name': package['name'],
                'installed_version': package['version'],
                'latest_version': package['latestVersion']
            })

    def update_cli(self, package_name=None):
        cmd = [self.cli_path] + self.cli_args + ['update', '--no-confirm']
        if package_name:
            cmd.append(package_name)
        return cmd

    def update_all_cli(self):
        return self.update_cli()
