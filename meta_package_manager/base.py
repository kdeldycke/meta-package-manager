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
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from shutil import which
from textwrap import dedent, indent, shorten
from typing import (
    Callable,
    ContextManager,
    Iterable,
    Iterator,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
)
from unittest.mock import patch

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from boltons.cacheutils import cachedproperty as cached_property

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from boltons.typeutils import classproperty
from click_extra.colorize import theme
from click_extra.platform import CURRENT_OS_ID, is_linux
from click_extra.run import INDENT, format_cli, run_cmd

from . import logger
from .version import TokenizedString, parse_version

Operations = Enum(
    "Operations",
    (
        "installed",
        "outdated",
        "search",
        "install",
        "upgrade",
        "remove",
        "sync",
        "cleanup",
    ),
)
"""Recognize operation IDs that are implemented by package manager with their specific CLI invokation.

Each operation has its own CLI subcommand.
"""


class CLIError(Exception):

    """An error occurred when running package manager CLI."""

    def __init__(self, code: int, output: str, error: str):
        """The exception internally keeps the result of CLI execution."""
        super().__init__()
        self.code = code
        self.output = output
        self.error = error

    def __str__(self) -> str:
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

    def __repr__(self) -> str:
        error_excerpt = shorten(
            " ".join(self.error.split()), width=60, placeholder="(...)"
        )
        return f"<{self.__class__.__name__}({self.code}, {error_excerpt!r})>"


@dataclass
class Package:
    """Lightweight representation of a package and its metadata."""

    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    # installed_version and latest_version are allowed to temporarily be a string between __init__ and __post_init__.
    installed_version: Optional[Union[TokenizedString, str]] = None
    latest_version: Optional[Union[TokenizedString, str]] = None

    def __post_init__(self) -> None:
        # Make sure version strings are parsed into proper objects.
        self.installed_version = parse_version(self.installed_version)
        self.latest_version = parse_version(self.latest_version)


_EnvVars = Optional[dict[str, str]]

# XXX Recursive types are not supported by mypy yet: https://github.com/python/mypy/issues/731
# _NestedArgs = Iterable[Union[str, Path, None, Iterable["_NestedArgs"]]]
_Arg = Union[str, Path, None]
_Args = Iterable[_Arg]
_NestedArgs = Iterable[
    Union[
        _Arg, Iterable[Union[_Arg, Iterable[Union[_Arg, Iterable[Union[_Arg, _Args]]]]]]
    ]
]


T = TypeVar("T")
_ClassProperty = Union[T, Callable[["PackageManager"], T]]


