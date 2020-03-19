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

import os
import re
from shutil import which

from boltons.cacheutils import cachedproperty
from packaging.version import parse as parse_version

from ..base import PackageManager
from ..platform import LINUX, MACOS, WINDOWS
from . import logger


class Gem(PackageManager):

    platforms = frozenset([LINUX, MACOS, WINDOWS])

    def get_version(self):
        """ Fetch version from ``gem --version`` output."""
        return self.run([self.cli_path, '--version'])

    name = "Ruby Gems"

    @cachedproperty
    def cli_path(self):
        """ Fully qualified path to the package manager CLI.

        Automaticaly search the location of the CLI in the system.

        Returns `None` if CLI is not found or is not a file.
        """

        if not self.cli_name:
            return None
        env_path = ":".join([
            "/usr/local/opt/ruby/bin/gem",
            "/usr/local/opt/ruby/bin",
            "/usr/local/bin",
            os.environ.get("PATH")
        ])
        cli_path = which(self.cli_name, mode=os.F_OK, path=env_path)
        if not cli_path:
            return None
        cli_path = which(cli_path, mode=os.F_OK, path=env_path)

        logger.debug(
            "CLI found at {}".format(cli_path) if cli_path
            else "{} CLI not found.".format(self.cli_name))
        return cli_path

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``gem list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem list

            *** LOCAL GEMS ***

            bigdecimal (1.2.0)
            CFPropertyList (2.2.8)
            io-console (0.4.2)
            json (1.7.7)
            libxml-ruby (2.6.0)
            molinillo (0.5.4, 0.4.5, 0.2.3)
            nokogiri (1.5.6)
            psych (2.0.0)
            rake (0.9.6)
            rdoc (4.0.0)
            sqlite3 (1.3.7)
            test-unit (2.0.0.0)
        """
        installed = {}

        output = self.run([self.cli_path] + self.cli_args + ['list'])

        if output:
            regexp = re.compile(r'(\S+) \((.+)\)')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, versions = match.groups()

                    # Guess latest installed version.
                    versions = set([v.strip() for v in versions.split(',')])
                    # Parse versions to avoid lexicographic sorting gotchas.
                    version = None
                    if versions:
                        _, version = max(
                            [(parse_version(v), v) for v in versions])

                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': version}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``gem search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem search python

            *** REMOTE GEMS ***

            bee_python (0.2.3)
            fluent-plugin-airbrake-python (0.2)
            logstash-filter-python (0.0.1 java)
            pythonconfig (1.0.1)
            rabbit-slide-niku-erlangvm-for-pythonista (2015.09.12)
            RubyToPython (0.0)
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query])

        if output:
            regexp = re.compile(r'(\S+) \((.+)\)')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, version = match.groups()
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': version.split()[0],
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``gem outdated`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ gem outdated
            did_you_mean (1.0.0 < 1.0.2)
            io-console (0.4.5 < 0.4.6)
            json (1.8.3 < 2.0.1)
            minitest (5.8.3 < 5.9.0)
            power_assert (0.2.6 < 0.3.0)
            psych (2.0.17 < 2.1.0)
        """
        outdated = {}

        output = self.run([self.cli_path] + self.cli_args + ['outdated'])

        if output:
            regexp = re.compile(r'(\S+) \((\S+) < (\S+)\)')
            for package in output.split('\n'):
                match = regexp.match(package)
                if match:
                    package_id, current_version, latest_version = \
                        match.groups()
                    outdated[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': current_version,
                        'latest_version': latest_version}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update', '--user-install']
        # Installs require `sudo` on system ruby.
        # I (@tresni) recommend doing something like:
        #     $ sudo dseditgroup -o edit -a -t user wheel
        # And then do `visudo` to make it so the `wheel` group does not require
        # a password. There is a line already there for it, you just need to
        # uncomment it and save.)
        # if self.cli_path == '/usr/bin/gem':
        #     cmd.insert(0, '/usr/bin/sudo')
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()
