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

Two altitudes live here. The lower one runs *one* manager's CLI in one subprocess:
the :py:class:`meta_package_manager.execution.CLIExecutor` mixin (which
:py:class:`meta_package_manager.manager.PackageManager` inherits) locates the binary
and runs it, the :py:class:`meta_package_manager.execution.CLIError` exception carries
a failed call's result, and :py:func:`meta_package_manager.execution.highlight_cli_name`
themes a binary's name.

The higher one schedules *many* managers at once: the concurrent fan-out primitives
:py:func:`meta_package_manager.execution.collect_from_managers` and
:py:func:`meta_package_manager.execution.collect_per_package`, the
:py:func:`meta_package_manager.execution.effective_jobs` policy that sizes them, the
up-front :py:func:`meta_package_manager.execution.warm_availability` probe, and the
shared ``✓``/``✗`` ledger (:py:class:`meta_package_manager.execution.OperationTrail`
and the :py:func:`meta_package_manager.execution.trail_line` atom) that the concurrent
and sequential paths both report through.

Cutting across both altitudes,
:py:func:`meta_package_manager.execution.install_interrupt_handler` and
:py:func:`meta_package_manager.execution.terminate_live_processes` make Ctrl+C abort a
concurrent fan-out cleanly, by killing the in-flight subprocesses whose worker threads
would otherwise keep the thread pool (and the interpreter) from shutting down; and
:py:func:`meta_package_manager.execution.prime_sudo` authenticates ``sudo`` once up front
so a privilege-escalation password prompt never stalls the run from inside that fan-out.

.. note::
    The name and intent mirror :py:mod:`click_extra.execution` from the sibling
    `click-extra <https://github.com/kdeldycke/click-extra>`_ project, which gathers
    options that govern how a CLI runs (parallelism, timing, exit code). Co-locating
    the cross-manager scheduling here realizes that alignment: :option:`mpm --jobs`
    and the fan-out it drives now sit beside the per-call timeout and spinner they
    build upon.
"""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from textwrap import dedent, indent, shorten
from typing import ClassVar, Final, cast
from unittest.mock import patch

from boltons.iterutils import unique
from boltons.strutils import strip_ansi
from click.core import ParameterSource
from click_extra import echo, get_current_context
from click_extra.context import JOBS
from click_extra.envvar import env_copy
from click_extra.execution import resolve_jobs, run_jobs, run_lanes
from click_extra.spinner import Spinner
from click_extra.testing import INDENT, args_cleanup, format_cli_prompt
from click_extra.theme import KO_GLYPH, OK_GLYPH, get_current_theme as theme
from extra_platforms import UNIX, current_platform, is_any_windows

from .version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from contextlib import AbstractContextManager
    from datetime import timedelta
    from types import FrameType, TracebackType

    from click import Context
    from click_extra.envvar import TEnvVars
    from click_extra.testing import TArg, TNestedArgs
    from typing_extensions import Self

    from .manager import PackageManager
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


# Interrupt handling for concurrent fan-outs.
#
# Python delivers Ctrl+C (SIGINT/KeyboardInterrupt) only to the main thread, but a
# concurrent command (``mpm upgrade``, ``install``, ...) runs each manager's CLI in a
# worker thread of a ``ThreadPoolExecutor`` (see ``click_extra.execution.run_lanes``).
# The workers never see the interrupt; what actually stops their subprocesses is the
# terminal, which sends SIGINT to the whole foreground process group, mpm's children
# included. Any child that survives that signal (a ``sudo`` reading its password from
# ``/dev/tty``, a manager mid-transaction) keeps its worker blocked in
# ``communicate()``, so the pool cannot be joined: the abort then hangs, first in the
# executor's ``shutdown(wait=True)`` teardown and again in the interpreter's atexit
# thread-join. That double block is why a second Ctrl+C was needed and why it surfaced
# an "Exception ignored on threading shutdown" traceback.
#
# The fix: track every live subprocess and, on the first Ctrl+C, terminate them from
# the main thread's signal handler so the workers unblock and the pool drains cleanly.


_LIVE_PROCESSES: Final[set[subprocess.Popen[str]]] = set()
"""Registry of package-manager subprocesses currently running.

