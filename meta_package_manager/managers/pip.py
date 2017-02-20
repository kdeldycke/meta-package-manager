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

import re

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX, MACOS


class Pip(PackageManager):

    platforms = frozenset([MACOS, LINUX])

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

            $ pip list
            configparser (3.5.0)
            docutils (0.13.1)
            html5lib (0.9999999)
            imagesize (0.7.1)
            MarkupSafe (0.23)
            mccabe (0.5.3)
            meta-package-manager (2.4.0, /home/kev/venvs/meta-package-manager)
            nose (1.3.7)
        """
        installed = {}

        output = self.run([self.cli_path] + self.cli_args + ['list'])

        if output:
            regexp = re.compile(r'(\S+) \((.*)\)')
            for outdated_pkg in output.split('\n'):
                if not outdated_pkg:
                    continue

                matches = regexp.match(outdated_pkg)
                if not matches:
                    continue

                package_id, installed_info = matches.groups()

                # Extract current non-standard location if found.
                installed_info = installed_info.split(',', 1)
                version = installed_info[0]
                special_location = " ({})".format(installed_info[1].strip()) \
                    if len(installed_info) > 1 else ''

                installed[package_id] = {
                    'id': package_id,
                    'name': package_id + special_location,
                    'installed_version': version}

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

            $ pip list --outdated
            ccm (2.1.8, /Users/kdeldycke/ccm) - Latest: 2.1.11 [sdist]
            coverage (4.0.3) - Latest: 4.1 [wheel]
            IMAPClient (0.13) - Latest: 1.0.1 [wheel]
            Logbook (0.10.1) - Latest: 1.0.0 [sdist]
            mccabe (0.4.0) - Latest: 0.5.0 [wheel]
            mercurial (3.8.3) - Latest: 3.8.4 [sdist]
            pylint (1.5.6) - Latest: 1.6.1 [wheel]
        """
        outdated = {}

        output = self.run([
            self.cli_path] + self.cli_args + ['list', '--outdated'])

        if output:
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
                special_location = " ({})".format(installed_info[1].strip()) \
                    if len(installed_info) > 1 else ''

                outdated[package_id] = {
                    'id': package_id,
                    'name': package_id + special_location,
                    'installed_version': version,
                    'latest_version': latest_version}

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
