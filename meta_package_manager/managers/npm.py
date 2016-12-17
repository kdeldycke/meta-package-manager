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


class NPM(PackageManager):

    cli_path = '/usr/local/bin/npm'

    platforms = frozenset([MACOS])

    def get_version(self):
        return self.run([self.cli_path, '--version'])

    @cachedproperty
    def name(self):
        return "Node's npm"

    def sync(self):
        """
        Sample of npm output:

            $ npm -g --progress=false --json outdated
            {
              "my-linked-package": {
                "current": "0.0.0-development",
                "wanted": "linked",
                "latest": "linked",
                "location": "/Users/..."
              },
              "npm": {
                "current": "3.10.3",
                "wanted": "3.10.5",
                "latest": "3.10.5",
                "location": "/Users/..."
              }
            }
        """
        super(NPM, self).sync()

        output = self.run([
            self.cli_path] + self.cli_args + [
                '-g', '--progress=false', '--json', 'outdated'])

        if not output:
            return

        for package_id, values in json.loads(output).items():
            if values['wanted'] == 'linked':
                continue
            self.outdated[package_id] = {
                'id': package_id,
                'name': package_id,
                'installed_version':
                    values['current'] if 'current' in values else None,
                'latest_version': values['latest']}

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + [
            '-g', '--progress=false', 'update']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