Populated by :py:meth:`CLIExecutor.run` for the lifetime of each ``communicate()``
call (added right after spawn, discarded in its ``finally``). Read by
:py:func:`terminate_live_processes` to interrupt them all at once. Guarded by
:py:data:`_LIVE_PROCESSES_LOCK`, since the fan-out runs :py:meth:`CLIExecutor.run` from
several worker threads concurrently.
"""


_LIVE_PROCESSES_LOCK: Final = threading.Lock()
"""Guards :py:data:`_LIVE_PROCESSES` against concurrent mutation by worker threads."""


def terminate_live_processes() -> None:
    """Send ``SIGTERM`` to every package-manager subprocess currently running.

    Called from the main thread's ``SIGINT`` handler (see
    :py:func:`install_interrupt_handler`) so a concurrent fan-out aborts promptly:
    terminating the children unblocks the worker threads parked in
    :py:meth:`subprocess.Popen.communicate`, letting the thread pool drain instead of
    hanging on a child that ignored the terminal's process-group ``SIGINT``.

    Uses ``SIGTERM`` rather than ``SIGKILL`` so a child still gets to clean up, notably
    to restore terminal state a ``sudo`` password prompt may have altered. The registry
    is snapshotted under the lock, then signalled outside it, because :py:meth:`run` may
    be discarding its own entries from other threads at the same time.
    """
    with _LIVE_PROCESSES_LOCK:
        live = tuple(_LIVE_PROCESSES)
    for proc in live:
        try:
            proc.terminate()
        except OSError:
            # Reaped between the snapshot and the signal: nothing left to stop.
            pass


def install_interrupt_handler(ctx: Context) -> None:
    """Make the first Ctrl+C terminate in-flight subprocesses, then abort as usual.

    Installs a ``SIGINT`` handler for the duration of the CLI run that calls
    :py:func:`terminate_live_processes` before re-raising :py:class:`KeyboardInterrupt`
    (exactly what Python's default handler raises). The abort then proceeds normally,
    but the concurrent fan-out no longer hangs on surviving children. The previous
    handler is restored when ``ctx`` closes.

    Must run in the main thread: :py:func:`signal.signal` refuses to install a handler
    from any other, so a non-main-thread caller (embedded use, some tests) is a no-op
    that keeps the default Ctrl+C behavior.

    A signal handler is required here rather than a ``try``/``except KeyboardInterrupt``
    around the fan-out: the interrupt unwinds through the executor's blocking
    ``shutdown(wait=True)`` teardown *before* any ``except`` in mpm could run, so the
    children must be killed at signal-delivery time, ahead of that teardown.
    """
    if threading.current_thread() is not threading.main_thread():
        return

    def handler(signum: int, frame: FrameType | None) -> None:
        terminate_live_processes()
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, handler)
    ctx.call_on_close(lambda: signal.signal(signal.SIGINT, previous))


# Up-front sudo priming for a mutating fan-out.
#
# A concurrent state-changing command mutes per-manager output and feeds each child
# ``stdin=/dev/null``, so a ``sudo`` password prompt raised mid-run — by mpm's own
# ``sudo -n`` or by a manager that escalates internally (Homebrew ``cask``) — lands
# invisibly on ``/dev/tty`` and can stall the run up to the mutating timeout. Priming
# authenticates once, up front, in one clearly-labeled prompt, then keeps the credential
# warm; every later escalation on the same terminal then spends the cache silently.


_SUDO_KEEPALIVE_INTERVAL: Final = 60
"""Seconds between ``sudo -n -v`` credential-cache refreshes during a run.

Comfortably under sudo's default ``timestamp_timeout`` (5 minutes), so the cache warmed
by :py:func:`prime_sudo` stays valid for the whole command. A host configured with a
shorter ``timestamp_timeout`` may still see a mid-run escalation re-prompt or fail.
"""

_SUDO_PRIMED: Final = "mpm_sudo_primed"
"""``ctx.meta`` key marking that :py:func:`prime_sudo` already ran this invocation."""

_SUDO_ESCALATION_PREFIX: Final = ("sudo", "-n")
"""Argv prefix mpm prepends to escalate a manager command non-interactively.

:py:meth:`CLIExecutor.build_cli` emits it and :py:meth:`CLIExecutor.run` matches it
byte-for-byte to turn a ``sudo -n`` authentication failure into an actionable hint, so
the two sites must stay in lockstep.
"""


def _resolved_sudo(manager: CLIExecutor) -> bool:
    """Whether ``manager`` escalates: its :py:attr:`~CLIExecutor.sudo` override if set,
    else its built-in :py:attr:`~CLIExecutor.default_sudo`."""
    return manager.sudo if manager.sudo is not None else manager.default_sudo


def _is_sudo_auth_failure(error: str) -> bool:
    """Whether ``error`` is ``sudo`` refusing to authenticate non-interactively.

    ``sudo -n`` writes one of these to ``<stderr>`` when it has no cached credentials
    and cannot prompt for a password (nothing cached, no controlling terminal, no
    askpass helper). Lets :py:meth:`CLIExecutor.run` turn an opaque escalation failure
    into an actionable hint.
    """
    lowered = error.lower()
    return "sudo:" in lowered and any(
        marker in lowered
        for marker in (
            "a password is required",
            "a terminal is required",
            "no tty present",
            "askpass",
        )
    )


def prime_sudo(ctx: Context, managers: Iterable[PackageManager]) -> None:
    """Authenticate ``sudo`` once, up front, for a mutating fan-out that will escalate.

    Validates the ``sudo`` credential on mpm's controlling terminal in a single
    clearly-labeled foreground prompt, then keeps it warm with a background refresh, so
    every later escalation on the same terminal — mpm's own ``sudo -n`` *and* a manager's
    internal ``sudo`` (Homebrew ``cask``) — spends the cache instead of blocking on an
    invisible prompt inside the concurrent fan-out.

    Call at the top of each mutating subcommand, before the fan-out draws its spinner.
    Returns without prompting (leaving escalations to fail fast through their own
    ``sudo -n``) when there is nothing to prime:

    - Windows (no ``sudo``) or the process is already root,
    - no selected manager escalates (:py:func:`_resolved_sudo`),
    - a dry run (no real CLI is executed),
    - already primed once this invocation (idempotent), or
    - no interactive terminal to prompt on: one warning is logged and the escalating
      managers are left to fail fast rather than block on a prompt no one can answer.
    """
    managers = list(managers)
    if is_any_windows() or getattr(os, "geteuid", lambda: 1)() == 0:
        return
    if not any(_resolved_sudo(manager) for manager in managers):
        return
    if any(manager.dry_run for manager in managers):
        return
    if ctx.meta.get(_SUDO_PRIMED):
        return
    ctx.meta[_SUDO_PRIMED] = True

    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        logging.warning(
            "Some managers need administrator rights, but no terminal is available to "
            "prompt for a password: they may fail. Re-run in a terminal, pre-authenticate "
            "with `sudo -v`, or drop them with --no-sudo.",
        )
        return

    echo(
        "Some managers need administrator rights: enter your password if prompted.",
        err=True,
    )
    if subprocess.run(("sudo", "-v"), check=False).returncode != 0:
        logging.warning(
            "Could not acquire sudo credentials: managers needing root may fail.",
        )
        return

    # Keep the credential fresh for the whole run so a long fan-out does not outlast
    # sudo's timestamp and re-prompt mid-flight. Output is captured so a failed refresh
    # cannot smear the aggregate spinner drawing on stderr. The daemon thread is stopped
    # when the context closes (normal exit or Ctrl+C both run close callbacks).
    stop = threading.Event()

    def keepalive() -> None:
        while not stop.wait(_SUDO_KEEPALIVE_INTERVAL):
            subprocess.run(("sudo", "-n", "-v"), capture_output=True, check=False)

    threading.Thread(target=keepalive, daemon=True).start()
    ctx.call_on_close(stop.set)


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

    sudo: bool | None = None
    """User escalation policy: run this manager's privileged commands with ``sudo``.

    ``None`` (the default) means the user expressed no preference, so the built-in
    :py:attr:`default_sudo` decides. ``True``/``False`` force escalation on or off for
    every operation this manager marks privileged (a ``build_cli(..., sudo=True)`` call).
    Set globally by :option:`mpm --sudo` / :option:`mpm --no-sudo` and per manager by the
    ``[mpm.managers.<id>] sudo`` config key, the latter winning (see
    :py:meth:`meta_package_manager.pool.ManagerPool._select_managers`).

    Only privileged operations on UNIX are ever escalated. A manager that escalates
    *internally* (Homebrew ``cask``) has no such markers and is never wrapped in ``sudo``
    by ``mpm``: its own ``sudo`` is instead served by the credential cache warmed by
    :py:func:`prime_sudo`.
    """

    default_sudo: bool = False
    """Built-in escalation default, used when :py:attr:`sudo` is ``None``.

    ``False`` on the base: most managers install into user-writable trees and never need
    root. The system package managers whose privileged operations require root (``apt``,
    ``dnf``, ``pacman``, ``zypper``, ...) set this to ``True`` so their
    ``build_cli(..., sudo=True)`` operations escalate out of the box, while staying
    switchable off through :py:attr:`sudo` (``--no-sudo`` or config) for rootless setups.
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

    run_cache: dict[tuple, tuple[int, str, str]] | None = None
    """Optional cache that de-duplicates identical CLI runs within a lock family.

    ``None`` by default, which disables caching: every :py:meth:`run` call spawns its own
    subprocess. :func:`dispatch` injects one shared dict into all the managers of a
    multi-manager lock-family lane (see :data:`SHARED_LOCK_FAMILIES`) for the duration of
    that lane, so members resolving to a byte-identical command (``brew`` and ``cask``
    both running ``brew update`` for :command:`mpm sync`) run the subprocess once and
    replay the cached ``(code, output, error)`` for the rest. The replay still walks
    :py:meth:`run`'s logging and failure gate, so a failed shared command is attributed
    to every member. Keyed on the resolved command line and its environment, so only
    genuinely identical invocations collapse.
    """

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

    def cooldown_rounded_up(self, unit_seconds: int) -> str:
        """Render :py:attr:`cooldown` as an integer count of ``unit_seconds``-long
        units, rounded up.

        Helper for the :py:meth:`cooldown_env_value` overrides of managers whose native
        release-age knob expects a unit count rather than the default RFC 3339 timestamp
        (npm's day-based ``min-release-age``, pnpm's minute-based ``minimumReleaseAge``).
        Sub-unit cooldowns round up so the gate over-protects rather than silently
        collapsing to ``0`` (the "no cooldown" sentinel).
        """
        assert self.cooldown is not None
        return str(math.ceil(self.cooldown.total_seconds() / unit_seconds))

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
            :py:class:`meta_package_manager.manager.CLIError` when the command
            fails, regardless of the user-facing :py:attr:`stop_on_error`
            preference, rather than accumulating the error for an end-of-run
            summary. Use for calls whose output is parsed (JSON, XML, regex),
            where a swallowed failure would be indistinguishable from empty
            results. A non-zero exit that leaves ``<stderr>`` empty is tolerated
            as a benign status code (``npm`` and ``pnpm outdated`` exit ``1``
            when updates exist); only the per-package state changers, which run
            under a patched :py:attr:`stop_on_error`, treat every non-zero exit
            as a failure. See the failure gate below for details.
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

        # Within a lock-family lane, key this run on its resolved command line and
        # environment so a family peer that already ran the identical command serves it
        # from cache instead of spawning a redundant (and lock-contending) subprocess.
        # See SHARED_LOCK_FAMILIES and CLIExecutor.run_cache.
        cache = self.run_cache
        cache_key = (tuple(clean_args), tuple(sorted((extra_env or {}).items())))
        cached = cache.get(cache_key) if cache is not None else None

        if cached is not None:
            # Replay the peer's result: the subprocess is skipped, but the logging and
            # failure gate below still run, so this manager is marked like the peer.
            code, output, error = cached
            logging.debug(f"Reuse lock-family peer result: {cli_msg}")
        elif self.dry_run:
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
            # Track the live child so the main thread's SIGINT handler can terminate
            # it on Ctrl+C (see terminate_live_processes): this worker thread never
            # receives the interrupt itself.
            with _LIVE_PROCESSES_LOCK:
                _LIVE_PROCESSES.add(proc)
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
                # The child is no longer live: drop it so a later Ctrl+C does not
                # try to signal an already-reaped process.
                with _LIVE_PROCESSES_LOCK:
                    _LIVE_PROCESSES.discard(proc)
            code = proc.returncode
            output = stdout or ""
            error = stderr or ""

        # Publish a freshly produced result — real or dry-run — so lock-family peers
        # replay it instead of re-running, collapsing identical invocations even under
        # --dry-run (where the first member logs the command and the rest are silent
        # cache hits). Skipped when this run was itself a hit. Normalization below is
        # idempotent, so caching the raw result here is equivalent.
        if cache is not None and cached is None:
            cache[cache_key] = (code, output, error)

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

        # Detect a failed run.
        #
        # By default a non-zero exit code is only treated as a failure when the
        # command *also* wrote to <stderr>. Many read-only CLIs use a non-zero
        # code as a status while writing their payload to <stdout> and leaving
        # <stderr> empty: ``npm`` and ``pnpm outdated`` exit 1 when updates
        # exist. Flagging those would break the parsing of their output, so a
        # silent <stderr> earns the benefit of the doubt.
        #
        # The per-package state changers (install/remove/upgrade <packages>/
        # restore) cannot afford that tolerance. They run under a patched
        # ``stop_on_error`` with ``must_succeed`` left False, and there a
        # non-zero exit is a genuine failure even when the tool reported it on
        # <stdout> and left <stderr> empty: steamcmd prints "not logged in to
        # Steam" this way on Windows, so a failed install was mistaken for a
        # success. For them the <stderr> condition is dropped.
        strict = self.stop_on_error and not must_succeed
        failed = bool(code) if strict else bool(code and error)
        if failed:
            # Produce an exception and eventually raise it.
            exception = CLIError(code, output, error)
            # A non-interactive escalation that could not authenticate is a
            # missing-credential problem, not a real command failure. Point the user
            # at the fix, naming the manager (this also answers "which one just asked
            # for my password?").
            is_escalation = clean_args[:2] == _SUDO_ESCALATION_PREFIX
            if is_escalation and _is_sudo_auth_failure(error):
                manager_id = self.id  # type: ignore[attr-defined]
                logging.warning(
                    f"{manager_id} needs administrator rights but sudo has no cached "
                    "credentials; re-run in a terminal, or with `mpm --sudo` to "
                    "authenticate once up front.",
                )
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

            $ [<pre_cmds>|sudo -n] <cli_path> <pre_args> <*args> <post_args>

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

        On UNIX, an operation marked privileged (``sudo=True``) is escalated only when
        the per-manager policy opts in (:py:attr:`sudo`, falling back to
        :py:attr:`default_sudo`). It is then run through `sudo <https://www.sudo.ws>`_
        with ``-n`` (non-interactive: it spends the credential cache warmed by
        :py:func:`prime_sudo` and fails fast rather than blocking on a password prompt).
        When escalation applies, ``override_pre_cmds`` is not allowed to be set and
        ``auto_pre_cmds`` is forced to ``False``. A non-UNIX host never escalates.
        """
        # Apply delegation overrides if set by a DelegatedMethod descriptor.
        delegate_path = getattr(self, "_delegate_cli_path", None)
        if delegate_path is not None:
            override_cli_path = override_cli_path or delegate_path
            auto_post_args = False

        params: list[TArg | TNestedArgs] = []

        # Resolve whether this privileged operation is actually escalated: the caller
        # marks the operation as needing root (``sudo``), the per-manager policy opts in
        # (the ``sudo`` override, else ``default_sudo``), and the platform has ``sudo``.
        # A non-UNIX host simply does not escalate rather than raising.
        escalate = bool(sudo and _resolved_sudo(self) and current_platform() in UNIX)
        # Sudo replaces any pre-command, be it overridden or automatic. ``-n`` keeps the
        # call non-interactive: it spends the credential cache warmed up front by
        # prime_sudo() and fails fast instead of blocking on an invisible /dev/tty
        # password prompt buried in the concurrent fan-out.
        if escalate:
            if override_pre_cmds:
                msg = "Pre-commands not allowed if sudo is requested."
                raise ValueError(msg)
            if auto_pre_cmds:
                auto_pre_cmds = False
            params.extend(_SUDO_ESCALATION_PREFIX)
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


# Cross-manager dispatch.
#
# Everything above runs one manager's CLI in one subprocess. The rest of this module
# schedules many managers: the job-count policy that decides sequential-vs-concurrent
# (:func:`effective_jobs`), the up-front availability warming used during selection
# (:func:`warm_availability`), the two spinner-wrapped fan-out primitives the CLI
# subcommands drive (:func:`collect_from_managers`, :func:`collect_per_package`), and
# the shared ``✓``/``✗`` trail (:class:`OperationTrail` plus the :func:`trail_line`
# atom) that the concurrent and sequential paths both report through.


SHARED_LOCK_FAMILIES: Final[tuple[frozenset[str], ...]] = (
    frozenset({"apt", "apt-mint", "deb-get"}),
    frozenset({"brew", "cask"}),
    frozenset({"dnf", "dnf5", "yum", "zypper"}),
    frozenset({"pacman", "pacstall"}),
)
"""Managers that contend for one shared backend lock, grouped by backend.

Different managers are otherwise independent processes over disjoint state, so running
them in parallel is safe. The exception is a handful that drive a *shared* backend and
serialize on its lock:

- ``apt``, ``apt-mint`` and ``deb-get`` all reach :command:`dpkg`
  (``/var/lib/dpkg/lock``).
- ``brew`` and ``cask`` are the *same* :command:`brew` binary and serialize on
  Homebrew's own update lock: two concurrent ``brew update`` (which :command:`mpm sync`
  issues identically for both, as the formula/cask split does not apply to it) collide,
  one failing with *"Another active Homebrew update process is already running"*.
