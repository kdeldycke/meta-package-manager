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
from packaging.version import parse as parse_version

from ..base import PackageManager


class MAS(PackageManager):

    cli_path = '/usr/local/bin/mas'

    # 'mas outdated' output has been changed in 1.3.1: https://github.com
    # /mas-cli/mas/commit/ca72ee42b1c5f482513b1d2fbf780b0bf3d9618b
    requirement = '>= 1.3.1'

    def __init__(self):
        super(MAS, self).__init__()
        self.map = {}

    @cachedproperty
    def name(self):
        return "Mac AppStore"

    @cachedproperty
    def version(self):
        return parse_version(self.run([self.cli_path, 'version']))

    def sync(self):
        super(MAS, self).sync()

        output = self.run([self.cli_path] + self.cli_args + ['outdated'])

        if not output:
            return

        regexp = re.compile(r'(\d+) (.*) \((\S+) -> (\S+)\)$')
        for application in output.split('\n'):
            if not application:
                continue
            _id, name, installed_version, latest_version = regexp.match(
                application).groups()
            self.map[name] = _id
            self.updates.append({
                'name': name,
                'latest_version': latest_version,
                # Normalize unknown version. See: https://github.com/mas-cli
                # /mas/commit/1859eaedf49f6a1ebefe8c8d71ec653732674341
                'installed_version': (
                    installed_version if installed_version != 'unknown'
                    else '')})

    def update_cli(self, package_name):
        if package_name not in self.map:
            return None
        return [self.cli_path] + self.cli_args + [
            'install', self.map[package_name]]

    def update_all_cli(self):
        return [self.cli_path] + self.cli_args + ['upgrade']