class PackageManager:

    """Base class from which all package manager definitions inherits."""

    @classproperty
    def _id_default_getter(cls) -> str:
        """Returns package manager's ID.

        Derived by defaults from the lower-cased class name in which underscores ``_`` are replaced
        by dashes ``-``.

        This ID must be unique among all package manager definitions and lower-case, as
        they're used as feature flags for the :program:`mpm` CLI.
        """
        return cls.__name__.lower().replace("_", "-")  # type: ignore

    id: _ClassProperty[str] = _id_default_getter

    @classproperty
    def _name_default_getter(cls) -> str:
        """Return package manager's common name.

        Defaults based on class name.
        """
        return cls.__name__  # type: ignore

    name: _ClassProperty[str] = _name_default_getter

    homepage_url: Optional[str] = None
    """Home page of the project, only used in documentation for reference."""

    platforms: frozenset = frozenset()
    """List of platforms supported by the manager."""

    requirement: Optional[str] = None
    """Minimal required version.

    Should be a string parseable by :py:class:`meta_package_manager.version.parse_version`.

    Defaults to ``None``, which deactivate version check entirely.
    """

    _CliNames = Union[tuple[Union[str, _ClassProperty[str]], ...], None]

    @classproperty
    def _cli_names_default_getter(cls) -> _CliNames:
        """List of CLI names the package manager is known as.

        The supported CLI names are ordered by priority. This is used for example to
        help out the search of the right binary in the case of the python3/python2
        transition.

        Is derived by default from the manager's ID.
        """
        return (cls.id,)

    cli_names: _ClassProperty[_CliNames] = _cli_names_default_getter

    cli_search_path: tuple[str, ...] = ()
    """ List of additional path to help :program:`mpm` hunt down the package manager CLI.

    Should be a list of strings whose order dictatate the search sequence.

    Most of the time unnecessary: :py:func:`meta_package_manager.base.PackageManager.cli_path`
    works well on all platforms.
    """

    extra_env: _EnvVars = None
    """Additional environment variables to add to the current context.

    Automatically applied on each :py:func:`meta_package_manager.base.PackageManager.run_cli`
    calls.
    """

    pre_cmds: tuple[str, ...] = ()
    """Global list of pre-commands to add before before invoked CLI.

    Automatically added to each :py:func:`meta_package_manager.base.PackageManager.run_cli`
    call.

    Used to prepend `sudo <https://www.sudo.ws>`_ or other system utilities.
    """

    pre_args: tuple[str, ...] = ()
    post_args: tuple[str, ...] = ()
    """Global list of options used before and after the invoked package manager CLI.

    Automatically added to each :py:func:`meta_package_manager.base.PackageManager.run_cli`
    call.

    Essentially used to force silencing, low verbosity or no-color output.
    """

    version_cli_options: tuple[str, ...] = ("--version",)
    """List of options to get the version from the package manager CLI."""

    version_regex: str = r"(?P<version>\S+)"
    """ Regular expression used to extract the version number from the result of the CLI
    run with the options above. It doesn't matter if the regex returns unsanitized
    and crappy string. The :py:func:`meta_package_manager.base.PackageManager.version`
    method will clean and normalized it.

    By default match the first part that is space-separated.
    """

    stop_on_error: bool = False
    """Tell the manager to either raise or continue on errors."""

    ignore_auto_updates: bool = True
    """Some managers can report or ignore packages which have their own auto-update mechanism.
    """

    dry_run: bool = False
    """Do not actually perform any action, just simulate CLI calls."""

    cli_errors: list[CLIError]
    """Accumulate all CLI errors encountered by the package mananger."""

    package_class: Type[Package] = Package
    """The dataclass to use to produce Package objects from the manager."""

    def __init__(self) -> None:
        """Initialize ``cli_errors`` list."""
        self.cli_errors = []

    @classmethod
    def implements(cls, op: Operations) -> bool:
        """Inspect manager implementation to check for proper support of an operation."""
        logger.debug(f"Is {cls} implementing {op}?")

        # Derive the method ID that is hinting at proper implementation of the operation.
        # Special case for `upgrade` for which `upgrade_cli()` is the minimal method from which the manager is capable of executing all upgrade operations.
        method_id = "upgrade_cli" if op == Operations.upgrade else op.name

        # If none of the classes in the inheritance hierarchy up to the base one implements the operation, then we can be certain
        # the manager doesn't implement the operation at all.
        for klass in cls.mro():
            if klass is PackageManager:
                return False
            # Presence of the operation function is not enough to rules out proper implementation, as it can
            # be a method that raises NotImplemented error anyway. See for instance the upgrade_all_cli in pip.py:
            # https://github.com/kdeldycke/meta-package-manager/blob/4acc003bd268a59f5a79cf317be6d25a90878f6d/meta_package_manager/managers/pip.py#L271-L279
            if method_id in klass.__dict__:
                return True

        raise NotImplementedError(f"Can't guess {cls} implementation of {op}.")

    @classproperty
    def virtual(cls) -> bool:
        """Should we expose the package manager to the user?

        Virtual package manager are just skeleton classes used to factorize code among
        managers of the same family.
        """
        return cls.__name__ == "PackageManager" or not cls.cli_names  # type: ignore

    @cached_property
    def cli_path(self) -> Union[Path, None]:
        """Fully qualified path to the package manager CLI.

        Automatically search the location of the CLI in the system. Try multiple CLI
        names within several system path.

        Only checks if the file exists. Its executability will be assessed later. See
        the :py:func:`meta_package_manager.base.PackageManager.executable` method below.

        Returns ``None`` if no CLI was found or those found were not a file.
        """
        # Check if the path exist in any of the environment locations.
        env_path = ":".join(flatten((self.cli_search_path, os.getenv("PATH"))))

        # Search for multiple CLI names.
        cli_path_found = False
        if self.cli_names is not None:
            for name in self.cli_names:
                cli_path_found = which(name, mode=os.F_OK, path=env_path)
                if cli_path_found:
                    break
                logger.debug(f"{theme.invoked_command(name)} CLI not found.")

        if not cli_path_found:
            return None

        # Check if path exist and is a file.
        # Do not resolve symlink here. Some manager like Homebrew on Linux rely on some
        # sort of synlink trickery to set environment variables.
        cli_path = Path(cli_path_found)
        if not cli_path.exists():
            raise FileNotFoundError(f"{cli_path}")
        elif not cli_path.is_file():
            logger.warning(f"{theme.invoked_command(cli_path)} is not a file.")
        else:
            logger.debug(
                f"{theme.invoked_command(name)} CLI found at {theme.invoked_command(cli_path)}"
            )

        return cli_path

    @cached_property
    def version(self) -> Union[TokenizedString, None]:
        """Invoke the manager and extract its own reported version string.

        Returns a parsed and normalized version in the form of a
        :py:class:`meta_package_manager.version.TokenizedString` instance.
        """
        if self.executable:
            # Invoke the manager.
            try:
                output = self.run_cli(
                    self.version_cli_options,
                    auto_pre_cmds=False,
                    auto_pre_args=False,
                    auto_post_args=False,
                    force_exec=True,
                )
            # Catch false-positive CLIs.
            except OSError as ex:
                # In the environment on Windows, extension of available executables are
                # ignored as they're plenty: .EXE, .CMD, .BAT, ...
                # See: https://github.com/kdeldycke/meta-package-manager/issues/542
                # Check for "OSError: [WinError 193] %1 is not a valid Win32
                # application" error.
                if getattr(ex, "winerror", None) == 193:
                    logger.debug(
                        f"{theme.invoked_command(self.cli_path)} is not a valid Windows application."
                    )
                    # Declare CLI as un-executable.
                    self.executable = False
                    return None
                # Unidentified error: re-raise.
                raise

            # Extract the version with the regex.
            parts = re.compile(self.version_regex, re.MULTILINE | re.VERBOSE).search(
                output
            )
            if parts:
                version_string = parts.groupdict().get("version")
                logger.debug(f"Extracted version: {version_string!r}")
                parsed_version = parse_version(version_string)
                logger.debug(f"Parsed version: {parsed_version!r}")
                return parsed_version
        return None

    @cached_property
    def supported(self) -> bool:
        """Is the package manager supported on that platform?"""
        return CURRENT_OS_ID in self.platforms

    @cached_property
    def executable(self) -> bool:
        """Is the package manager CLI can be executed by the current user?"""
        if not self.cli_path:
            return False
        if not os.access(self.cli_path, os.X_OK):
            logger.debug(f"{self.cli_path} is not allowed to be executed.")
            return False
        return True

    @cached_property
    def fresh(self) -> bool:
        """Does the package manager match the version requirement?"""
        # Version is mandatory.
        if not self.version:
            return False
        if self.requirement:
            if self.version < parse_version(self.requirement):
                logger.debug(
                    f"{self.id} {self.version} is older than "
                    f"{self.requirement} version requirement."
                )
                return False
        return True

    @cached_property
    def available(self) -> bool:
        """Is the package manager available and ready-to-use on the system?

        Returns ``True`` only if the main CLI:

        1. is :py:attr:`supported on the current platform <meta_package_manager.base.PackageManager.supported>`,
        2. was :py:attr:`found on the system <meta_package_manager.base.PackageManager.cli_path>`,
        3. is :py:attr:`executable <meta_package_manager.base.PackageManager.executable>`, and
        4. :py:attr:`match the version requirement <meta_package_manager.base.PackageManager.fresh>`.
        """
        logger.debug(
            f"{self.id} is supported: {self.supported}; "
            f"found at: {self.cli_path}; "
            f"is executable: {self.executable}; "
            f"is fresh: {self.fresh}."
        )
        return bool(self.supported and self.cli_path and self.executable and self.fresh)

    @classmethod
    def _args_cleanup(cls, *args: Union[_Arg, _NestedArgs]) -> tuple[str, ...]:
        """Flatten recursive iterables, remove all ``None``, and cast each element to
        strings.

        Helps serialize :py:class:`pathlib.Path` and :py:class:`meta_package_manager.version.TokenizedString` objects.
        """
        return tuple(str(arg) for arg in flatten(args) if arg is not None)

    def run(self, *args: Union[_Arg, _NestedArgs], extra_env: _EnvVars = None) -> str:
        """Run a shell command, return the output and accumulate error messages.

        ``args`` is allowed to be a nested structure of iterables, in which case it will
        be recursively flatten, then ``None`` will be discarded, and finally each item
        casted to strings.

        Running commands with that method takes care of:
          * adding logs at the appropriate level
          * removing ANSI escape codes from :py:attr:`subprocess.CompletedProcess.stdout` and :py:attr:`subprocess.CompletedProcess.stderr`
          * returning ready-to-use normalized strings (dedented and stripped)
          * letting :option:`mpm --dry-run` and :option:`mpm --stop-on-error` have expected effect on execution

        .. todo::

            Move :option:`mpm --dry-run` option and this method to `click-extra <https://github.com/kdeldycke/click-extra>`_.
        """
        # Casting to string helps serialize Path and Version objects.
        clean_args = self._args_cleanup(*args)
        cli_msg = format_cli(clean_args, extra_env)

        code = 0
        output = ""
        error = ""

        if self.dry_run:
            logger.warning(f"Dry-run: {cli_msg}")
        else:
            logger.debug(cli_msg)
            code, output, error = run_cmd(
                *clean_args, extra_env=extra_env, print_output=False
            )

        # Normalize messages.
        if error:
            error = dedent(strip_ansi(error).strip())
        if output:
            output = dedent(strip_ansi(output).strip())

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

    def build_cli(
        self,
        *args: Union[_Arg, _NestedArgs],
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_pre_cmds: Optional[_NestedArgs] = None,
        override_cli_path: Optional[Path] = None,
        override_pre_args: Optional[_NestedArgs] = None,
        override_post_args: Optional[_NestedArgs] = None,
        sudo: bool = False,
    ) -> tuple[str, ...]:
        """Build the package manager CLI by combining the custom ``*args`` with the
        package manager's global parameters.

        Returns a tuple of strings.

        Helps the construction of CLI's repeating patterns and makes the code easier to read. Just pass the
        specific ``*args`` and the full CLI string will be composed out of the globals,
        following this schema:

        .. code-block:: shell-session

            $ [<self.pre_cmds>|sudo] <self.cli_path> <self.pre_args> <*args> <self.post_args>

        * :py:attr:`self.pre_cmds <meta_package_manager.base.PackageManager.pre_cmds>` is added before the CLI path.

        * :py:attr:`self.cli_path <meta_package_manager.base.PackageManager.cli_path>` is used as the main binary to execute.

        * :py:attr:`self.pre_args <meta_package_manager.base.PackageManager.pre_args>` and :py:attr:`self.post_args <meta_package_manager.base.PackageManager.post_args>`  globals are added before and after
          the provided ``*args``.

        Each additional set of elements can be disabled with their respective flag:

        * ``auto_pre_cmds=False``  to skip the automatic addition of :py:attr:`self.pre_cmds <meta_package_manager.base.PackageManager.pre_cmds>`
        * ``auto_pre_args=False``  to skip the automatic addition of :py:attr:`self.pre_args <meta_package_manager.base.PackageManager.pre_args>`
        * ``auto_post_args=False`` to skip the automatic addition of :py:attr:`self.post_args <meta_package_manager.base.PackageManager.post_args>`

        Each global set of elements can be locally overriden with:

        * ``override_pre_cmds=tuple()``
        * ``override_cli_path=str``
        * ``override_pre_args=tuple()``
        * ``override_post_args=tuple()``

        On linux, the command can be run with `sudo <https://www.sudo.ws>`_ if the parameter of the same name is set to ``True``.
        In which case the ``override_pre_cmds`` parameter is not allowed to be set and the ``auto_pre_cmds`` parameter is forced to ``False``.
        """
        params: list[Union[_Arg, _NestedArgs]] = []

        # Sudo replaces any pre-command, be it overriden or automatic.
        if sudo:
            if not is_linux():
                raise NotImplementedError("sudo only supported on Linux.")
            if override_pre_cmds:
                raise ValueError("Pre-commands not allowed if sudo is requested.")
            if auto_pre_cmds:
                auto_pre_cmds = False
            params.append("sudo")
        elif override_pre_cmds:
            params.extend(override_pre_cmds)
        elif auto_pre_cmds:
            params.extend(self.pre_cmds)

        if override_cli_path:
            params.append(override_cli_path)
        else:
            params.append(self.cli_path)

        if override_pre_args:
            params.extend(override_pre_args)
        elif auto_pre_args:
            params.extend(self.pre_args)

        if args:
            params.extend(args)

        if override_post_args:
            params.extend(override_post_args)
        elif auto_post_args:
            params.extend(self.post_args)

        return self._args_cleanup(cast(_NestedArgs, params))

    def run_cli(
        self,
        *args: Union[_Arg, _NestedArgs],
        auto_extra_env: bool = True,
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_extra_env: _EnvVars = None,
        override_pre_cmds: Optional[_NestedArgs] = None,
        override_cli_path: Optional[Path] = None,
        override_pre_args: Optional[_NestedArgs] = None,
        override_post_args: Optional[_NestedArgs] = None,
        force_exec: bool = False,
        sudo: bool = False,
    ) -> str:
        """Build and run the package manager CLI by combining the custom ``*args`` with
        the package manager's global parameters.

        After the CLI is built with the :py:meth:`meta_package_manager.base.PackageManager.build_cli` method, it is executed with
        the :py:meth:`meta_package_manager.base.PackageManager.run` method, augmented with
        environment variables from :py:attr:`self.extra_env <meta_package_manager.base.PackageManager.extra_env>`.

        All parameters are the same as :py:meth:`meta_package_manager.base.PackageManager.build_cli`, plus:

        * ``auto_extra_env=False`` to skip the automatic addition of :py:attr:`self.extra_env <meta_package_manager.base.PackageManager.extra_env>`
        * ``override_extra_env=dict()`` to locally overrides the later
        * ``force_exec`` ignores the :option:`mpm --dry-run` and :option:`mpm --stop-on-error` options to force
          the execution and completion of the command.
        """
        cli = self.build_cli(
            *args,
            auto_pre_cmds=auto_pre_cmds,
            auto_pre_args=auto_pre_args,
            auto_post_args=auto_post_args,
            override_pre_cmds=override_pre_cmds,
            override_cli_path=override_cli_path,
            override_pre_args=override_pre_args,
            override_post_args=override_post_args,
            sudo=sudo,
        )

        # Prepare the full list of CLI arguments.
        extra_env = None
        if override_extra_env:
            extra_env = override_extra_env
        elif auto_extra_env:
            extra_env = self.extra_env

        # No-op context manager without any effects.
        local_option1: ContextManager = nullcontext()
        local_option2: ContextManager = nullcontext()
        # Temporarily replace --dry-run and --stop-on-error user options with our own.
        if force_exec:
            local_option1 = patch.object(self, "dry_run", False)
            local_option2 = patch.object(self, "stop_on_error", False)
        # Execute the command with eventual local options.
        with local_option1, local_option2:
            output = self.run(*cli, extra_env=extra_env)

        return output

    def package(self, *args, **kwargs) -> Package:
        """Produce a ``Package`` object with provided attributes."""
        return self.package_class(*args, **kwargs)

    @property
    def installed(self) -> Iterator[Package]:
        """List packages currently installed on the system.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    @property
    def outdated(self) -> Iterator[Package]:
        """List installed packages with available upgrades.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    @classmethod
    def query_parts(cls, query: str) -> set[str]:
        """Returns a set of all contiguous alphanumeric string segments.

        Contrary to :py:class:`meta_package_manager.version.TokenizedString`, do no splits on colated number/alphabetic junctions.
        """
        return {p for p in re.split(r"\W+", query) if p}

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search packages available for install.

        There is no need for this method to be perfect and sensitive to ``extended`` and ``exact`` parameters. If the package manager
        is not supporting these kind of options out of the box, just returns the closest subset of matching package you can
        come up with. Finer refiltering will happens in the :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` method below.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def refiltered_search(
        self, query: str, extended: bool, exact: bool
    ) -> Iterator[Package]:
        """Returns search results with extra manual refiltering to refine gross
        matchings.

        Some package managers returns unbounded results, and/or don't support fine
        search criterions. In which case we use this method to manually refilters
        :py:meth:`meta_package_manager.base.PackageManager.search` results to either
        exclude non-extended or non-exact matches.

        Returns a generator producing the same data as the
        :py:meth:`meta_package_manager.base.PackageManager.search` method above.

        .. tip::

            If you are implementing a package manager definition, do not waste time to
            filter CLI results. Let this method do this job.

            Instead, just implement the core
            :py:meth:`meta_package_manager.base.PackageManager.search` method above and
            try to produce results as precise as possible using the native filtering
            capabilities of the package manager CLI.
        """
        for match in self.search(query, extended, exact):
            # Look by default into package ID and name.
            search_content = {match.id, match.name}

            # Rejects fuzzy results: only keep packages stricly matching on ID or name.
            if exact and query not in search_content:
                continue

            # Add description to the list of content to look into.
            if extended:
                search_content.add(match.description)

            # Normalize searched content.
            serialized_content = "".join({s.lower() for s in search_content if s})

            # Exclude packages not matching any part of the query.
            confirmed_match = False
            for part in {p.lower() for p in self.query_parts(query)}:
                if part in serialized_content:
                    confirmed_match = True
                    break
            if not confirmed_match:
                continue

            # Report the package as matching.
            yield match

    def install(self, package_id: str) -> str:
        """Install one package and one only.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def upgrade_cli(self, package_id: Optional[str] = None) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade the package provided as ``package_id``
        parameter.

        If ``package_id`` is ``None``, the returned CLI is expected be the one that is
        used to upgrade all outdated packages on the system.
        """
        raise NotImplementedError

    def upgrade(self, package_id: Optional[str] = None) -> str:
        """Perform the upgrade of the provided package to latest version.

        Executes the CLI provided by :py:meth:`meta_package_manager.base.PackageManager.upgrade_cli`.
        """
        return self.run(self.upgrade_cli(package_id), extra_env=self.extra_env)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade all outdated packages on the system.

        By default, returns the result of the :py:meth:`meta_package_manager.base.PackageManager.upgrade_cli`
        method, without a ``package_id`` parameter.

        This dedicated method allows some package manager to return a CLI that is very different from the
        one returned by :py:meth:`meta_package_manager.base.PackageManager.upgrade_cli`.

        It can also be used to ``raise NotImplementedError`` on some managers to signal to :program:`mpm` that
        the package manager has no proper support for a full upgrade operation. See for example
        :py:meth:`meta_package_manager.managers.pip.Pip.upgrade_all_cli`.
        """
        return self.upgrade_cli()

    def upgrade_all(self) -> str:
        """Perform a full upgrade of all outdated packages on the system.

        Executes the CLI provided by :py:meth:`meta_package_manager.base.PackageManager.upgrade_all_cli`.

        If the manager doesn't provides a full upgrade one-liner (i.e. if
        :py:meth:`meta_package_manager.base.PackageManager.upgrade_all_cli` raises
        :py:exc:`NotImplementedError`), then the list of all outdated packages will be fetched
        (via :py:meth:`meta_package_manager.base.PackageManager.outdated`) and each package will be
        updated one by one by a :py:meth:`meta_package_manager.base.PackageManager.upgrade` call.
        """
        try:
            return self.run(self.upgrade_all_cli(), extra_env=self.extra_env)
        except NotImplementedError:
            logger.warning(f"{self.id} does not implement upgrade_all operation.")

        logger.info(f"Fallback to calling upgrade operation on each outdated package.")
        log = ""
        for package in self.outdated:
            output = self.upgrade(package.id)
            if output:
                log += f"\n{output}"
        return log

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def sync(self) -> None:
        """Refresh package metadata from remote repositories.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """Removes left-overs, orphaned dependencies,

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError
