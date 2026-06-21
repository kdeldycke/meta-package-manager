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
"""CLI-execution engine shared by every package manager.

Houses the machinery that locates a manager's binary on the system and runs it:
the :py:class:`meta_package_manager.execution.CLIExecutor` mixin (which
:py:class:`meta_package_manager.manager.PackageManager` inherits), the
:py:class:`meta_package_manager.execution.CLIError` exception, and the
:py:func:`meta_package_manager.execution.highlight_cli_name` helper.

.. note::
    The name and intent mirror :py:mod:`click_extra.execution` from the sibling
    `click-extra <https://github.com/kdeldycke/click-extra>`_ project, which gathers
    options that govern how a CLI runs (parallelism, timing, exit code). They house
    different kinds of things today, but keeping the name aligned anticipates reusing
    those click-extra execution options from here.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
from contextlib import nullcontext
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from textwrap import dedent, indent, shorten
from typing import ClassVar, Final, cast
from unittest.mock import patch

from boltons.iterutils import unique
from boltons.strutils import strip_ansi
from click_extra.envvar import env_copy
from click_extra.spinner import Spinner
from click_extra.testing import INDENT, args_cleanup, format_cli_prompt
from click_extra.theme import get_current_theme as theme
from extra_platforms import UNIX, current_platform, is_any_windows

from .version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from contextlib import AbstractContextManager
    from datetime import timedelta

    from click_extra._types import TArg, TEnvVars, TNestedArgs

    from .version import TokenizedString


class CLIError(Exception):
    """An error occurred when running package manager CLI."""

    def __init__(self, code: int | None, output: str, error: str) -> None:
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


def highlight_cli_name(path: Path | None, match_names: Iterable[str]) -> str | None:
    """Highlight the binary name in the provided ``path``.

    If ``match_names`` is provided, only highlight the start of the binary name that is
    in the list.

    Matching is insensitive to case on Windows and case-sensitive on other platforms,
    thanks to ``os.path.normcase``.
    """
    if path is None:
        return None

    highlighted_name = path.name
    for ref_name in match_names:
        if os.path.normcase(ref_name).startswith(os.path.normcase(path.name)):
            highlighted_name = (
                theme().invoked_command(path.name[: len(ref_name)])
                + path.name[len(ref_name) :]
            )
            break

    return f"{path.parent}{os.path.sep}{highlighted_name}"


READ_ONLY_TIMEOUT: Final = 120
"""Default timeout (seconds) for read-only probes and queries.

