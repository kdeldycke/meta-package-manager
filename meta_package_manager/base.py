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
from subprocess import PIPE, Popen

from . import logger


class PackageManager(object):
    """ Package manager definition. """

    # Fully qualified path to the package manager CLI.
    cli_path = None

    # Systematic options passed to package manager CLI. Might be of use to
    # force silencing or high verbosity for instance.
    cli_args = []

    def __init__(self):
        # List all available updates and their versions.
        self.updates = []
        self.error = None

    @property
    def id(self):
        """ Return package manager's ID. Defaults based on class name.

        This ID must be unique among all package manager definitions and
        lower-case as they're used as feature flags for the mpm CLI.
        """
        return self.__class__.__name__.lower()

    @property
    def name(self):
        """ Return package manager's common name. Defaults based on class name.
        """
        return self.__class__.__name__

    @property
    def available(self):
        """ Is the package manager available and ready-to-use on the system?

        Returns True is the main CLI exists and is executable.
        """
        if not os.path.isfile(self.cli_path):
            logger.debug("{} not found.".format(self.cli_path))
            return False
        if not os.access(self.cli_path, os.X_OK):
            logger.debug("{} not executable.".format(self.cli_path))
            return False
        return True

    def run(self, cmd):
        """ Run a shell command, return the output and keep error message. """
        self.error = None
        assert isinstance(cmd, list)
        logger.debug("Running `{}`...".format(' '.join(cmd)))
        process = Popen(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        output, error = process.communicate()
        if process.returncode != 0 and error:
            self.error = error.decode('utf-8')
        return output.decode('utf-8')

    def sync(self):
        """ Fetch latest versions of installed packages.

        Returns a list of dict with package name, current installed version and
        latest upgradeable version.
        """
        logger.info('Sync {} package info...'.format(self.id))

    def update_cli(self, package_name=None):
        """ Return a bash-compatible full-CLI to update a package. """
        raise NotImplementedError

    def update(self, package_name=None):
        """ Effectively perform an update of provided package. """
        return self.run(self.update_cli(package_name))

    def update_all_cli(self):
        """ Return a bash-compatible full-CLI to update all packages. """
        raise NotImplementedError

    def update_all(self):
        """ Effectively perform a full update of all outdated packages.

        If the manager doesn't implements a full update one-liner, then
        fall-back to calling single-package update one by one.
        """
        try:
            return self.run(self.update_all_cli())
        except NotImplementedError:
            logger.warning(
                "{} doesn't seems to implement a full update subcommand. Call"
                "single-package update CLI one by one.".format(self.id))
            output = []
            for package in self.updates:
                output.append(self.update(package['name']))
            return '\n'.join(output)

    @staticmethod
    def bitbar_cli_format(full_cli):
        """ Format a bash-runnable full-CLI with parameters into bitbar schema.
        """
        cmd, params = full_cli.strip().split(' ', 1)
        bitbar_cli = "bash={}".format(cmd)
        for index, param in enumerate(params.split(' ')):
            bitbar_cli += " param{}={}".format(index + 1, param)
        return bitbar_cli
