# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2017 Kevin Deldycke <kevin@deldycke.com>
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

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import simplejson as json
import re

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX, MACOS


class Pip(PackageManager):

    platforms = frozenset([MACOS, LINUX])

    requirement = '>= 9.0.0'

    # Deny this manager to be tied to a CLI, as we only use this class as a
    # common skeleton for pip2 and pip3.
    cli_name = None

    def get_version(self):
        """ Fetch version from ``pip --version`` output."""
        output = self.run([self.cli_path, '--version'])
        if output:
            return output.split()[1]

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``pip list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ pip list --format=json | jq
            [
             {
                "version": "1.3",
                "name": "backports.functools-lru-cache"
              },
              {
                "version": "0.9999999",
                "name": "html5lib"
              },
              {
                "version": "2.8",
                "name": "Jinja2"
              },
              (...)
            ]
        """
        installed = {}

        output = self.run(
            [self.cli_path] + self.cli_args + ['list', '--format=json'])

        if output:
            for package in json.loads(output):
                package_id = package['name']
                installed[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': package['version']}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``pip search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ pip search abc
            ABC (0.0.0)                 - UNKNOWN
            micropython-abc (0.0.1)     - Dummy abc module for MicroPython
            abc1 (1.2.0)                - a list about my think
            abcd (0.3.0)                - AeroGear Build Cli for Digger
            abcyui (1.0.0)              - Sorry ,This is practice!
            astroabc (1.4.2)            - A Python implementation of an
                                          Approximate Bayesian Computation
                                          Sequential Monte Carlo (ABC SMC)
                                          sampler for parameter estimation.
            collective.js.abcjs (1.10)  - UNKNOWN
            cosmoabc (1.0.5)            - Python ABC sampler
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            regexp = re.compile(r'(\S+) \((.*?)\).*')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, version = match.groups()
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': version,
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``pip list --outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ pip list --format=json --outdated | jq
            [
              {
                "latest_filetype": "wheel",
                "version": "0.7.9",
                "name": "alabaster",
                "latest_version": "0.7.10"
              },
              {
                "latest_filetype": "wheel",
                "version": "0.9999999",
                "name": "html5lib",
                "latest_version": "0.999999999"
              },
              {
                "latest_filetype": "wheel",
                "version": "2.8",
                "name": "Jinja2",
                "latest_version": "2.9.5"
              },
              {
                "latest_filetype": "wheel",
                "version": "0.5.3",
                "name": "mccabe",
                "latest_version": "0.6.1"
              },
              {
                "latest_filetype": "wheel",
                "version": "2.2.0",
                "name": "pycodestyle",
                "latest_version": "2.3.1"
              },
              {
                "latest_filetype": "wheel",
                "version": "2.1.3",
                "name": "Pygments",
                "latest_version": "2.2.0"
              }
            ]
        """
        outdated = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'list', '--format=json', '--outdated'])

        if output:
            for package in json.loads(output):
                package_id = package['name']
                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id,
                    'installed_version': package['version'],
                    'latest_version': package['latest_version']}

        return outdated

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

    name = "Python 2's Pip"
    cli_name = 'pip2'


class Pip3(Pip):

    name = "Python 3's Pip"
    cli_name = 'pip3'
