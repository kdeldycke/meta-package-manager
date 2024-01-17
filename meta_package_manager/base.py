# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from textwrap import dedent, indent, shorten
from typing import ContextManager, Generator, Iterable, Iterator, cast
from unittest.mock import patch

from boltons.iterutils import flatten, unique
from boltons.strutils import strip_ansi
from click_extra.colorize import default_theme as theme
from click_extra.platforms import UNIX, Group, Platform, current_os
from click_extra.testing import (
    INDENT,
    Arg,
    EnvVars,
    NestedArgs,
    args_cleanup,
    env_copy,
    format_cli_prompt,
)

from .version import TokenizedString, parse_version

Operations = Enum(
    "Operations",
    (
        "installed",
        "outdated",
        "search",
        "install",
        "upgrade",
        "upgrade_all",
        "remove",
        "sync",
        "cleanup",
    ),
)
"""Recognized operation IDs that are implemented by package manager with their specific
CLI invocation.

Each operation has its own CLI subcommand.
"""


class CLIError(Exception):
    """An error occurred when running package manager CLI."""

    def __init__(self, code: int, output: str, error: str) -> None:
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
                {indented_error}""",
            ),
            INDENT,
        )

    def __repr__(self) -> str:
        error_excerpt = shorten(
            " ".join(self.error.split()),
            width=60,
            placeholder="(...)",
        )
        return f"<{self.__class__.__name__}({self.code}, {error_excerpt!r})>"


@dataclass
class Package:
    """Lightweight representation of a package and its metadata."""

    id: str
    """ID is required and is the primary key used by the manager."""

    name: str | None = None

    description: str | None = None

    installed_version: TokenizedString | str | None = None
    latest_version: TokenizedString | str | None = None
    """Installed and latest versions are optional: they're not always provided by the
    package manager.

    ``installed_version`` and ``latest_version`` are allowed to temporarily be strings
    between ``__init__`` and ``__post_init__``. Once they reach the later, they're
    parsed and normalized into either ``TokenizedString`` or `None`. They can't be
    strings beyong that point, i.e. after the Package instance has been fully
    instantiated. We don't know how to declare this transient state with type hints,
    so we're just going to allow string type.
    """

    def __post_init__(self) -> None:
        # Make sure version strings are parsed into proper objects.
        self.installed_version = parse_version(self.installed_version)
        self.latest_version = parse_version(self.latest_version)


def packages_asdict(packages: Iterator[Package], keep_fields: tuple[str, ...]):
    """Returns a list of packages casted to a ``dict`` with only a subset of its
    fields."""
    return ({k: v for k, v in asdict(p).items() if k in keep_fields} for p in packages)


class MetaPackageManager(type):
    """Custom metaclass used as a class factory for package managers."""

    def __init__(cls, name, bases, dct) -> None:
        """Sets some class defaults, but only if they're not redefined in the final
        manager class.

        Also normalize list of platform, by ungrouping groups, deduplicate entries and
        freeze them into a set of unique platforms.
        """
        if "id" not in dct:
            cls.id = name.lower().replace("_", "-")

        if "name" not in dct:
            cls.name = name

        if "cli_names" not in dct:
            cls.cli_names = (cls.id,)

        if "virtual" not in dct:
            cls.virtual = name == "PackageManager" or not cls.cli_names

        if "platforms" in dct:
            platforms = set()
            for spec in flatten([dct["platforms"]]):
                if isinstance(spec, Platform):
                    platforms.add(spec)
                elif isinstance(spec, Group):
                    platforms |= set(spec.platforms)
                else:
                    msg = f"Unrecognized platform specifier: {spec!r}"
                    raise ValueError(msg)
            cls.platforms = frozenset(platforms)


def highlight_cli_name(path: Path | None, match_names: Iterable[str]) -> str | None:
    """Highlight the binary name in the provided ``path``.

    If ``match_names`` is provided, only highlight the start of the binary name that is
    in the list.

    Matchin is insensitive to case on Windows and case-sensitive on other platforms,
    thanks to ``os.path.normcase``.
    """
    if path is None:
        return None

    highlighted_name = path.name
    for ref_name in match_names:
        if os.path.normcase(ref_name).startswith(os.path.normcase(path.name)):
            highlighted_name = (
                theme.invoked_command(path.name[: len(ref_name)])
                + path.name[len(ref_name) :]
            )
            break

    return f"{path.parent}{os.path.sep}{highlighted_name}"


class PackageManager(metaclass=MetaPackageManager):
    """Base class from which all package manager definitions inherits."""

    deprecated: bool = False
    """A manager marked as deprecated will be hidden from all package selection by
    default.

    You can still use it but need to explicitly call for it on the command line.

    Implementation of a deprecated manager will be kept within mpm source code, but some
    of its features or total implementation are allowed to be scraped in the face of
    maintenance pain and adversity.

    Integration tests and unittests for deprecated managers can be removed. We do not
    care if a deprecated manager is not 100% reliable. A flakky deprecated manager
    should not block a release due to flakky tests.
    """

    deprecation_url: str | None = None
    """Announcement from the official project or evidence of abandonment of
    maintainance."""

    id: str
    """Package manager's ID.

    Derived by defaults from the lower-cased class name in which underscores ``_`` are
    replaced by dashes ``-``.

    This ID must be unique among all package manager definitions and lower-case, as
    they're used as feature flags for the :program:`mpm` CLI.
    """

    name: str
    """Return package manager's common name.

    Default value is based on class name.
    """

    homepage_url: str | None = None
    """Home page of the project, only used in documentation for reference."""

    platforms: Group | Platform | Iterable[Group | Platform] | frozenset[Platform] = (
        frozenset()
    )
    """List of platforms supported by the manager.

    Allows for a mishmash of platforms and groups. Will be normalized into a frozen set
    of ``Platform`` instances at instanciation.
    """

    requirement: str | None = None
    """Minimal required version.

    Should be a string parseable by
    :py:class:`meta_package_manager.version.parse_version`.

    Defaults to ``None``, which deactivate version check entirely.
    """

    cli_names: tuple[str, ...]
    """List of CLI names the package manager is known as.

    The supported CLI names are ordered by priority. This is used for example to help
    out the search of the right binary in the case of the python3/python2 transition.

    Is derived by default from the manager's ID.
    """

    virtual: bool
    """Should we expose the package manager to the user?

    Virtual package manager are just skeleton classes used to factorize code among
    managers of the same family.
    """

    cli_search_path: tuple[str, ...] = ()
    """List of additional path to help :program:`mpm` hunt down the package manager CLI.

    Must be a list of strings whose order dictates the search sequence.

    Most of the time unnecessary:
    :py:func:`meta_package_manager.base.PackageManager.cli_path` works well on all
    platforms.
    """

    extra_env: EnvVars | None = None
    """Additional environment variables to add to the current context.

    Automatically applied on each
    :py:func:`meta_package_manager.base.PackageManager.run_cli` calls.
    """

    pre_cmds: tuple[str, ...] = ()
    """Global list of pre-commands to add before before invoked CLI.

    Automatically added to each
    :py:func:`meta_package_manager.base.PackageManager.run_cli` call.

    Used to prepend `sudo <https://www.sudo.ws>`_ or other system utilities.
    """

    pre_args: tuple[str, ...] = ()
    post_args: tuple[str, ...] = ()
    """Global list of options used before and after the invoked package manager CLI.

    Automatically added to each
    :py:func:`meta_package_manager.base.PackageManager.run_cli` call.

    Essentially used to force silencing, low verbosity or no-color output.
    """

    version_cli_options: tuple[str, ...] = ("--version",)
    """List of options to get the version from the package manager CLI."""

    version_regex: str = r"(?P<version>\S+)"
    """Regular expression used to extract the version number from the result of the CLI
    run with the options above. It doesn't matter if the regex returns unsanitized and
    crappy string. The :py:func:`meta_package_manager.base.PackageManager.version`
    method will clean and normalized it.

    By default match the first part that is space-separated.
    """

    stop_on_error: bool = False
    """Tell the manager to either raise or continue on errors."""

    ignore_auto_updates: bool = True
    """Some managers can report or ignore packages which have their own auto-update
    mechanism."""

    dry_run: bool = False
    """Do not actually perform any action, just simulate CLI calls."""

    timeout: int | None = None
    """Maximum number of seconds to wait for a CLI call to complete."""

    cli_errors: list[CLIError]
    """Accumulate all CLI errors encountered by the package manager."""

    package: type[Package] = Package
    """The dataclass to use to produce Package objects from the manager."""

    def __init__(self) -> None:
        """Initialize ``cli_errors`` list."""
        self.cli_errors = []

    @classmethod
    def implements(cls, op: Operations) -> bool:
        """Inspect manager's implementation to check for proper support of an
        operation."""
        logging.debug(f"Does {cls} implements {op}?")

        # General case: the operation and the method implementing it shares the same ID.
        method_deps: tuple[set[str], ...] = ({op.name},)

        # Special case for single-package `upgrade`: we depends on `upgrade_one_cli()`.
        if op == Operations.upgrade:
            method_deps = ({"installed", "upgrade_one_cli"},)

        # For `upgrade_all`: we depends on eother `upgrade_all_cli()`, or we can
        # simulate the latter with a combination of `outdated()` and
        # `upgrade_one_cli()`.
        elif op == Operations.upgrade_all:
            method_deps = ({"upgrade_all_cli"}, {"outdated", "upgrade_one_cli"})

        # If none of the classes in the inheritance hierarchy up to the base one
        # implements the operation, then we can be certain the manager doesn't implement
        # the operation at all.
        for klass in cls.mro():
            if klass is PackageManager:
                return False
            # Presence of the operation function is not enough to rules out proper
            # implementation, as it can be a method that raises NotImplemented error
            # anyway. See for instance the upgrade_all_cli in pip.py:
            # https://github.com/kdeldycke/meta-package-manager/blob/4acc003/meta_package_manager/managers/pip.py#L271-L279
            for method_ids in method_deps:
                all_deps_found = method_ids.issubset(klass.__dict__)
                if all_deps_found:
                    return True

        msg = f"Can't guess {cls} implementation of {op}."
        raise NotImplementedError(msg)

    def search_all_cli(
        self,
        cli_names: Iterable[str],
        env=None,
    ) -> Generator[Path, None, None]:
        """Search for all binary files matching the CLI names, in all environment path.

        This is like our own implementation of ``shutil.which()``, with the difference
        that it is capable of returning all the possible paths of the provided file
        names, in all environment path, not just the first one that match. And on
        Windows, prevents matching of CLI in the current directory, which takes
        precedence on other paths.

        Returns all files matching any ``cli_names``, by iterating over all folders in
        this order:
          * folders provided by :py:attr:`cli_search_path
            <meta_package_manager.base.PackageManager.cli_search_path>`,
          * then in all the default places specified by the environment variable (i.e.
            ``os.getenv("PATH")``).

        Only returns files that exists and are not empty.

        .. caution::

            Symlinks are not resolved, because some manager like `Homebrew on Linux
            relies on some sort of symlink-based trickery
            <https://github.com/kdeldycke/meta-package-manager/pull/188>`_ to set
            environment variables.
        """
        # Check CLI names are not path, but plain filenames.
        for cli_name in cli_names:
            assert not os.path.dirname(
                cli_name,
            ), f"CLI name {cli_name} contains path separator {os.path.sep}."

        # Validates each search path.
        for cli_search_path in self.cli_search_path:
            assert os.pathsep not in cli_search_path, (
                f"Search path {cli_search_path} contains "
                f"environment path separator {os.pathsep}."
            )

        # By default, the filename to search for is the case-sensitive CLI name.
        search_filenames = list(cli_names)
        # But on Windows, there is this special ``PATHEXT`` environment variable to
        # tell you what file suffixes are executable. We have to search for any
        # variation of the CLI name with any of these suffixes.
        # Code below is inpired by the original implementation of ``shutil.which()``:
        # https://github.com/python/cpython/blob/8d46c7e/Lib/shutil.py#L1478-L1491
        if sys.platform == "win32":
            pathext_source = os.getenv("PATHEXT") or shutil._WIN_DEFAULT_PATHEXT
            pathext = unique(ext for ext in pathext_source.split(os.pathsep) if ext)
            search_filenames = []
            for cli_name in cli_names:
                # See if the given file matches any of the expected path extensions.
                # This will allow us to short circuit when given "python.exe".
                # If it does match, only test that one, otherwise we have to try
                # others.
                if any(cli_name.lower().endswith(ext.lower()) for ext in pathext):
                    search_filenames.append(cli_name)
                else:
                    search_filenames.extend(f"{cli_name}{ext}" for ext in pathext)
        search_filenames = unique(search_filenames)

        def normalize_path(path: Path) -> str:
            """Resolves symlinks and produces a normalized absolute path string.

            Additonnaly use ``os.path.normcase`` on Windows to exclude duplicates
            produced by case-insensitive filesystems.
            """
            return os.path.normcase(path.resolve())

        # Deduplicate search paths while keeping their order and original value, as the
        # normalization process happens with the ``key`` lookup.
        search_path_list: list[Path] = unique(
            # Manager-specific search path takes precedence over default environment.
            (Path(p) for p in list(self.cli_search_path) + os.get_exec_path(env=env)),
            key=normalize_path,
        )

        logging.debug(
            "Search for "
            + ", ".join(theme.invoked_command(cli) for cli in search_filenames)
            + " in "
            + ", ".join(str(p) for p in search_path_list),
        )

        for search_path in search_path_list:
            if not search_path.is_dir():
                continue

            for filename in search_filenames:
                file = search_path / filename
                if not file.is_file() or not os.path.getsize(file):
                    continue
                logging.debug(f"CLI found at {highlight_cli_name(file, cli_names)}")
                yield file

    def which(self, cli_name: str) -> Path | None:
        """Emulates the ``which`` command.

        Based on the ``search_all_cli()`` method.
        """
        for cli_path_found in self.search_all_cli([cli_name]):
            return cli_path_found
        return None

    @cached_property
    def cli_path(self) -> Path | None:
        """Fully qualified path to the canonical package manager binary.

        Try each CLI names provided by :py:attr:`cli_names
        <meta_package_manager.base.PackageManager.cli_names>`, in each system path
        provided by :py:attr:`cli_search_path
        <meta_package_manager.base.PackageManager.cli_search_path>`. In that order.
        Then returns the first match.

        Executability of the CLI will be separately assessed later by the
        :py:func:`meta_package_manager.base.PackageManager.executable` method below.
        """
        if self.cli_names is not None:
            for cli_path in self.search_all_cli(self.cli_names):
                return cli_path
        return None

    @cached_property
    def version(self) -> TokenizedString | None:
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
                    logging.debug(
                        f"{theme.invoked_command(str(self.cli_path))} "
                        "is not a valid Windows application.",
                    )
                    # Declare CLI as un-executable.
                    self.executable = False
                    return None
                # Unidentified error: re-raise.
                raise

            # Extract the version with the regex.
            parts = re.compile(self.version_regex, re.MULTILINE | re.VERBOSE).search(
                output,
            )
            if parts:
                version_string = parts.groupdict().get("version")
                logging.debug(f"Extracted version: {version_string!r}")
                parsed_version = parse_version(version_string)
                logging.debug(f"Parsed version: {parsed_version!r}")
                return parsed_version
        return None

    @cached_property
    def supported(self) -> bool:
        """Is the package manager supported on that platform?"""
        # At this point self.platforms is normalized as a frozenset of Platform
        # instances, but mypy doesn't know it.
        return current_os() in self.platforms  # type: ignore[operator]

    @cached_property
    def executable(self) -> bool:
        """Is the package manager CLI can be executed by the current user?"""
        if not self.cli_path:
            return False
        if not os.access(self.cli_path, os.X_OK):
            logging.debug(
                f"{highlight_cli_name(self.cli_path, self.cli_names)} "
                "is not allowed to be executed.",
            )
            return False
        return True

    @cached_property
    def fresh(self) -> bool:
        """Does the package manager match the version requirement?"""
        # Version is mandatory.
        if not self.version:
            return False
        if self.requirement and self.version < parse_version(self.requirement):
            logging.debug(
                f"{self.id} {self.version} is older than "
                f"{self.requirement} version requirement.",
            )
            return False
        return True

    @cached_property
    def available(self) -> bool:
        """Is the package manager available and ready-to-use on the system?

        Returns ``True`` only if the main CLI:

        1. is :py:attr:`supported on the current platform
           <meta_package_manager.base.PackageManager.supported>`,
        2. was :py:attr:`found on the system
           <meta_package_manager.base.PackageManager.cli_path>`,
        3. is :py:attr:`executable
           <meta_package_manager.base.PackageManager.executable>`, and
        4. :py:attr:`match the version requirement
           <meta_package_manager.base.PackageManager.fresh>`.
        """
        logging.debug(
            f"{self.id} "
            f"is deprecated: {self.deprecated}; "
            f"is supported: {self.supported}; "
            f"found at: {highlight_cli_name(self.cli_path, self.cli_names)}; "
            f"is executable: {self.executable}; "
            f"is fresh: {self.fresh}.",
        )
        return bool(self.supported and self.cli_path and self.executable and self.fresh)

    def run(self, *args: Arg | NestedArgs, extra_env: EnvVars | None = None) -> str:
        """Run a shell command, return the output and accumulate error messages.

        ``args`` is allowed to be a nested structure of iterables, in which case it will
        be recursively flatten, then ``None`` will be discarded, and finally each item
        casted to strings.

        Running commands with that method takes care of:
          * adding logs at the appropriate level
          * removing ANSI escape codes from
            :py:attr:`subprocess.CompletedProcess.stdout` and
            :py:attr:`subprocess.CompletedProcess.stderr`
          * returning ready-to-use normalized strings (dedented and stripped)
          * letting :option:`mpm --dry-run` and :option:`mpm --stop-on-error` have
            expected effect on execution
        """
        # Casting to string helps serialize Path and Version objects.
        clean_args = args_cleanup(*args)
        cli_msg = format_cli_prompt(clean_args, extra_env)

        code = 0
        output = ""
        error = ""

        if self.dry_run:
            logging.warning(f"Dry-run: {cli_msg}")
        else:
            logging.debug(cli_msg)
            result = subprocess.run(
                clean_args,
                capture_output=True,
                timeout=self.timeout,
                encoding="utf-8",
                env=cast("subprocess._ENV", env_copy(extra_env)),
            )
            code = result.returncode
            output = result.stdout
            error = result.stderr

        # Normalize messages.
        if error:
            error = dedent(strip_ansi(error).strip())
        if output:
            output = dedent(strip_ansi(output).strip())

        # Log <stdout> and <stderr> output.
        if output:
            logging.debug(indent(output, INDENT))
        if error:
            # Non-fatal error messages are logged as warnings.
            log_func = logging.error if code else logging.warning
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
        *args: Arg | NestedArgs,
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_pre_cmds: NestedArgs | None = None,
        override_cli_path: Path | None = None,
        override_pre_args: NestedArgs | None = None,
        override_post_args: NestedArgs | None = None,
        sudo: bool = False,
    ) -> tuple[str, ...]:
        """Build the package manager CLI by combining the custom ``*args`` with the
        package manager's global parameters.

        Returns a tuple of strings.

        Helps the construction of CLI's repeating patterns and makes the code easier to
        read. Just pass the specific ``*args`` and the full CLI string will be composed
        out of the globals, following this schema:

        .. code-block:: shell-session

            $ [<pre_cmds>|sudo] <cli_path> <pre_args> <*args> <post_args>

        * :py:attr:`self.pre_cmds <meta_package_manager.base.PackageManager.pre_cmds>`
          is added before the CLI path.

        * :py:attr:`self.cli_path <meta_package_manager.base.PackageManager.cli_path>`
          is used as the main binary to execute.

        * :py:attr:`self.pre_args <meta_package_manager.base.PackageManager.pre_args>`
          and :py:attr:`self.post_args
          <meta_package_manager.base.PackageManager.post_args>`  globals are added
          before and after the provided ``*args``.

        Each additional set of elements can be disabled with their respective flag:

        * ``auto_pre_cmds=False``  to skip the automatic addition of
          :py:attr:`self.pre_cmds <meta_package_manager.base.PackageManager.pre_cmds>`
        * ``auto_pre_args=False``  to skip the automatic addition of
          :py:attr:`self.pre_args <meta_package_manager.base.PackageManager.pre_args>`
        * ``auto_post_args=False`` to skip the automatic addition of
          :py:attr:`self.post_args <meta_package_manager.base.PackageManager.post_args>`

        Each global set of elements can be locally overridden with:

        * ``override_pre_cmds=tuple()``
        * ``override_cli_path=str``
        * ``override_pre_args=tuple()``
        * ``override_post_args=tuple()``

        On linux, the command can be run with `sudo <https://www.sudo.ws>`_ if the
        parameter of the same name is set to ``True``. In which case the
        ``override_pre_cmds`` parameter is not allowed to be set and the
        ``auto_pre_cmds`` parameter is forced to ``False``.
        """
        params: list[Arg | NestedArgs] = []

        # Sudo replaces any pre-command, be it overridden or automatic.
        if sudo:
            if current_os() not in UNIX:
                msg = "sudo only supported on UNIX."
                raise NotImplementedError(msg)
            if override_pre_cmds:
                msg = "Pre-commands not allowed if sudo is requested."
                raise ValueError(msg)
            if auto_pre_cmds:
                auto_pre_cmds = False
            params.append("sudo")
        elif override_pre_cmds:
            params.extend(override_pre_cmds)  # type: ignore[arg-type]
        elif auto_pre_cmds:
            params.extend(self.pre_cmds)

        if override_cli_path:
            params.append(override_cli_path)
        else:
            params.append(self.cli_path)

        if override_pre_args:
            params.extend(override_pre_args)  # type: ignore[arg-type]
        elif auto_pre_args:
            params.extend(self.pre_args)

        if args:
            params.extend(args)

        if override_post_args:
            params.extend(override_post_args)  # type: ignore[arg-type]
        elif auto_post_args:
            params.extend(self.post_args)

        return args_cleanup(params)  # type: ignore[arg-type]

    def run_cli(
        self,
        *args: Arg | NestedArgs,
        auto_extra_env: bool = True,
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_extra_env: EnvVars | None = None,
        override_pre_cmds: NestedArgs | None = None,
        override_cli_path: Path | None = None,
        override_pre_args: NestedArgs | None = None,
        override_post_args: NestedArgs | None = None,
        force_exec: bool = False,
        sudo: bool = False,
    ) -> str:
        """Build and run the package manager CLI by combining the custom ``*args`` with
        the package manager's global parameters.

        After the CLI is built with the
        :py:meth:`meta_package_manager.base.PackageManager.build_cli` method, it is
        executed with the :py:meth:`meta_package_manager.base.PackageManager.run`
        method, augmented with environment variables from :py:attr:`self.extra_env
        <meta_package_manager.base.PackageManager.extra_env>`.

        All parameters are the same as
        :py:meth:`meta_package_manager.base.PackageManager.build_cli`, plus:

        * ``auto_extra_env=False`` to skip the automatic addition of
          :py:attr:`self.extra_env <meta_package_manager.base.PackageManager.extra_env>`
        * ``override_extra_env=dict()`` to locally overrides the later
        * ``force_exec`` ignores the :option:`mpm --dry-run` and :option:`mpm
          --stop-on-error` options to force the execution and completion of the command.
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
            return self.run(*cli, extra_env=extra_env)

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

        Contrary to :py:class:`meta_package_manager.version.TokenizedString`, do no
        splits on colated number/alphabetic junctions.
        """
        return {p for p in re.split(r"\W+", query) if p}

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search packages available for install.

        There is no need for this method to be perfect and sensitive to ``extended`` and
        ``exact`` parameters. If the package manager is not supporting these kind of
        options out of the box, just returns the closest subset of matching package you
        can come up with. Finer refiltering will happens in the
        :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` method
        below.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def refiltered_search(
        self,
        query: str,
        extended: bool,
        exact: bool,
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

            # Rejects fuzzy results: only keep packages strictly matching on ID or name.
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

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package and one only.

        Allows a specific ``version`` to be provided.
        """
        raise NotImplementedError

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade all outdated packages on the system."""
        raise NotImplementedError

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade one package and one only.

        Allows a specific ``version`` to be provided.
        """
        raise NotImplementedError

    def upgrade(self, package_id: str | None = None, version: str | None = None) -> str:
        """Perform an upgrade of either all or one package.

        Executes the CLI provided by either
        :py:meth:`meta_package_manager.base.PackageManager.upgrade_all_cli` or
        :py:meth:`meta_package_manager.base.PackageManager.upgrade_one_cli`.

        If the manager doesn't provides a full upgrade one-liner (i.e. if
        :py:meth:`meta_package_manager.base.PackageManager.upgrade_all_cli` raises
        :py:exc:`NotImplementedError`), then the list of all outdated packages will be
        fetched (via :py:meth:`meta_package_manager.base.PackageManager.outdated`) and
        each package will be updated one by one by calling
        :py:meth:`meta_package_manager.base.PackageManager.upgrade_one_cli`.

        See for example the case of
        :py:meth:`meta_package_manager.managers.pip.Pip.upgrade_one_cli`.
        """
        if package_id:
            cli = self.upgrade_one_cli(package_id, version=version)

        else:
            try:
                cli = self.upgrade_all_cli()
            except NotImplementedError:
                logging.info(
                    "Fallback to calling upgrade operation on each outdated package.",
                )
                log = ""
                for package in self.outdated:
                    output = self.upgrade(package.id)
                    if output:
                        log += f"\n{output}"
                return log

        return self.run(cli, extra_env=self.extra_env)

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
        """Prune left-overs, remove orphaned dependencies and clear caches.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError
