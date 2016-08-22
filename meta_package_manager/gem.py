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


from __future__ import print_function, unicode_literals

import os
import re

from .base import PackageManager


class Gems(PackageManager):

    HOMEBREW_PATH = '/usr/local/bin/gem'
    SYSTEM_PATH = '/usr/bin/gem'

    def __init__(self):
        super(Gems, self).__init__()

        self.system = True
        if os.path.exists(Gems.HOMEBREW_PATH):
            self.system = False
            self._cli = Gems.HOMEBREW_PATH
        else:
            self._cli = Gems.SYSTEM_PATH

    @property
    def cli(self):
        return self._cli

    @property
    def name(self):
        return "Ruby Gems"

    def sync(self):
        """
        Sample of gem output:

            $ gem outdated
            did_you_mean (1.0.0 < 1.0.2)
            io-console (0.4.5 < 0.4.6)
            json (1.8.3 < 2.0.1)
            minitest (5.8.3 < 5.9.0)
            power_assert (0.2.6 < 0.3.0)
            psych (2.0.17 < 2.1.0)
        """
        # outdated does not require sudo privileges on homebrew or system
        output = self.run(self.cli, 'outdated')

        regexp = re.compile(r'(\S+) \((\S+) < (\S+)\)')
        for package in output.split('\n'):
            if not package:
                continue
            name, current_version, latest_version = regexp.match(
                package).groups()
            self.updates.append({
                'name': name,
                'installed_version': current_version,
                'latest_version': latest_version
            })

    def update_cli(self, package_name=None):
        # installs require sudo on system ruby
        cmd = "{}{} update".format(
            '/usr/bin/sudo ' if self.system else '',
            self.cli)
        if package_name:
            cmd += " {}".format(package_name)
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        return self.update_cli()
