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

from boltons.cacheutils import cachedproperty
from boltons.strutils import strip_ansi
from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version

from . import logger
from .bitbar import run
from .platform import current_os

# Rendering format of CLI in JSON fields.
CLI_FORMATS = frozenset(['plain', 'fragments', 'bitbar'])


class CLIError(Exception):

    """ An error occured when running package manager CLI. """

    def __init__(self, code, output, error):
        """ The exception keeps internally the result of CLI execution. """
        super(CLIError, self).__init__()
        self.code = code
        self.output = output
        self.error = error

    def __str__(self):
        """ Human-readable error. """
        return (
            "Return code: {}\n"
            "Output:\n{}\n"
            "Error:\n{}\n").format(self.code, self.output, self.error)


class PackageManager(object):
    """ Package manager definition. """

    # Fully qualified path to the package manager CLI.
    cli_path = None

    # Systematic options passed to package manager CLI. Might be of use to
    # force silencing or high verbosity for instance.
    cli_args = []

    # List of platforms supported by the manager.
    platforms = frozenset()

    # Version requirement specifier.
    requirement = None

    def __init__(self):
        # Outdated packages intalled on the system.
        self.outdated = {}

    def get_version(self):
        """ Invoke the manager and extract its own reported version. """
        raise NotImplementedError

    @cachedproperty
    def version_string(self):
        """ Raw but cleaned string of the package manager version.

        Returns `None` if the manager had an issue extracting its version.
        """
        if self.executable:
            try:
                return self.get_version().strip()
            except CLIError as expt:
                logger.warning(expt.error)

    @cachedproperty
    def version(self):
        """ Parsed and normalized package manager's own version.

        Returns an instance of ``packaging.Version`` or None.
        """
        if self.version_string:
            return parse_version(self.version_string)

    @cachedproperty
    def id(self):
        """ Return package manager's ID. Defaults based on class name.

        This ID must be unique among all package manager definitions and
        lower-case as they're used as feature flags for the mpm CLI.
        """
        return self.__class__.__name__.lower()

    @cachedproperty
    def name(self):
        """ Return package manager's common name. Defaults based on class name.
        """
        return self.__class__.__name__

    @cachedproperty
    def supported(self):
        """ Is the package manager supported on that platform? """
        return current_os()[0] in self.platforms

    @cachedproperty
    def exists(self):
        """ Is the package manager CLI exist on the system? """
        if not os.path.isfile(self.cli_path):
            logger.debug("{} not found.".format(self.cli_path))
            return False
        return True

    @cachedproperty
    def executable(self):
        """ Is the package manager CLI can be executed by the current user? """
        if not self.exists:
            return False
        if not os.access(self.cli_path, os.X_OK):
            logger.debug("{} not executable.".format(self.cli_path))
            return False
        return True

    @cachedproperty
    def fresh(self):
        """ Does the package manager match the version requirement? """
        # Version is mandatory.
        if not self.version:
            return False
        if self.requirement:
            if self.version not in SpecifierSet(self.requirement):
                logger.debug(
                    "{} {} doesn't fit the '{}' version requirement.".format(
                        self.id, self.version, self.requirement))
                return False
        return True

    @cachedproperty
    def available(self):
        """ Is the package manager available and ready-to-use on the system?

        Returns True only if the main CLI:
            1 - is supported on the current platform,
            2 - exists on the system,
            3 - is executable, and
            4 - match the version requirement.
        """
        return (
            self.supported and self.exists and self.executable and self.fresh)

    def run(self, args, dry_run=False):
        """ Run a shell command, return the output and keep error message.

        Removes ANSI escape codes, and returns ready-to-use strings.
        """
        assert isinstance(args, list)
        logger.debug("Running `{}`...".format(' '.join(args)))

        code = 0
        output = None
        error = None

        if not dry_run:
            code, output, error = run(*args)
        else:
            logger.warning("Dry-run mode active: skip execution of command.")

        # Normalize messages.
        if error:
            error = strip_ansi(error)
            error = error if error else None
        if output:
            output = strip_ansi(output)
            output = output if output else None

        if code and error:
            raise CLIError(code, output, error)

        return output

    def sync(self):
        """ Fetch latest versions of installed packages.

        Returns a list of dict with package name, current installed version and
        latest upgradeable version.
        """
        logger.info('Sync {} package info...'.format(self.id))

    def upgrade_cli(self, package_id=None):
        """ Return a bash-compatible full-CLI to upgrade a package. """
        raise NotImplementedError

    def upgrade(self, package_id=None, dry_run=False):
        """ Perform the upgrade of the provided package to latest version. """
        return self.run(self.upgrade_cli(package_id), dry_run=dry_run)

    def upgrade_all_cli(self):
        """ Return a bash-compatible full-CLI to upgrade all packages. """
        raise NotImplementedError

    def upgrade_all(self, dry_run=False):
        """ Perform a full upgrade of all outdated packages to latest versions.

        If the manager doesn't implements a full upgrade one-liner, then
        fall-back to calling single-package upgrade one by one.
        """
        try:
            return self.run(self.upgrade_all_cli(), dry_run=dry_run)
        except NotImplementedError:
            logger.warning(
                "{} doesn't seems to implement a full upgrade subcommand. "
                "Call single-package upgrade CLI one by one.".format(self.id))
            log = []
            self.sync()
            for package_id in self.outdated:
                output = self.upgrade(package_id, dry_run=dry_run)
                if output:
                    log.append(output)
            if log:
                return '\n'.join(log)

    @staticmethod
    def render_cli(cmd, cli_format='plain'):
        """ Return a formatted CLI in the provided format. """
        assert isinstance(cmd, list)
        assert cli_format in CLI_FORMATS
        if cli_format != 'fragments':
            cmd = ' '.join(cmd)
            if cli_format == 'bitbar':
                cmd = PackageManager.render_bitbar_cli(cmd)
        return cmd

    @staticmethod
    def render_bitbar_cli(full_cli):
        """ Format a bash-runnable full-CLI with parameters into bitbar schema.
        """
        cmd, params = full_cli.strip().split(' ', 1)
        bitbar_cli = "bash={}".format(cmd)
        for index, param in enumerate(params.split(' ')):
            bitbar_cli += " param{}={}".format(index + 1, param)
        return bitbar_cli
