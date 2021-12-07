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
import re
from pathlib import Path
from shutil import which
from textwrap import dedent, indent, shorten

from boltons.cacheutils import cachedproperty
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from boltons.typeutils import classproperty
from click_extra.colorize import theme
from click_extra.logging import logger
from click_extra.platform import CURRENT_OS_ID
from click_extra.run import INDENT, PROMPT, run

from .version import parse_version

CLI_FORMATS = frozenset({"plain", "fragments", "xbar"})
"""Rendering format of CLI in JSON fields."""


class CLIError(Exception):

    """An error occurred when running package manager CLI."""

    def __init__(self, code, output, error):
        """The exception internally keeps the result of CLI execution."""
        super().__init__()
        self.code = code
        self.output = output
        self.error = error

    def __str__(self):
        """Human-readable error."""
        indented_output = indent(str(self.output), INDENT)
        indented_error = indent(str(self.error), INDENT)
        return indent(
            dedent(
                f"""
            Return code: {self.code}
            Output:
            {indented_output}
            Error:
            {indented_error}"""
            ),
            INDENT,
        )

    def __repr__(self):
        error_excerpt = shorten(
            " ".join(self.error.split()), width=60, placeholder="(...)"
        )
        return f"<{self.__class__.__name__}({self.code}, {error_excerpt!r})>"