- ``dnf``, ``dnf5``, ``yum`` and ``zypper`` all reach the RPM database.
- ``pacman`` and ``pacstall`` all reach the pacman database
  (``/var/lib/pacman/db.lck``).

Concurrency is safe *across* families and unsafe *within* one, just as it is unsafe
within a single manager (which is why a manager's own packages stay serial). When two
members run at once the shared lock makes them *block or fail*, never corrupt.

Enforced for the mutating fan-outs only: :func:`merge_into_lock_lanes` collapses each
family's members into a single :func:`dispatch` lane, so they run serially while
distinct families still run in parallel. The read-only queries
(``installed``/``outdated``/``search``) take no backend lock, so they keep one lane per
manager and stay fully concurrent. Members of a lane also share a command cache (see
:py:attr:`CLIExecutor.run_cache`), so two that resolve to a byte-identical invocation
(``brew`` and ``cask`` for ``sync`` and ``cleanup``) run the subprocess once.

Adding a newly-conflicting set of managers is a one-line edit here: append a
``frozenset`` of their ids and both the serialization and the cache pick it up.
"""


_LOCK_FAMILY_BY_MANAGER: Final[dict[str, frozenset[str]]] = {
    manager_id: family for family in SHARED_LOCK_FAMILIES for manager_id in family
}
"""Reverse index of :data:`SHARED_LOCK_FAMILIES`: each member maps to its family.

Lets :func:`merge_into_lock_lanes` resolve a manager's mutual-exclusion group in O(1).
"""


def effective_jobs(ctx: Context | None, count: int) -> int:
    """Resolve how many worker threads to use for a batch of ``count`` items.

    Thin wrapper over :py:func:`click_extra.execution.resolve_jobs` pinning mpm's
    policy: always collapse to a single (sequential) worker at ``DEBUG`` verbosity,
    where coherent per-manager log narration matters more than the speed-up
    (interleaved threads would scramble it). The base helper also collapses to
    sequential with no active CLI context, for a single item, or at
    :option:`mpm --jobs` ``1``; otherwise the :option:`mpm --jobs` value wins,
    capped at ``count`` (no point spinning up more workers than there are items).
    """
    return resolve_jobs(ctx, count, serial_at_debug=True)


def warm_availability(managers: Iterable[PackageManager]) -> None:
    """Probe several managers' ``available`` concurrently.

    Reading ``available`` forces a manager's ``--version`` detection, whose
    result (and the ``cli_path`` / ``executable`` / ``version`` it depends on) is
    cached on the instance. Warming the candidate set up front turns the
    sequential string of probes into a single round bounded by the slowest one,
    shaving startup latency off any command that touches many managers.

    Each manager is a distinct instance with its own cached attributes and
    subprocess, so the probes are independent and thread-safe; the GIL is released
    while each waits. The executor barrier publishes every cached value before the
    caller reads it back.

    Sized by :func:`effective_jobs`: a no-op (leaving the probes to lazy,
    sequential evaluation) without an active context, at ``DEBUG`` verbosity, for a
    single candidate, or at :option:`mpm --jobs` ``1``.
    """
    candidates = list(managers)
    jobs = effective_jobs(get_current_context(silent=True), len(candidates))
    if jobs <= 1:
        return
    # Reading `available` forces and caches the probe inside each worker.
    list(run_jobs(lambda manager: manager.available, candidates, jobs=jobs))


def trail_glyph(ok: bool) -> str:
    """Return the themed ``✓`` or ``✗`` glyph for a trail line or finisher."""
    return theme().success(OK_GLYPH) if ok else theme().error(KO_GLYPH)


def trail_line(ok: bool, message: str) -> str:
    """Format one ``✓``/``✗`` trail line: a status glyph followed by ``message``."""
    return f"{trail_glyph(ok)} {message}"


def _state_failed(data: dict) -> bool:
    """Whether a manager's result fails its ``✓``/``✗`` trail line.

    A non-empty ``data["errors"]`` (CLI errors, or a read query's error list) or an
    explicit ``data["failed"]`` flag (``upgrade --all``'s cooldown skips, which run
    no CLI of their own) both mark the line ``✗``.
    """
    return bool(data.get("errors") or data.get("failed"))


class OperationTrail:
    """A ``✓``/``✗`` progress trail and finisher for a batch of operations.

    The single report surface for every fan-out command, rendered one of two ways
    depending on concurrency:

    - **sequential** (``jobs <= 1``): echo each outcome between the managers' own
      per-call spinners, with no aggregate spinner. The ordering-bound state changers
      (``install``/``remove``/``upgrade <packages>``/``restore``) drive this directly,
      since they chain managers by priority (a hit in the first manager skips the
      rest) and so cannot fan out; it is also every :func:`dispatch` fallback at
      :option:`mpm --jobs` ``1`` or ``DEBUG`` verbosity.
    - **concurrent** (``jobs > 1``): suppress the per-manager spinners (which would
      collide on stderr) and drive one aggregate spinner, buffering outcomes until it
      first draws, then streaming the rest live.

    Both are gated on ``--progress`` (folded into each manager's ``progress``) plus an
    interactive stderr, so pipes, CI, serialized and ``DEBUG`` runs stay silent. A read
    command whose result *table* is the real output stays silent in sequential mode too
    (``coverage=True``): the per-call spinners already narrate progress, so the trail
    would be noise. The running ``✓``/total tally is kept as outcomes land, so a caller
    computes no counts of its own.

    Thread-safe: :meth:`mark` may be called from worker threads. Use it as a context
    manager whenever it may run concurrently, to bound the aggregate spinner's life; a
    purely sequential caller (``install``'s priority search) may construct it bare.

    :param managers: the batch's managers, read for the ``--progress`` gate and (when
        concurrent) to mute their per-call spinners.
    :param label: present-tense verb for the running spinner ("Searching").
    :param done_label: past-tense verb for the finisher ("Searched").
    :param unit: the noun counted in the spinner and finisher ("managers", "packages").
    :param total: how many outcomes are expected, for the ``done/total`` count.
    :param jobs: the worker count from :func:`effective_jobs`; ``> 1`` selects the
        concurrent rendering.
    :param coverage: when set, a sequential run stays silent (the caller has another
        output, its result table). Unused when concurrent.
    """

    def __init__(
        self,
        managers: Iterable[PackageManager],
        *,
        label: str = "",
        done_label: str = "",
        unit: str = "",
        total: int = 0,
        jobs: int = 1,
        coverage: bool = False,
    ) -> None:
        self.label = label
        self.done_label = done_label
        self.unit = unit
        self.total = total
        self.concurrent = jobs > 1
        self._managers = tuple(managers)
        self._lock = threading.Lock()
        self._done = 0
        self._ok = 0
        self._start = time.monotonic()
        self._spinner: Spinner | None = None
        self._buffer: list[str] = []
        progress = any(manager.progress for manager in self._managers)
        # Sequential read commands stay silent: their result table is the output and
        # each manager keeps its own per-call spinner, so the trail would be noise.
        self._echo = (
            progress and not self.concurrent and not coverage and sys.stderr.isatty()
        )
        # Concurrent: a single aggregate spinner stands in for the muted per-call ones.
        self._enabled = None if progress else False

    def __enter__(self) -> Self:
        if self.concurrent:
            for manager in self._managers:
                manager.progress = False
            self._spinner = Spinner(
                f"{self.label} 0/{self.total} {self.unit}",
                delay=SPINNER_DELAY,
                enabled=self._enabled,
                timer=True,
            )
            self._spinner.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._spinner is not None:
            self._spinner.__exit__(exc_type, exc_val, exc_tb)
            self._spinner = None

    @property
    def ok_count(self) -> int:
        """How many marked outcomes have succeeded so far."""
        return self._ok

    def mark(self, ok: bool, message: str) -> None:
        """Record one ``✓``/``✗`` outcome: tally it and render its trail line."""
        with self._lock:
            self._done += 1
            if ok:
                self._ok += 1
            if self._spinner is not None:
                self._buffer.append(trail_line(ok, message))
                self._spinner.label = (
                    f"{self.label} {self._done}/{self.total} {self.unit}"
                )
                self._flush()
            elif self._echo:
                echo(trail_line(ok, message), err=True)

    def _flush(self) -> None:
        # Caller holds the lock. Drain buffered lines once the spinner is drawing;
        # before that, echo() would write unconditionally and leak into a pipe.
        if self._spinner is None or not self._spinner.shown:
            return
        for text in self._buffer:
            self._spinner.echo(text)
        self._buffer.clear()

    def finish(self, ok: bool, summary: str) -> None:
        """Render the persistent ``✓``/``✗`` ``{summary}`` finisher."""
        if self._spinner is not None:
            with self._lock:
                self._flush()
            if self._spinner.shown:
                self._spinner.label = summary
                (self._spinner.ok if ok else self._spinner.fail)()
        elif self._echo:
            elapsed = time.monotonic() - self._start
            echo(trail_line(ok, f"{summary} ({elapsed:.1f}s)"), err=True)


def dispatch(
    label: str,
    done_label: str,
    unit: str,
    lanes: list[
        tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]
    ],
    *,
    coverage: bool = False,
    ctx: Context | None = None,
) -> None:
    """Fan a set of work *lanes* out across managers, narrating a ``✓``/``✗`` trail.

    The single scheduling primitive behind both :func:`collect_from_managers` and
    :func:`collect_per_package`. A *lane* is one or more managers paired with a list of
    callables; lanes run concurrently (one worker each) while a lane's own callables run
    serially, because a package manager cannot safely run two of its own invocations at
    once, nor can two managers sharing a backend lock (see :data:`SHARED_LOCK_FAMILIES`).
    A lane usually wraps a single manager; :func:`merge_into_lock_lanes` is what bundles
    a whole lock family into one, and such a lane also gets a shared command cache (see
    :py:attr:`CLIExecutor.run_cache`) so its members collapse identical invocations.

    Each callable does its work, records its own outcome (output to ``INFO``, failures
    into a caller-owned list) and returns ``(ok, message)`` for the trail. The whole
    batch reports through one :class:`OperationTrail`: a per-outcome ``✓``/``✗`` line
    plus a finisher, behind a single aggregate spinner when concurrent (a slow batch on
    a terminal) and silent otherwise.

    Concurrency is sized by :func:`effective_jobs` (driven by :option:`mpm --jobs`): it
    collapses to a sequential pass — preserving each manager's own per-call spinner —
    for a single lane, at ``--jobs 1``, or at ``DEBUG`` verbosity.

    :param coverage: forwarded to :class:`OperationTrail`. Read commands set it (their
        result table is the output, so the sequential pass stays silent and the finisher
        reports coverage, ``{done_label} N {unit}``, always ``✓``). Maintenance and
        state-changing commands leave it ``False`` (the trail *is* their output, so the
        finisher reports the success count, ``{done_label} N/M {unit}``, ``✗`` on any
        failure).
    :param ctx: the active click context, read only to size concurrency
        (:func:`effective_jobs`). Defaults to the current context, so a command need not
        thread it; tests pass an explicit stand-in.
    """
    total = sum(len(tasks) for _managers, tasks in lanes)
    if not total:
        return
    if ctx is None:
        ctx = get_current_context(silent=True)
    jobs = effective_jobs(ctx, len(lanes))
    managers = [manager for lane_managers, _ in lanes for manager in lane_managers]

    # A multi-manager lane is a lock family: its members share one command cache
    # for the run, so byte-identical invocations (brew and cask both running
    # `brew update`) hit the subprocess once. Each cache belongs to a single lane
    # whose tasks run serially on one worker (via run_lanes), so only that thread
    # touches it: no lock needed. Cleared in the finally below.
    shared_caches: list[tuple[tuple[PackageManager, ...], dict]] = [
        (lane_managers, {}) for lane_managers, _ in lanes if len(lane_managers) > 1
    ]
    for lane_managers, cache in shared_caches:
        for manager in lane_managers:
            manager.run_cache = cache

    try:
        with OperationTrail(
            managers,
            label=label,
            done_label=done_label,
            unit=unit,
            total=total,
            jobs=jobs,
            coverage=coverage,
        ) as trail:
            # Each lane's tasks run serially on one worker, marking the trail as each
            # completes; distinct lanes run concurrently, sized by ``effective_jobs``.
            list(
                run_lanes(
                    lambda task: trail.mark(*task()),
                    [tasks for _managers, tasks in lanes],
                    jobs=jobs,
                )
            )

            if coverage:
                trail.finish(True, f"{done_label} {total} {unit}")
            else:
                ok = trail.ok_count
                trail.finish(ok == total, f"{done_label} {ok}/{total} {unit}")
    finally:
        for lane_managers, _ in shared_caches:
            for manager in lane_managers:
                manager.run_cache = None


def merge_into_lock_lanes(
    pairs: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]],
) -> list[tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]]:
    """Group ``(manager, task)`` pairs into :func:`dispatch` lanes, one per lock family.

    Managers sharing a :data:`SHARED_LOCK_FAMILIES` entry collapse into a single lane so
    their tasks run serially (the lane is :func:`dispatch`'s unit of mutual exclusion),
    while unrelated managers each keep their own lane and run concurrently. A manager not
    in any family keys on its own id, so its tasks still group together (a manager's own
    invocations cannot overlap either). First-seen order is preserved, both across lanes
    and within a lane's task list.

    Used by the mutating fan-outs only: the state changers through
    :func:`collect_per_package`, and ``sync``/``cleanup``/``upgrade --all`` through
    :func:`collect_from_managers`. The read commands take no backend lock and skip this,
    keeping one lane per manager.
    """
    lanes: dict[
        object, tuple[list[PackageManager], list[Callable[[], tuple[bool, str]]]]
    ]
    lanes = {}
    for manager, task in pairs:
        key = _LOCK_FAMILY_BY_MANAGER.get(manager.id, manager.id)
        lane_managers, lane_tasks = lanes.setdefault(key, ([], []))
        if manager not in lane_managers:
            lane_managers.append(manager)
        lane_tasks.append(task)
    return [(tuple(ms), ts) for ms, ts in lanes.values()]


def collect_from_managers(
    label: str,
    done_label: str,
    managers: list[PackageManager],
    work: Callable[[PackageManager], tuple[str, dict]],
    *,
    report_state: bool = False,
    ctx: Context | None = None,
) -> list[tuple[str, dict]]:
    """Run ``work(manager)`` for every manager concurrently, results in input order.

    The fan-out primitive for the read-only commands (``installed``/``outdated``/
    ``search``) and the independent maintenance commands (``sync``/``cleanup``/
    ``upgrade --all``). It adapts each manager into a :func:`dispatch` unit that runs
    ``work`` and stashes the ``(id, data)`` result in input position, so the returned
    list mirrors ``managers`` regardless of completion order. The maintenance commands
    (``report_state``) then merge lock-family members into shared serial lanes
    (:func:`merge_into_lock_lanes`); the read commands keep one lane per manager.

    ``work`` returns this manager's ``(id, data)``; it must handle its own
    :py:class:`meta_package_manager.execution.CLIError` (each manager owns its
    subprocess and error list, so the call is thread-safe per manager). A truthy
    ``data["errors"]`` (or ``data["failed"]``) marks that manager's trail line ``✗``;
    an optional ``data["label"]`` overrides its text (``upgrade --all`` uses it for
    cooldown skips).

    :param report_state: maintenance commands set it (their only output is the trail).
        It flips the finisher to a success count, keeps the trail in the sequential
        fallback, and turns on lock-family serialization. Read commands leave it
        ``False``: their table is the output, so the sequential fallback is silent and
        the finisher reports coverage. Passed to :func:`dispatch` as the inverse of
        ``coverage``.
    """
    results: list[tuple[str, dict]] = [("", {})] * len(managers)

    def make_unit(
        index: int, manager: PackageManager
    ) -> Callable[[], tuple[bool, str]]:
        def unit() -> tuple[bool, str]:
            manager_id, data = work(manager)
            results[index] = (manager_id, data)
            text = data.get("label") or theme().invoked_command(manager_id)
            return not _state_failed(data), text

        return unit

    pairs = [(manager, make_unit(i, manager)) for i, manager in enumerate(managers)]
    # Mutating fan-outs (report_state) serialize lock families into shared lanes; the
    # read commands take no backend lock and keep one lane per manager.
    lanes: list[tuple[tuple[PackageManager, ...], list[Callable[[], tuple[bool, str]]]]]
    if report_state:
        lanes = merge_into_lock_lanes(pairs)
    else:
        lanes = [((manager,), [unit]) for manager, unit in pairs]
    dispatch(label, done_label, "managers", lanes, coverage=not report_state, ctx=ctx)
    return results


def collect_per_package(
    label: str,
    done_label: str,
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]],
    *,
    ctx: Context | None = None,
) -> None:
    """Run per-package operations across managers concurrently, serial within each.

    The fan-out primitive for the ordering-free state changers that act on many
    (package, manager) pairs: ``remove``, ``upgrade <packages>``, ``restore`` and the
    manager-tied specs of ``install``. Takes a flat list of ``(manager, task)`` pairs
    and groups them into lanes by lock family (:func:`merge_into_lock_lanes`) — so a
    manager's own packages, and any lock-family peers, stay serial while unrelated
    managers run in parallel — then drives :func:`dispatch`. Each task returns
    ``(ok, message)`` after doing its CLI call and recording its own outcome. The
    unmatched-package priority search of ``install`` is *not* routed here: it has genuine
    cross-manager ordering (stop at the first manager that has the package) and stays
    sequential on its own.
    """
    dispatch(label, done_label, "packages", merge_into_lock_lanes(tasks), ctx=ctx)


def warn_jobs_ignored(ctx: Context) -> None:
    """Note that ``--jobs`` does not parallelize this run.

    Only ``install`` with at least one *untied* package reaches this: those packages
    need a priority search (install with the first manager that has the package, skip
    the rest), which is cross-manager-sequential, so the whole command runs serially.
    The other state changers (``remove``, ``upgrade <packages>``, ``restore``, and
    ``install`` of fully manager-tied specs) now fan out through
    :func:`collect_per_package`. When the user explicitly raised :option:`mpm --jobs`
    above ``1``, say so once at ``INFO``: the request simply has no effect on this
    run, which is narration, not a problem.
    """
    if ctx.meta.get(JOBS, 1) <= 1:
        return
    if ctx.find_root().get_parameter_source("jobs") not in (
        ParameterSource.COMMANDLINE,
        ParameterSource.ENVIRONMENT,
    ):
        return
    logging.info(
        "This command dispatches managers sequentially by priority; "
        "--jobs does not parallelize it.",
    )
