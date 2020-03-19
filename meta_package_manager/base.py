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
from shutil import which

from boltons.cacheutils import cachedproperty
from boltons.strutils import indent, strip_ansi
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
        """ The exception internally keeps the result of CLI execution. """
        super(CLIError, self).__init__()
        self.code = code
        self.output = output
        self.error = error

    def __str__(self):
        """ Human-readable error. """
        margin = ' ' * 2
        return indent((
            "\nReturn code: {}\n"
            "Output:\n{}\n"
            "Error:\n{}").format(
                self.code,
                indent(str(self.output), margin),
                indent(str(self.error), margin)), margin)


class PackageManager(object):

    """ Base class from which all package manager definitions should inherits.
    """

    # Systematic options passed to package manager CLI. Might be of use to
    # force silencing or high verbosity for instance.
    cli_args = []

    # List of platforms supported by the manager.
    platforms = frozenset()

    # Version requirement specifier.
    requirement = None

    # Tell the manager either to raise or continue on errors.
    raise_on_cli_error = False

    # Some managers have the ability to report or ignore packages
    # possessing their own auto-update mecanism.
    ignore_auto_updates = True

    # Log of all encountered CLI errors.
    cli_errors = []

    @cachedproperty
    def cli_name(self):
        """ Package manager's CLI name.

        Is derived by default from the manager's ID.
        """
        return self.id

    @cachedproperty
    def cli_path(self):
        """ Fully qualified path to the package manager CLI.

        Automaticaly search the location of the CLI in the system.

        Returns `None` if CLI is not found or is not a file.
        """

        if not self.cli_name:
            return None
        env_path = "/usr/local/bin:{}".format(os.environ.get("PATH"))
        cli_path = which(self.cli_name, mode=os.F_OK, path=env_path)
        if not cli_path:
            return None
        cli_path = which(cli_path, mode=os.F_OK, path=env_path)

        logger.debug(
            "CLI found at {}".format(cli_path) if cli_path
            else "{} CLI not found.".format(self.cli_name))
        return cli_path

    def get_version(self):
        """ Invoke the manager and extract its own reported version. """
        raise NotImplementedError

    @cachedproperty
    def version_string(self):
        """ Raw but cleaned string of the package manager version.

        Returns `None` if the manager had an issue extracting its version.
        """
        if self.executable:
            version = self.get_version()
            if version:
                return version.strip()

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
        lower-case as they're used as feature flags for the :command:`mpm` CLI.
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
    def executable(self):
        """ Is the package manager CLI can be executed by the current user? """
        if not self.cli_path:
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
            2 - was found on the system,
            3 - is executable, and
            4 - match the version requirement.
        """
        return bool(
            self.supported and
            self.cli_path and
            self.executable and
            self.fresh)

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
            exception = CLIError(code, output, error)
            if self.raise_on_cli_error:
                raise exception
            else:
                logger.error(error)
                self.cli_errors.append(exception)

        logger.debug(output)

        return output

    @property
    def sync(self):
        """ Refresh local manager metadata from remote repository. """
        logger.info('Sync {} package info...'.format(self.id))

    @property
    def installed(self):
        """ List packages currently installed on the system.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name and version.
        """
        raise NotImplementedError

    @staticmethod
    def exact_match(query, result):
        """ Compare search query and matching result.

        Returns `True` if the matching result exactly match the search query.

        Still pplies a light normalization and tokenization of strings before
        comparison to make the "exactiness" in the human sense instead of
        strictly machine sense.
        """
        # TODO: tokenize.
        return query.lower() == result.lower()

    def search(self, query):
        """ Search packages whose ID contain exact or partial query.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name, version and a boolean indicating if the match is
        exact or partial.
        """
        raise NotImplementedError

    @property
    def outdated(self):
        """ List currently installed packages having a new version available.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name, current installed version and latest upgradeable
        version.
        """
        raise NotImplementedError

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
