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

import os
import re

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import MACOS


class Gem(PackageManager):

    HOMEBREW_PATH = '/usr/local/bin/gem'
    SYSTEM_PATH = '/usr/bin/gem'

    platforms = frozenset([MACOS])

    def __init__(self):
        super(Gem, self).__init__()

        # Check if the gem CLI is the original one from the system or was
        # installed via Homebrew.
        self.system_install = True
        if os.path.exists(Gem.HOMEBREW_PATH):
            self.system_install = False

    def get_version(self):
        return self.run([self.cli_path, '--version'])

    @cachedproperty
    def cli_path(self):
        return Gem.SYSTEM_PATH if self.system_install else Gem.HOMEBREW_PATH

    @cachedproperty
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
        super(Gem, self).sync()

        # Outdated does not require sudo privileges on homebrew or system.
        output = self.run([self.cli_path] + self.cli_args + ['outdated'])

        regexp = re.compile(r'(\S+) \((\S+) < (\S+)\)')
        for package in output.split('\n'):
            if not package:
                continue
            package_id, current_version, latest_version = regexp.match(
                package).groups()
            self.outdated[package_id] = {
                'id': package_id,
                'name': package_id,
                'installed_version': current_version,
                'latest_version': latest_version}

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update']
        # Installs require `sudo` on system ruby.
        # I (@tresni) recommend doing something like:
        #     $ sudo dseditgroup -o edit -a -t user wheel
        # And then do `visudo` to make it so the `wheel` group does not require
        # a password. There is a line already there for it, you just need to
        # uncomment it and save.)
        if self.system_install:
            cmd.insert(0, '/usr/bin/sudo')
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
