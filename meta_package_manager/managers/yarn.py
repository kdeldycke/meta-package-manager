# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2018 Kevin Deldycke <kevin@deldycke.com>
#                         and contributors.
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

import simplejson as json
from boltons.cacheutils import cachedproperty

from ..base import PackageManager

from ..platform import LINUX, MACOS, WINDOWS


class YARN(PackageManager):
    name = "Node's yarn"

    cli_args = [
        '--no-progress',
        '--non-interactive',
        '--skip-integrity-check'
    ]

    platforms = frozenset([LINUX, MACOS, WINDOWS])

    requirement = '>= 1.0.*'

    def get_version(self):
        """ Fetch version from ``yarn --version`` output."""
        return self.run([self.cli_path, '--version'])

    def parse(self, output):
        packages = {}

        if not output:
            return packages

        outdatedList = output.split('\n')
        for line in outdatedList:
            if not line:
                continue
            obj = json.loads(line)
            if obj['type'] != 'info':
                continue
            package = self.parse_info(obj)
            packages[package['id']] = package
        return packages

    def parse_info(self, obj):
        data = obj['data'].replace('has binaries:', '')
        parts = data.replace('"', '').split('@')
        package_id = parts[0]
        version = parts[1]
        return {
            'id': package_id,
            'name': package_id,
            'installed_version': version
        }

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``yarn list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

           $ yarn --json --no-progress --non-interactive --skip-integrity-check global list'  # noqa

            (...)
        """

        cmd = [self.cli_path, 'global', '--json'] + self.cli_args + [
            'list', '--depth', '0']
        output = self.run(cmd)

        return self.parse(output)

    def search(self, query):
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'info', query, '--json'])

        if output:
            for obj in json.loads('[{}]'.format(output)):
                if obj['type'] != 'inspect':
                    continue
                package = obj['data']
                package_id = package['name']
                matches[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'latest_version': package['version'],
                    'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def global_dir(self):
        cmd = [self.cli_path, 'global', 'dir']
        output = self.run(cmd)
        return output.rstrip("\n\r")

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``yarn outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

           $ yarn --json --no-progress --non-interactive --skip-integrity-check global list'  # noqa

            (...)
        """

        outdated = {}
        cmd = [self.cli_path, '--json'] + self.cli_args + [
            'outdated', '--cwd', self.global_dir]
        output = self.run(cmd)

        if not output:
            return outdated

        packages = list()
        for line in output.split('\n'):
            if not line:
                continue
            obj = json.loads(line)
            if obj['type'] == 'table':
                packages = obj['data']['body']
                break

        for package in packages:
            package_id = package[0]
            values = {
                'current': package[1],
                'wanted': package[2],
                'latest': package[3]
            }

            if values['wanted'] == 'linked':
                continue
            outdated[package_id] = {
                'id': package_id + '@' + values['latest'],
                'name': package_id,
                'installed_version':
                    values['current'] if 'current' in values else None,
                'latest_version': values['latest']}
        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path, 'global'] + self.cli_args + ['--silent']

        if package_id:
            cmd.append('add')
            cmd.append(package_id)
        else:
            cmd.append('upgrade')

        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