class PackageManager:

    """Base class from which all package manager definitions inherits."""

    platforms = frozenset()
    """List of platforms supported by the manager."""

    requirement = None
    """Minimal required version."""

    version_cli_options = ("--version",)
    """List of options to get the version from the package manager CLI."""

    version_regex = r"(?P<version>\S+)"
    """ Regular expression used to extract the version number from the result of the CLI
    run with the options above. It doesn't matter if the regex returns unsanitized
    and crappy string. The ``version()`` method will clean and normalized it.

    By default match the first part that is space-separated.
    """

    cli_search_path = ()
    """ List of additional path to help mpm hunt down the package manager CLI.

    Should be a list of strings whose order dictatate the search sequence.

    Most of the time unnecessay: :py:func:`meta_package_manager.base.PackageManager.cli_path`
    works well on all platforms.
    """

    global_args = ()
    """Global list of options used for each call to the package manager CLI.

    Automaticcaly added to each :py:func:`meta_package_manager.base.PackageManager.run_cli`
    call.

    Usually used to force silencing, low verbosity or no color output.
    """

    prepend_global_args = True
    """Add the global args either at the begginning (``True``) or the end (``False``) of the CLI.
    """

    stop_on_error = False
    """Tell the manager to either raise or continue on errors."""

    ignore_auto_updates = True
    """Some managers can report or ignore packages which have their own auto-update mecanism.
    """

    dry_run = False
    """Do not actually perform any action, just simulate CLI calls."""

    def __init__(self):
        # Log of all encountered CLI errors.
        self.cli_errors = []

    @classproperty
    def id(cls):
        """Return package manager's ID. Defaults based on class name.

        This ID must be unique among all package manager definitions and
        lower-case as they're used as feature flags for the :command:`mpm` CLI.
        """
        return cls.__name__.lower().replace("_", "-")

    @classproperty
    def name(cls):
        """Return package manager's common name. Defaults based on class name."""
        return cls.__name__

    @classproperty
    def cli_names(cls):
        """List of CLI names the package manager is known as.

        The supported CLI names are ordered by priority. This is used for example to
        help out the search of the right binary in the case of the python3/python2
        transition.

        Is derived by default from the manager's ID.
        """
        return (cls.id,)

    @classproperty
    def virtual(cls):
        """Should we expose the package manager to the user?

        Virtual package manager are just skeleton classes used to factorize
        code among managers of the same family.
        """
        return cls.__name__ == "PackageManager" or not cls.cli_names

    @cachedproperty
    def cli_path(self):
        """Fully qualified path to the package manager CLI.

        Automaticaly search the location of the CLI in the system. Try multiple CLI
        names within several system path.

        Only checks if the file exists. Its executability will be assessed later. See
        the ``self.executable`` method below.

        Returns ``None`` if no CLI was found or those found were not a file.
        """
        # Check if the path exist in any of the environment locations.
        env_path = ":".join(flatten((self.cli_search_path, os.getenv("PATH"))))

        # Search for multiple CLI names.
        for name in self.cli_names:
            cli_path = which(name, mode=os.F_OK, path=env_path)
            if cli_path:
                break
            logger.debug(f"{name} CLI not found.")

        if not cli_path:
            return

        # Check if path exist and is a file.
        # Do not resolve symlink here. Some manager like Homebrew on Linux rely on some
        # sort of synlink trickery to set environment variables.
        cli_path = Path(cli_path)
        if not cli_path.exists():
            raise FileNotFoundError(f"{cli_path}")
        elif not cli_path.is_file():
            logger.warning(f"{cli_path} is not a file.")
        else:
            logger.debug(f"{name} CLI found at {cli_path}")

        return cli_path

    @cachedproperty
    def version(self):
        """Invoke the manager and extract its own reported version string.

        Returns a parsed and normalized version in the form of a `TokenizedString`
        instance.
        """
        if self.executable:
            # Invoke the manager.
            output = self.run_cli(
                self.version_cli_options, skip_globals=True, force_exec=True
            )

            # Extract the version with the regex.
            if output:
                version_string = (
                    re.compile(self.version_regex, re.MULTILINE | re.VERBOSE)
                    .search(output)
                    .groupdict()
                ).get("version")
                logger.debug(f"Extracted version: {version_string}")
                return parse_version(version_string)

    @cachedproperty
    def supported(self):
        """Is the package manager supported on that platform?"""
        return CURRENT_OS_ID in self.platforms

    @cachedproperty
    def executable(self):
        """Is the package manager CLI can be executed by the current user?"""
        if not self.cli_path:
            return False
        if not os.access(self.cli_path, os.X_OK):
            logger.debug(f"{self.cli_path} not executable.")
            return False
        return True

    @cachedproperty
    def fresh(self):
        """Does the package manager match the version requirement?"""
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

        # is supported on the current platform,
        # was found on the system,
        # is executable, and
        # match the version requirement.
        """
        return bool(self.supported and self.cli_path and self.executable and self.fresh)

    def run(self, *args):
        """Run a shell command, return the output and accumulate error messages.

        args is allowed to be a nested structure of iterables, in which case it will
        be recursively flatten, and each item within casted to strings.

        Running commands with that method:
          * adds logs at the appropriate level
          * removes ANSI escape codes from ``<stdout>`` and ``<stderr>``
          * returns ready-to-use normalized strings (dedented and stripped)
          * let ``--dry-run`` and ``--stop-on-error`` have effect on execution

        ..todo:

            Move ``--dry-run`` option and this method to click-extra?
        """
        # Casting to string helps serialize Path and Version objects.
        args = list(map(str, flatten(args)))
        args_str = theme.invoked_command(" ".join(args))
        cli_msg = f"{PROMPT}{args_str}"

        code = 0
        output = None
        error = None

        if self.dry_run:
            logger.warning(f"Dry-run: {cli_msg}")
        else:
            logger.debug(cli_msg)
            code, output, error = run(*args)

        # Normalize messages.
        if error:
            error = dedent(strip_ansi(error).strip())
            error = error if error else None
        if output:
            output = dedent(strip_ansi(output).strip())
            output = output if output else None

        # Log <stdout> and <stderr> output.
        if output:
            logger.debug(indent(output, INDENT))
        if error:
            # Non-fatal error messages are logged as warnings.
            log_func = logger.error if code else logger.warning
            log_func(indent(error, INDENT))

        # Non-successful run.
        if code and error:
            # Produce an exception and eventually raise it.
            exception = CLIError(code, output, error)
            if self.stop_on_error:
                raise exception
            # Accumulate errors.
            self.cli_errors.append(exception)

        return output

    def run_cli(self, *args, skip_globals=False, force_exec=False):
        """Shortcut utility to the ``run`` method above, that is explicitly using the
        binary set by the ``cli_path`` property.

        ``global_args`` are automaticcaly added before the provided args unless
        ``prepend_global_args`` is ``False``. if ``skip_globals`` is ``True`` global arguments
        are not added whatsoever to the list of provided ``args``.

        Also offer the possibility to force the execution and completion of the command
        regardless of ``--dry-run`` and ``--stop-on-error`` user options.
        """
        # Prepare the full list of CLI arguments.
        if not skip_globals:
            if self.prepend_global_args:
                args = list(self.global_args) + list(args)
            else:
                args = list(args) + list(self.global_args)

        # Temporarily replace --dry-run and --stop-on-error user options with our own.
        if force_exec:
            user_options = (self.dry_run, self.stop_on_error)
            self.dry_run, self.stop_on_error = False, False

        # Execute the command.
        output = self.run(self.cli_path, args)

        # Restore user options for --dry-run and --stop-on-error.
        if force_exec:
            self.dry_run, self.stop_on_error = user_options

        return output

    def sync(self):
        """Refresh local manager metadata from remote repository."""
        if self.sync.__func__.__qualname__ == PackageManager.sync.__qualname__:
            logger.warning(f"{self.id} does not implement sync command.")
            return
        logger.info(f"Sync {self.id} package info...")

    def cleanup(self):
        """Remove left-overs and unused packages."""
        if self.cleanup.__func__.__qualname__ == PackageManager.cleanup.__qualname__:
            logger.warning(f"{self.id} does not implement cleanup command.")
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

    def install(self, package_id):
        """Install one package and one only."""
        if self.install.__func__.__qualname__ == PackageManager.install.__qualname__:
            logger.warning(f"{self.id} does not implement install command.")
            return
        logger.info(f"Install {package_id} package from {self.id}...")

    @property
    def outdated(self):
        """List currently installed packages having a new version available.

        Returns a dict indexed by package IDs. Each item is a dict with
        package ID, name, current installed version and latest upgradeable
        version.
        """
        raise NotImplementedError

    def upgrade_cli(self, package_id=None):
        """Return a shell-compatible full-CLI to upgrade a package."""
        raise NotImplementedError

    def upgrade(self, package_id=None):
        """Perform the upgrade of the provided package to latest version."""
        return self.run(self.upgrade_cli(package_id))

    def upgrade_all_cli(self):
        """Return a shell-compatible full-CLI to upgrade all packages.

        Piggy-back on upgrade_cli() by default, which we'll call without a package_id parameter.
        """
        return self.upgrade_cli()

    def upgrade_all(self):
        """Perform a full upgrade of all outdated packages to latest versions.

        If the manager doesn't implements a full upgrade one-liner, then
        fall-back to calling single-package upgrade one by one.
        """
        try:
            return self.run(self.upgrade_all_cli())
        except NotImplementedError:
            logger.warning(f"{self.id} does not implement upgrade_all command.")
            logger.info(f"Call single-package upgrade CLI one by one.")
            log = []
            for package_id in self.outdated:
                output = self.upgrade(package_id)
                if output:
                    log.append(output)
            if log:
                return "\n".join(log)

    @staticmethod
    def render_cli(cmd, cli_format="plain"):
        """Return a formatted CLI in the requested format.

        * ``plain`` returns a simple string
        * ``fragments`` returns a list of strings
        * ``xbar`` returns a CLI with parameters formatted into the xbar dialect
        """
        assert isinstance(cmd, list)
        assert cli_format in CLI_FORMATS
        cmd = map(str, flatten(cmd))  # Serialize Path instances.

        if cli_format == "fragments":
            return list(cmd)

        if cli_format == "plain":
            return " ".join(cmd)

        # Renders the CLI into xbar dialect.
        xbar_params = []
        for index, param_value in enumerate(cmd):
            param_id = "shell" if index == 0 else f"param{index}"
            xbar_params.append(f"{param_id}={param_value}")
        return " | ".join(xbar_params)
