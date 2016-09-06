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


class NPM(PackageManager):

    cli_path = '/usr/local/bin/npm'

    @property
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
        output = self.run(
            self.cli_path, '-g', '--progress=false', '--json', 'outdated')
        if not output:
            return

        for package, values in json.loads(output).iteritems():
            if values['wanted'] == 'linked':
                continue
            self.updates.append({
                'name': package,
                'installed_version':
                    values['current'] if 'current' in values else '',
                'latest_version': values['latest']
            })

    def update_cli(self, package_name=None):
        cmd = "{} -g --progress=false update".format(self.cli_path)
        if package_name:
            cmd += " {}".format(package_name)
        return cmd

    def update_all_cli(self):
        return self.update_cli()