These operations only inspect state, so a short cap lets a wedged binary fail fast
instead of stalling the whole run. The value is generous enough for legitimately
slow scans (a freshly-pulled ``guix search`` walking every package's metadata)
while still being far below :py:data:`MUTATING_TIMEOUT`.
"""

MUTATING_TIMEOUT: Final = 500
"""Default timeout (seconds) for operations that change system state.

Installs, upgrades, removals, channel syncs and cleanups routinely build from
source, download large archives or pull entire channels, so they need a long cap.
Kept identical to the historical global default so these operations behave exactly
as before when no explicit ``--timeout`` is given.
"""

DEFAULT_TIMEOUT: Final = MUTATING_TIMEOUT
"""Fallback timeout (seconds) for a CLI call whose operation is unknown.

Defaults to the conservative :py:data:`MUTATING_TIMEOUT`: when in doubt, wait
rather than risk killing a legitimate long-running command.
"""

OPERATION_TIMEOUTS: Final[dict[str, int]] = {
    "version": READ_ONLY_TIMEOUT,
    "installed": READ_ONLY_TIMEOUT,
    "outdated": READ_ONLY_TIMEOUT,
    "search": READ_ONLY_TIMEOUT,
    "install": MUTATING_TIMEOUT,
    "upgrade": MUTATING_TIMEOUT,
    "upgrade_all": MUTATING_TIMEOUT,
    "remove": MUTATING_TIMEOUT,
    "sync": MUTATING_TIMEOUT,
    "cleanup": MUTATING_TIMEOUT,
}
"""Per-operation timeout defaults, applied only when the user has set no explicit
``--timeout`` (or per-manager ``timeout`` override).

Keyed by the :py:class:`meta_package_manager.capabilities.Operations` member name,
plus the special ``"version"`` detection probe. The keys are validated against the
``Operations`` enum by the test suite so the two never drift apart. An operation
absent from this map resolves to :py:data:`DEFAULT_TIMEOUT`.
"""

SPINNER_DELAY: Final = 0.1
"""Seconds a CLI call must run before its progress spinner appears.

Kept short so the spinner surfaces almost immediately on any call that is not
instant: prompt feedback makes ``mpm`` feel responsive from the start rather than
stalled during the first second. Only the quickest calls (cached version probes,
trivial metadata queries) finish within this delay and stay silent; anything
slower (a ``guix search``, a source build) shows the spinner right away.
"""


class CLIExecutor:
    """Locate a manager's CLI on the system and run it.

    Mixin inherited by :py:class:`meta_package_manager.manager.PackageManager`. Owns the
    CLI-invocation configuration (names, search paths, environment, arguments, timeout)
    and the engine that searches for the binary, executes it, captures and normalizes its
    output, accumulates errors, and parses its self-reported version.
    """

    cli_names: tuple[str, ...]
    """List of CLI names the package manager is known as.

    This list of recognized CLI names is ordered by priority. That way we can influence
    the search of the right binary.

    ..hint::
        This was helpful in the case of the Python transition from 2.x to 3.x, where
        multiple versions of the same executable were named ``python`` or ``python3``.

    By default, this property's value is derived from the manager's ID (see the
    ``MetaPackageManager.__init__`` method above).
    """

    cli_search_path: tuple[str, ...] = ()
    """List of additional path to help :program:`mpm` hunt down the package manager CLI.

    Must be a list of strings whose order dictates the search sequence.

    Most of the time unnecessary:
    :py:func:`meta_package_manager.manager.PackageManager.cli_path` works well on all
    platforms.
    """

    extra_env: ClassVar[TEnvVars | None] = None
    """Additional environment variables to add to the current context.

    Automatically applied on each
    :py:func:`meta_package_manager.manager.PackageManager.run_cli` calls.
    """

    pre_cmds: tuple[str, ...] = ()
    """Global list of pre-commands to add before before invoked CLI.

    Automatically added to each
    :py:func:`meta_package_manager.manager.PackageManager.run_cli` call.

    Used to prepend `sudo <https://www.sudo.ws>`_ or other system utilities.
    """

    pre_args: tuple[str, ...] = ()
    post_args: tuple[str, ...] = ()
    """Global list of options used before and after the invoked package manager CLI.

    Automatically added to each
    :py:func:`meta_package_manager.manager.PackageManager.run_cli` call.

    Essentially used to force silencing, low verbosity or no-color output.
    """

    version_cli_options: tuple[str, ...] = ("--version",)
    """CLI options used to produce the version of the package manager.

    The raw output produced by the package manager CLI will be parsed with the
    :py:attr:`version_regexes <meta_package_manager.manager.PackageManager.version_regexes>`
    below to extract the version number.
    """

    version_regexes: tuple[str, ...] = (r"(?P<version>\S+)",)
    """Regular expressions used to extract the version number.

    This property must be a tuple of strings, each of which is a valid regular
    expression that must contain a `group
    <https://docs.python.org/3/library/re.html#index-18>`_ named ``<version>``.

    The first of these regexes producing a match and returning non-empty ``<version>``
    group will be used as the version string of the package manager.

    That version string will then be sanitized and normalized by
    :py:func:`meta_package_manager.manager.PackageManager.version`.

    By default match the first part that is space-separated.

    .. caution::
        These regexes are compiled with :py:data:`re.MULTILINE` only. They are
        *not* compiled with :py:data:`re.VERBOSE`, so literal whitespace in the
        pattern is significant and matches whitespace in the CLI output.
    """

    stop_on_error: bool = False
    """Tell the manager to either raise or continue on errors."""

    dry_run: bool = False
    """Do not actually perform any action, just simulate CLI calls."""

    timeout: int | None = None
    """Maximum number of seconds to wait for a CLI call to complete.

    ``None`` means the user expressed no explicit preference: the effective cap is
    then resolved per-operation by ``_resolve_timeout()`` from
    :py:data:`OPERATION_TIMEOUTS`. A non-``None`` value (the ``--timeout`` flag or a
    per-manager override) wins for every operation.
    """

    _active_operation: str | None = None
    """Name of the operation this manager is currently performing.

    Stamped by :py:meth:`meta_package_manager.pool.ManagerPool._select_managers`
    just before the manager is handed to a subcommand, and by the :py:attr:`version`
    probe. Consumed by :py:meth:`_resolve_timeout` to pick a per-operation default.
    ``None`` (no known operation) falls back to :py:data:`DEFAULT_TIMEOUT`.
    """

    progress: bool = False
    """Whether CLI calls may show a progress spinner while they block.

    Set by the CLI to an interactive, human-facing run only (a TTY, no serialized
    output, not at DEBUG verbosity). Even when ``True`` the spinner still
    self-suppresses off a TTY: see ``_make_spinner()``. Defaults to ``False`` so
    programmatic use stays silent.
    """

    cooldown: timedelta | None = None
    """Minimum age a release must have before it can be installed or upgraded.

    When set, the manager refuses to bring in any package version published more
    recently than ``cooldown`` ago. This is a mitigation against supply-chain
    attacks: a malicious release is typically detected and pulled within days of
    publication, so a waiting period keeps freshly-published (and potentially
    compromised) versions out of the system. ``None`` disables the gate.

    Only managers able to natively enforce a release-age limit honor this; see
    :py:attr:`cooldown_env_var` and :py:attr:`supports_cooldown`.
    """

    require_cooldown_support: bool = True
    """Require native :py:attr:`cooldown` support to run install/upgrade.

    By default (``True``, fail-closed), when a :py:attr:`cooldown` is requested,
    install and upgrade operations are skipped for managers lacking native
    release-age support, so nothing slips in unguarded. Setting this to ``False``
    opts into running those operations anyway, without the safeguard.
    """

    cooldown_env_var: ClassVar[str | None] = None
    """Environment variable this manager reads to honor a :py:attr:`cooldown`.

    ``None`` (the default) means the manager has no native release-age mechanism and
    cannot honor a cooldown. A subclass that sets this string advertises support (see
    :py:attr:`supports_cooldown`); the value produced by :py:meth:`cooldown_env_value`
    is then injected into the environment of every CLI call.
    """

    windows_creation_flags: int = 0
    """Additional Windows process creation flags OR-ed with ``CREATE_NO_WINDOW``.

    Use this on individual managers to control how their subprocess is attached
    to the calling process's console. For example, setting this to
    ``subprocess.DETACHED_PROCESS`` (``0x8``) fully detaches the child from the
    parent's console. Any grandchild process (like a COM server or installer EXE)
    that calls ``GenerateConsoleCtrlEvent(0)`` on exit will then fail silently
    because there is no console to broadcast to.

    No-op on non-Windows platforms (``getattr`` returns ``0`` for Windows-only flags).
    """

    windows_processes_to_cleanup: tuple[str, ...] = ()
    """Windows process image names to forcibly terminate after each CLI call.

    When a package manager spawns grandchild processes that outlive the direct
    subprocess (like winget's ``WindowsPackageManagerServer.exe`` COM server),
    those orphans can linger and consume resources. List the image names here so
    they are killed after ``communicate()`` returns.

    No-op on non-Windows platforms.
    """

    cli_errors: list[CLIError]
    """Accumulate all CLI errors encountered by the package manager."""

    def __init__(self) -> None:
        """Initialize ``cli_errors`` list."""
        self.cli_errors = []

    @property
    def supports_cooldown(self) -> bool:
        """Whether this manager can natively enforce a release-age :py:attr:`cooldown`."""
        return self.cooldown_env_var is not None

    def cooldown_env_value(self) -> str:
        """Render :py:attr:`cooldown` as the value of :py:attr:`cooldown_env_var`.

        Defaults to the RFC 3339 timestamp of the most recent release date still
        allowed, i.e. now minus the cooldown. Managers whose environment variable
        expects another format (a number of minutes, a bare day count, ...) override
        this.
        """
        assert self.cooldown is not None
        cutoff = datetime.now(tz=timezone.utc) - self.cooldown
        return cutoff.isoformat()

    def cooldown_env(self) -> TEnvVars:
        """Environment fragment enforcing the :py:attr:`cooldown`, empty when inactive.

        Returns an empty mapping unless a :py:attr:`cooldown` is set *and* the manager
        supports it. Merged into the environment of every :py:meth:`run` call.
        """
        if self.cooldown is None or self.cooldown_env_var is None:
            return {}
        return {self.cooldown_env_var: self.cooldown_env_value()}

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
            <meta_package_manager.manager.PackageManager.cli_search_path>`,
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
        # Code below is inspired by the original implementation of ``shutil.which()``:
        # https://github.com/python/cpython/blob/8d46c7e/Lib/shutil.py#L1478-L1491
        if is_any_windows():
            win_pathext = shutil._WIN_DEFAULT_PATHEXT  # type: ignore[attr-defined]
            pathext_source = os.getenv("PATHEXT") or win_pathext
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
            (Path(p) for p in (*self.cli_search_path, *os.get_exec_path(env=env))),
            key=normalize_path,
        )

        logging.debug(
            "Search for "
            + ", ".join(theme().invoked_command(cli) for cli in search_filenames)
            + " in:\n"
            + "\n".join(str(p) for p in search_path_list)
        )

        for search_path in search_path_list:
            if not search_path.is_dir():
                continue

            for filename in search_filenames:
                file = search_path / filename
                # On Windows, check for reparse points (e.g., Windows App Execution Aliases like winget).
                # These return False for is_file() and 0 for getsize(), so we detect them separately.
                if is_any_windows():
                    try:
                        file_stat = file.lstat()
                        if (
                            file_stat.st_file_attributes
                            & stat.FILE_ATTRIBUTE_REPARSE_POINT
                        ):
                            logging.debug(
                                f"CLI found at {highlight_cli_name(file, cli_names)} (reparse point)"
                            )
                            yield file
                            continue
                    except OSError:
                        # Permission denied or file doesn't exist; fall through to normal checks.
                        pass
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
        <meta_package_manager.manager.PackageManager.cli_names>`, in each system path
        provided by :py:attr:`cli_search_path
        <meta_package_manager.manager.PackageManager.cli_search_path>`. In that order.
        Then returns the first match.

        Executability of the CLI will be separately assessed later by the
        :py:func:`meta_package_manager.manager.PackageManager.executable` method below.
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

        Skipped on platforms where the manager is not supported, even if
        :py:attr:`cli_path` resolved to an executable: that binary almost
        certainly belongs to a different tool that happens to share the
        same name (e.g. GNU ``make`` on macOS getting matched by the
        FreeBSD ``ports`` manager), so probing it would either misreport
        the version or surface confusing error output.
        """
        # ``supported`` is declared on the ``PackageManager`` subclass, not on
        # this mixin: mypy does not see it, but every concrete instance does.
        if not self.supported:  # type: ignore[attr-defined]
            return None
        if self.executable:
            # Version detection is a fast liveness probe, so tag it as a read-only
            # operation: a wedged binary then trips the short timeout instead of the
            # long mutating one. Safe to leave set: ``_select_managers`` re-stamps the
            # real operation before any subcommand runs, and an explicit ``--timeout``
            # still wins inside ``_resolve_timeout``.
            self._active_operation = "version"
            output = self.run_cli(
                self.version_cli_options,
                auto_pre_cmds=False,
                auto_pre_args=False,
                auto_post_args=False,
                force_exec=True,
            )

            # Try each regex to extract the version.
            for regex in self.version_regexes:
                logging.debug(f"Use {regex!r} to extracting version.")
                parts = re.compile(regex, re.MULTILINE).search(output)
                if parts:
                    version_string = parts.groupdict().get("version")
                    logging.debug(f"Extracted version: {version_string!r}")
                    if version_string:
                        parsed_version = parse_version(version_string)
                        logging.debug(f"Parsed version: {parsed_version!r}")
                        if parsed_version:
                            return parsed_version
        return None

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

    def _resolve_timeout(self) -> int:
        """Resolve the timeout (in seconds) for the current CLI call.

        Precedence, most specific first:

        1. An explicit :py:attr:`timeout` (the user's ``--timeout`` flag or a
           per-manager ``timeout`` override) wins for every operation.
        2. Otherwise the per-operation default keyed on :py:attr:`_active_operation`
           (see :py:data:`OPERATION_TIMEOUTS`).
        3. An unknown operation falls back to :py:data:`DEFAULT_TIMEOUT`.
        """
        if self.timeout is not None:
            return self.timeout
        if self._active_operation is None:
            return DEFAULT_TIMEOUT
        return OPERATION_TIMEOUTS.get(self._active_operation, DEFAULT_TIMEOUT)

    def _make_spinner(self) -> Spinner:
        """Build a (not-yet-started) progress spinner for the current CLI call.

        The label combines the manager ID and the active operation, so a slow call
        reads like the command it runs (``guix search``, ``brew install``). The
        spinner is disabled unless :py:attr:`progress` is set; even then it only
        animates on a TTY (see :py:class:`click_extra.Spinner`), so it stays silent
        when output is piped or captured.
        """
        manager_id = self.id  # type: ignore[attr-defined]
        operation = self._active_operation
        label = f"{manager_id} {operation}" if operation else str(manager_id)
        # Append the elapsed time so a long call (a slow ``guix search``) reads as
        # "⠙ guix search (12.3s)" rather than looking stuck.
        return Spinner(
            label,
            delay=SPINNER_DELAY,
            enabled=None if self.progress else False,
            timer=True,
        )

    def run(
        self,
        *args: TArg | TNestedArgs,
        extra_env: TEnvVars | None = None,
        must_succeed: bool = False,
    ) -> str:
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

        :param must_succeed: if ``True``, raise
            :py:class:`meta_package_manager.manager.CLIError` on non-zero exit code
            regardless of :py:attr:`stop_on_error`. Use for calls whose output is
            parsed (JSON, XML, regex) and where a silent failure would be
            indistinguishable from empty results. Unlike ``stop_on_error`` (a
            user-facing preference for cross-manager resilience), ``must_succeed``
            is a developer assertion that the invocation itself is correct.
        """
        # Casting to string helps serialize Path and Version objects.
        clean_args = args_cleanup(*args)
        # Enforce the release-age cooldown by injecting the manager's dedicated
        # environment variable into every call (harmless for operations that ignore
        # it, like removal or cache cleanup).
        cooldown_env = self.cooldown_env()
        if cooldown_env:
            extra_env = {**(extra_env or {}), **cooldown_env}
        cli_msg = format_cli_prompt(clean_args, extra_env)

        code = 0
        output = ""
        error = ""

        if self.dry_run:
            logging.warning(f"Dry-run: {cli_msg}")
        else:
            logging.debug(cli_msg)
            # On Windows, CREATE_NO_WINDOW suppresses any console window the
            # child might open, while still capturing stdout/stderr via the
            # explicit PIPE handles.
            # stdin=DEVNULL prevents child processes from blocking on stdin reads.
            # SW_HIDE is a belt-and-suspenders suppression of console windows.
            # STARTUPINFO must be created per call because subprocess overwrites
            # its hStd* fields.
            # On POSIX, both creationflags=0 and startupinfo=None are no-ops.
            _si = getattr(subprocess, "STARTUPINFO", None)
            if _si is not None:
                _si = _si()
                _si.dwFlags = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
                _si.wShowWindow = 0  # SW_HIDE
            try:
                proc = subprocess.Popen(
                    clean_args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    errors="replace",
                    env=cast("subprocess._ENV", env_copy(extra_env)),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | self.windows_creation_flags,
                    startupinfo=_si,
                )
            except OSError as ex:
                winerror = getattr(ex, "winerror", None)
                # Windows shims trigger WinError 193 when spawned as a subprocess.
                if winerror == 193:
                    logging.debug(
                        f"{highlight_cli_name(self.cli_path, self.cli_names)} "
                        "is not a valid Windows application.",
                    )
                    self.executable = False
                    return ""
                # The binary disappeared between the availability check and
                # execution (e.g. only a .bat wrapper found on Windows while
                # the underlying binary is absent).
                if isinstance(ex, FileNotFoundError):
                    logging.debug(
                        f"{highlight_cli_name(self.cli_path, self.cli_names)} "
                        "executable not found.",
                    )
                    self.executable = False
                    return ""
                raise
            logging.debug(f"Spawned PID {proc.pid}: {clean_args[0]}.")
            effective_timeout = self._resolve_timeout()
            spinner = self._make_spinner()
            spinner.start()
            try:
                logging.debug(
                    f"Waiting for PID {proc.pid} (timeout={effective_timeout}s).",
                )
                stdout, stderr = proc.communicate(timeout=effective_timeout)
                logging.debug(
                    f"PID {proc.pid} exited {proc.returncode}; "
                    f"stdout {len(stdout)} chars, stderr {len(stderr)} chars."
                )
                if is_any_windows():
                    for proc_name in self.windows_processes_to_cleanup:
                        subprocess.run(
                            ("taskkill", "/F", "/T", "/IM", proc_name),
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
            except subprocess.TimeoutExpired:
                # Erase the spinner before the timeout warning is logged.
                spinner.stop()
                logging.debug(f"PID {proc.pid} timed out; sending kill.")
                if is_any_windows():
                    # Grandchild processes (e.g. installer EXEs spawned by
                    # winget's COM server) inherit the pipe write handles and
                    # keep them open after proc.kill(), which would cause
                    # communicate() to block until every grandchild exits.
                    # taskkill /F /T kills the entire process tree, closing
                    # all inherited handles so communicate() returns promptly.
                    subprocess.run(
                        ("taskkill", "/F", "/T", "/PID", str(proc.pid)),
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    for proc_name in self.windows_processes_to_cleanup:
                        subprocess.run(
                            ("taskkill", "/F", "/T", "/IM", proc_name),
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                proc.kill()
                stdout, stderr = proc.communicate()
                logging.debug(f"PID {proc.pid} killed; exit {proc.returncode}.")
                msg = f"Timed out after {effective_timeout}s."
                logging.warning(msg)
                exception = CLIError(None, "", msg)
                if must_succeed or self.stop_on_error:
                    raise exception
                self.cli_errors.append(exception)
                return ""
            except KeyboardInterrupt:
                # Erase the spinner before the interrupt warning is logged.
                spinner.stop()
                logging.debug(f"PID {proc.pid} interrupted; sending kill.")
                proc.kill()
                proc.communicate()
                msg = "Subprocess interrupted by a console signal."
                logging.warning(msg)
                exception = CLIError(None, "", msg)
                self.cli_errors.append(exception)
                return ""
            finally:
                # Safety net: stop on the success path and on any other exit.
                spinner.stop()
            code = proc.returncode
            output = stdout or ""
            error = stderr or ""

        # Normalize messages.
        if error:
            error = dedent(strip_ansi(error).strip())
        if output:
            output = dedent(strip_ansi(output).strip())

        # Log <stdout> and <stderr> output.
        #
        # Both streams capture the raw output of an external CLI, not mpm's
        # own messages, so they go to DEBUG: callers running ``mpm outdated``
        # do not want gem extension warnings, mas Spotlight chatter or yarn's
        # missing-node error flooding the table they came to see. Failures
        # still propagate either as a raised :py:class:`CLIError` (when
        # ``must_succeed`` or ``stop_on_error`` is set) or via
        # :py:attr:`cli_errors` for end-of-run summaries.
        if output:
            logging.debug(indent(output, INDENT))
        if error:
            logging.debug(indent(error, INDENT))

        # Non-successful run.
        if code and error:
            # Produce an exception and eventually raise it.
            exception = CLIError(code, output, error)
            if must_succeed or self.stop_on_error:
                raise exception
            # Accumulate errors.
            self.cli_errors.append(exception)

        return output

    def build_cli(
        self,
        *args: TArg | TNestedArgs,
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_pre_cmds: TNestedArgs | None = None,
        override_cli_path: Path | None = None,
        override_pre_args: TNestedArgs | None = None,
        override_post_args: TNestedArgs | None = None,
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

        * :py:attr:`self.pre_cmds <meta_package_manager.manager.PackageManager.pre_cmds>`
          is added before the CLI path.

        * :py:attr:`self.cli_path <meta_package_manager.manager.PackageManager.cli_path>`
          is used as the main binary to execute.

        * :py:attr:`self.pre_args <meta_package_manager.manager.PackageManager.pre_args>`
          and :py:attr:`self.post_args
          <meta_package_manager.manager.PackageManager.post_args>`  globals are added
          before and after the provided ``*args``.

        Each additional set of elements can be disabled with their respective flag:

        * ``auto_pre_cmds=False``  to skip the automatic addition of
          :py:attr:`self.pre_cmds <meta_package_manager.manager.PackageManager.pre_cmds>`
        * ``auto_pre_args=False``  to skip the automatic addition of
          :py:attr:`self.pre_args <meta_package_manager.manager.PackageManager.pre_args>`
        * ``auto_post_args=False`` to skip the automatic addition of
          :py:attr:`self.post_args <meta_package_manager.manager.PackageManager.post_args>`

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
        # Apply delegation overrides if set by a DelegatedMethod descriptor.
        delegate_path = getattr(self, "_delegate_cli_path", None)
        if delegate_path is not None:
            override_cli_path = override_cli_path or delegate_path
            auto_post_args = False

        params: list[TArg | TNestedArgs] = []

        # Sudo replaces any pre-command, be it overridden or automatic.
        if sudo:
            if current_platform() not in UNIX:
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
        *args: TArg | TNestedArgs,
        auto_extra_env: bool = True,
        auto_pre_cmds: bool = True,
        auto_pre_args: bool = True,
        auto_post_args: bool = True,
        override_extra_env: TEnvVars | None = None,
        override_pre_cmds: TNestedArgs | None = None,
        override_cli_path: Path | None = None,
        override_pre_args: TNestedArgs | None = None,
        override_post_args: TNestedArgs | None = None,
        force_exec: bool = False,
        must_succeed: bool = False,
        sudo: bool = False,
    ) -> str:
        """Build and run the package manager CLI by combining the custom ``*args`` with
        the package manager's global parameters.

        After the CLI is built with the
        :py:meth:`meta_package_manager.manager.PackageManager.build_cli` method, it is
        executed with the :py:meth:`meta_package_manager.manager.PackageManager.run`
        method, augmented with environment variables from :py:attr:`self.extra_env
        <meta_package_manager.manager.PackageManager.extra_env>`.

        All parameters are the same as
        :py:meth:`meta_package_manager.manager.PackageManager.build_cli`, plus:

        * ``auto_extra_env=False`` to skip the automatic addition of
          :py:attr:`self.extra_env <meta_package_manager.manager.PackageManager.extra_env>`
        * ``override_extra_env=dict()`` to locally overrides the later
        * ``force_exec`` ignores the :option:`mpm --dry-run` and :option:`mpm
          --stop-on-error` options to force the execution and completion of the command.
        * ``must_succeed`` raises on non-zero exit regardless of
          :option:`mpm --stop-on-error`. See :py:meth:`run` for details.
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
        local_option1: AbstractContextManager = nullcontext()
        local_option2: AbstractContextManager = nullcontext()
        # Temporarily replace --dry-run and --stop-on-error user options with our own.
        if force_exec:
            local_option1 = patch.object(self, "dry_run", False)
            local_option2 = patch.object(self, "stop_on_error", False)
        # Execute the command with eventual local options.
        with local_option1, local_option2:
            return self.run(*cli, extra_env=extra_env, must_succeed=must_succeed)
