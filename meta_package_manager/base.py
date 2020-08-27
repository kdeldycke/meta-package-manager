# -*- coding: utf-8 -*-
#
# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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
from pathlib import Path
from shutil import which
from textwrap import indent

import click
from boltons.cacheutils import cachedproperty
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from boltons.typeutils import classproperty

from . import logger
from .bitbar import run
from .platform import CURRENT_OS_ID
from .version import parse_version

# Rendering format of CLI in JSON fields.
CLI_FORMATS = frozenset(["plain", "fragments", "bitbar"])


class CLIError(Exception):

    """ An error occurred when running package manager CLI. """

    def __init__(self, code, output, error):
        """ The exception internally keeps the result of CLI execution. """
        super(CLIError, self).__init__()
        self.code = code
        self.output = output
        self.error = error

    def __str__(self):
        """ Human-readable error. """
        margin = " " * 2
        return indent(
            ("\nReturn code: {}\n" "Output:\n{}\n" "Error:\n{}").format(
                self.code,
                indent(str(self.output), margin),
                indent(str(self.error), margin),
            ),
            margin,
        )


class PackageManager:

    """Base class from which all package manager definitions must inherits."""

    # List of platforms supported by the manager.
    platforms = frozenset()

    # Version requirement specifier.
    requirement = None

    # List of additional path to help mpm hunt down the package manager CLI.
    # Should be a list of strings whose order dictatate the search sequence.
    # Most of the time unnecessay: the `cli_path()` method works well on all
    # platforms.
    cli_search_path = []

    # Global list of options used for each call to the package manager CLI.
    # Might be of use to force silencing or high verbosity.
    global_args = []

    # Tell the manager either to raise or continue on errors.
    raise_on_cli_error = False

    # Some managers have the ability to report or ignore packages
    # possessing their own auto-update mecanism.
    ignore_auto_updates = True

    def __init__(self):
        # Log of all encountered CLI errors.
        self.cli_errors = []

    @classproperty
    def id(cls):
        """Return package manager's ID. Defaults based on class name.

        This ID must be unique among all package manager definitions and
        lower-case as they're used as feature flags for the :command:`mpm` CLI.
        """
        return cls.__name__.lower()

    @classproperty
    def name(cls):
        """Return package manager's common name. Defaults based on class name."""
        return cls.__name__

    @classproperty
    def cli_name(cls):
        """Package manager's CLI name.

        Is derived by default from the manager's ID.
        """
        return cls.id

    @classproperty
    def virtual(cls):
        """Should we expose the package manager to the user?

        Virtual package manager are just skeleton classes used to factorize
        code among managers of the same family.
        """
        return cls.__name__ == "PackageManager" or not cls.cli_name

    @cachedproperty
    def cli_path(self):
        """Fully qualified path to the package manager CLI.

        Automaticaly search the location of the CLI in the system.

        Returns `None` if CLI is not found or is not a file.
        """
        if not self.cli_name:
            return None
        env_path = ":".join(
            self.cli_search_path + ["/usr/local/bin", os.environ.get("PATH")]
        )
        cli_path = which(self.cli_name, mode=os.F_OK, path=env_path)
        if not cli_path:
            return None
        cli_path = which(cli_path, mode=os.F_OK, path=env_path)

        if cli_path:
            cli_path = Path(cli_path).resolve(strict=True)
            logger.debug(f"CLI found at {cli_path}")
        else:
            logger.debug(f"{self.cli_name} CLI not found.")

        return cli_path

    def get_version(self):
        """Invoke the manager and extract its own reported version.

        It does matter if this method return unsanitized and crappy string. The
        `version()` method below will clean and normalized it.
        """
        raise NotImplementedError

    @cachedproperty
    def version(self):
        """Parsed and normalized package manager's own version.

        Returns an instance of `TokenizedString`.
        """
        if self.executable:
            return self.get_version()

    @cachedproperty
    def supported(self):
        """ Is the package manager supported on that platform? """
        return CURRENT_OS_ID in self.platforms

    @cachedproperty
    def executable(self):
        """ Is the package manager CLI can be executed by the current user? """
        if not self.cli_path:
            return False
        if not os.access(self.cli_path, os.X_OK):
            logger.debug(f"{self.cli_path} not executable.")
            return False
        return True

    @cachedproperty
    def fresh(self):
        """ Does the package manager match the version requirement? """
        # Version is mandatory.
        if not self.version:
            return False
        if self.requirement:
            if self.version < parse_version(self.requirement):
                logger.debug(
                    f"{self.id} {self.version} is older than "
                    "{self.requirement} version requirement."
                )
                return False
        return True

    @cachedproperty
    def available(self):
        """Is the package manager available and ready-to-use on the system?

        Returns True only if the main CLI:
            1 - is supported on the current platform,
            2 - was found on the system,
            3 - is executable, and
            4 - match the version requirement.
        """
        return bool(self.supported and self.cli_path and self.executable and self.fresh)

    def run(self, *args, dry_run=False):
        """Run a shell command, return the output and keep error message.

        Removes ANSI escape codes, and returns ready-to-use strings.
        """
        # Serialize Path objects to strings.
        args = list(map(str, flatten(args)))
        args_str = click.style(" ".join(args), fg="white")
        logger.debug(f"► {args_str}")

        code = 0
        output = None
        error = None

        if not dry_run:
            code, output, error = run(*args)
        else:
            logger.warning("Dry-run: skip execution of command.")

        # Normalize messages.
        if error:
            error = strip_ansi(error)
            error = error if error else None
        if output:
            output = strip_ansi(output)
            output = output if output else None

        # Non-successful run.
        if code and error:
            # Produce an exception and eventually raise it.
            exception = CLIError(code, output, error)
            if self.raise_on_cli_error:
                raise exception
            # Accumulate errors.
            self.cli_errors.append(exception)

        # Log <stdout> and <stderr> output.
        if output:
            logger.debug(indent(output, "  "))
        if error:
            # Non-fatal error messages are logged as warnings.
            log_func = logger.error if code else logger.warning
            log_func(indent(error, "  "))

        return output

    def run_cli(self, *args, dry_run=False):
        """Like the `run` method above, but execute the binary pointed to by
        the `cli_path` property set in the current instance.
        """
        return self.run(self.cli_path, args, dry_run=dry_run)

    def sync(self):
        """ Refresh local manager metadata from remote repository. """
        if self.sync.__func__.__qualname__ == PackageManager.sync.__qualname__:
            logger.warning(f"Sync not implemented for {self.id}.")
            return
        logger.info(f"Sync {self.id} package info...")

    def cleanup(self):
        """ Remove left-overs and unused packages. """
        if self.cleanup.__func__.__qualname__ == PackageManager.cleanup.__qualname__:
            logger.warning(f"Cleanup not implemented for {self.id}.")
            return
        logger.info(f"Cleanup {self.id}...")

    @property
    def installed(self):
        """List packages currently installed on the system.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name and version.
        """
        raise NotImplementedError

    def search(self, query, extended, exact):
        """Search packages whose ID contain exact or partial query.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name, version and a boolean indicating if the match is
        exact or partial.
        """
        raise NotImplementedError

    @property
    def outdated(self):
        """List currently installed packages having a new version available.

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
        """Perform a full upgrade of all outdated packages to latest versions.

        If the manager doesn't implements a full upgrade one-liner, then
        fall-back to calling single-package upgrade one by one.
        """
        try:
            return self.run(self.upgrade_all_cli(), dry_run=dry_run)
        except NotImplementedError:
            logger.warning(
                f"Full upgrade subcommand not implemented in {self.id}. Call "
                "single-package upgrade CLI one by one."
            )
            log = []
            for package_id in self.outdated:
                output = self.upgrade(package_id, dry_run=dry_run)
                if output:
                    log.append(output)
            if log:
                return "\n".join(log)

    @staticmethod
    def render_cli(cmd, cli_format="plain"):
        """Return a formatted CLI in the requested format.

        * ``plain`` returns a simple string
        * ``fragments`` returns a list of strings
        * ``bitbar`` returns a CLI with parameters formatted into the bitbar
        dialect.
        """
        assert isinstance(cmd, list)
        assert cli_format in CLI_FORMATS
        cmd = map(str, flatten(cmd))  # Serialize Path instances.

        if cli_format == "fragments":
            return list(cmd)

        if cli_format == "plain":
            return " ".join(cmd)

        # Renders the CLI into BitBar dialect.
        bitbar_cli = ""
        for index, param in enumerate(cmd):
            if index == 0:
                bitbar_cli += "bash={}".format(param)
            else:
                if "=" in param:
                    param = '\\"{}\\"'.format(param)
                bitbar_cli += " param{}={}".format(index, param)
        return bitbar_cli
