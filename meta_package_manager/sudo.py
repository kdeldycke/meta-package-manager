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
"""Privilege-escalation machinery for the mutating fan-outs.

This module owns ``sudo`` credential priming (:py:func:`prime_sudo`) and its
background keepalive (:py:func:`_start_sudo_keepalive`), escalation-policy
resolution (:py:func:`_resolved_sudo`), sudo-failure detection
(:py:func:`_is_sudo_auth_failure`), and the hidden-prompt stall watchdog
(:py:class:`_StallWatchdog`). The execution engine
(:py:mod:`meta_package_manager.execution`) consumes the policy pieces to wrap and
diagnose escalated commands; the CLI calls :py:func:`prime_sudo` at the top of
each mutating subcommand.

Why priming exists: a concurrent state-changing command mutes per-manager output
and feeds each child ``stdin=/dev/null``, so a ``sudo`` password prompt raised
mid-run (by mpm's own ``sudo --non-interactive`` or by a manager that escalates
internally, like
Homebrew ``cask``) lands invisibly on ``/dev/tty`` and can stall the run up to the
mutating timeout. Priming first probes the credential cache non-interactively:
found warm, it is silently kept alive for the whole run; found cold on a terminal,
the managers mpm itself escalates get a single up-front password prompt, naming
them and branded ``[mpm]``. Internal escalators never prompt up front: their rare
cold-cache escalation is covered by the silent-call stall notice instead, raised
while the hidden prompt can still be answered.

.. note::
    Everything in this module is UNIX-only: a Windows run returns early at
    :py:func:`prime_sudo`'s guard and never arms the watchdog (the internal
    escalators are macOS-only managers today).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Final

from click_extra import echo
from extra_platforms import is_any_windows

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable

    from click import Context

    from .execution import CLIExecutor
    from .manager import PackageManager


_STALL_NOTICE_DELAY: Final = 30
"""Seconds of child silence before an armed stall watchdog raises its notice.

Counted on a terminal, during a mutating call of a manager that runs ``sudo``
internally (:py:attr:`CLIExecutor.internal_sudo
<meta_package_manager.execution.CLIExecutor.internal_sudo>`). Long enough that
ordinary quiet stretches (dependency resolution, download lulls that still tick
progress lines) rarely trip it, yet far below
:py:data:`~meta_package_manager.execution.MUTATING_TIMEOUT`, so the user gets the
hint while the hidden password prompt can still be answered. See
:py:class:`_StallWatchdog`.
"""

_STALL_NOTICE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"install", "remove", "upgrade", "upgrade_all"},
)
"""Operations whose commands may block on an interactive internal ``sudo``.

Matched against :py:attr:`CLIExecutor._active_operation
<meta_package_manager.execution.CLIExecutor._active_operation>` when arming the
stall watchdog: the mutating operations whose installers may escalate mid-flight
(``restore`` stamps ``"install"``, so it is covered). ``sync`` and ``cleanup`` are
excluded on purpose, to avoid false notices on ``brew update``/``brew cleanup``,
whose long silent phases never escalate. The trade-off is a known gap: ``fink``
does re-exec ``fink selfupdate``/``fink cleanup`` through ``sudo``, so a cold-cache
``mpm sync``/``mpm cleanup`` of ``fink`` can still stall unflagged on a hidden
prompt.
"""

_SUDO_CACHE_WARM: Final = threading.Event()
"""Set while a priming keepalive maintains the credential cache for the invocation.

Armed by :py:func:`_start_sudo_keepalive` and cleared when the context closes. A warm
cache serves internal escalations (:py:attr:`CLIExecutor.internal_sudo
<meta_package_manager.execution.CLIExecutor.internal_sudo>`) silently, so the
silent-call stall watchdog skips arming while this flag is set.

.. note::

    The flag records that ``mpm`` holds a validated credential, assuming sudo's default
    timestamp semantics. Under a hardened sudoers policy (``timestamp_timeout=0``, or a
    ``timestamp_type`` keyed to the process rather than the terminal) a manager's own
    child ``sudo`` may not be able to spend that credential, and its mid-run prompt then
    goes unflagged. Priming still authenticates; only the watchdog is suppressed.
"""

_SUDO_ESCALATION_PREFIX: Final = ("sudo", "--non-interactive")
"""Argv prefix mpm prepends to escalate a manager command non-interactively.

:py:meth:`CLIExecutor.build_cli
<meta_package_manager.execution.CLIExecutor.build_cli>` emits it and
:py:meth:`CLIExecutor.run <meta_package_manager.execution.CLIExecutor.run>` matches
it byte-for-byte to turn a ``sudo --non-interactive`` authentication failure into
an actionable
hint, so the two sites must stay in lockstep.
"""

_SUDO_KEEPALIVE_INTERVAL: Final = 60
"""Seconds between ``sudo --non-interactive --validate`` credential-cache
refreshes during a run.

Comfortably under sudo's default ``timestamp_timeout`` (5 minutes), so the cache warmed
by :py:func:`prime_sudo` stays valid for the whole command. A host configured with a
shorter ``timestamp_timeout`` may still see a mid-run escalation re-prompt or fail.
"""

_SUDO_PRIMED: Final = "mpm_sudo_primed"
"""``ctx.meta`` key marking that :py:func:`prime_sudo` already ran this invocation."""


def _resolved_sudo(manager: CLIExecutor) -> bool:
    """Whether ``manager`` escalates: its
    :py:attr:`~meta_package_manager.execution.CLIExecutor.sudo` override if set,
    else its built-in
    :py:attr:`~meta_package_manager.execution.CLIExecutor.default_sudo`."""
    return manager.sudo if manager.sudo is not None else manager.default_sudo


def _is_sudo_auth_failure(error: str) -> bool:
    """Whether ``error`` is ``sudo`` refusing to authenticate non-interactively.

    ``sudo --non-interactive`` writes one of these to ``<stderr>`` when it has no
    cached credentials
    and cannot prompt for a password (nothing cached, no controlling terminal, no
    askpass helper). Lets :py:meth:`CLIExecutor.run
    <meta_package_manager.execution.CLIExecutor.run>` turn an opaque escalation
    failure into an actionable hint.
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


def _start_sudo_keepalive(ctx: Context) -> None:
    """Keep the ``sudo`` credential cache fresh for the rest of the invocation.

    Refreshes the cache every :py:data:`_SUDO_KEEPALIVE_INTERVAL` seconds so a long
    fan-out does not outlast sudo's timestamp and re-prompt mid-flight. Output is
    captured so a failed refresh cannot smear the aggregate spinner drawing on
    stderr. Sets :py:data:`_SUDO_CACHE_WARM` for the whole run; the daemon thread is
    stopped and the flag cleared when the context closes (normal exit or Ctrl+C both
    run close callbacks).
    """
    stop = threading.Event()

    def keepalive() -> None:
        while not stop.wait(_SUDO_KEEPALIVE_INTERVAL):
            subprocess.run(
                ("sudo", "--non-interactive", "--validate"),
                capture_output=True,
                check=False,
            )

    threading.Thread(target=keepalive, daemon=True).start()
    _SUDO_CACHE_WARM.set()

    def teardown() -> None:
        stop.set()
        _SUDO_CACHE_WARM.clear()

    ctx.call_on_close(teardown)


def prime_sudo(ctx: Context, managers: Iterable[PackageManager]) -> None:
    """Warm the ``sudo`` credential cache, up front, for a mutating fan-out.

    Probes the cache non-interactively (``sudo --non-interactive --validate``)
    before considering any
    prompt. A warm cache (pre-authenticated ``sudo --validate``, a ``NOPASSWD`` rule, a
    recent run) is silently kept fresh for the whole invocation by
    :py:func:`_start_sudo_keepalive`, so every later escalation on the same
    terminal, mpm's own ``sudo --non-interactive`` as well as a manager's internal
    ``sudo``
    (:py:attr:`CLIExecutor.internal_sudo
    <meta_package_manager.execution.CLIExecutor.internal_sudo>`), spends the cache
    instead of blocking on an invisible prompt inside the concurrent fan-out. Only
    a cold cache, on an interactive terminal, with managers that mpm itself
    escalates (:py:func:`_resolved_sudo`), triggers the interactive path: a notice
    naming the managers and the subcommand, then a single branded ``sudo`` password
    prompt.

    Call at the top of each mutating subcommand, before the fan-out draws its
    spinner. Never prompts when:

    - Windows (no ``sudo``) or the process is already root,
    - no selected manager escalates, through mpm or internally,
    - a dry run or a plan run (no state-changing CLI is executed),
    - already primed once this invocation (idempotent),
    - the ``sudo`` executable is missing (one warning is logged),
    - the probe finds the cache already warm (keepalive only, fully silent),
    - no interactive terminal is available: one warning names the managers mpm
      escalates and leaves them to fail fast rather than block on a prompt no one
      can answer, while an internal-only selection stays silent, or
    - only internal escalators are selected on a cold cache: most such runs never
      escalate, so the rare mid-run prompt is covered by the silent-call stall
      notice instead.
    """
    managers = list(managers)
    if is_any_windows() or getattr(os, "geteuid", lambda: 1)() == 0:
        return
    escalating = sorted({m.id for m in managers if _resolved_sudo(m)})
    internal = any(m.internal_sudo for m in managers)
    if not escalating and not internal:
        return
    if any(manager.dry_run or manager.plan for manager in managers):
        return
    if ctx.meta.get(_SUDO_PRIMED):
        return
    ctx.meta[_SUDO_PRIMED] = True

    try:
        probe = subprocess.run(
            ("sudo", "--non-interactive", "--validate"),
            capture_output=True,
            check=False,
        )
    except OSError:
        # No sudo on PATH (FileNotFoundError), or one that cannot be run: not executable
        # for this user (PermissionError), not a valid binary (OSError). Degrade to a
        # warning and let unprivileged managers proceed rather than crash.
        logging.warning("sudo could not be run: managers needing root may fail.")
        return
    if probe.returncode == 0:
        # Cache already warm (a prior ``sudo --validate``, a NOPASSWD rule):
        # keep it fresh,
        # silently. A CI job with pre-cached credentials thus gets the keepalive
        # instead of the no-terminal warning.
        _start_sudo_keepalive(ctx)
        return

    ids = ", ".join(escalating)
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        if escalating:
            logging.warning(
                f"{ids} need{'s' if len(escalating) == 1 else ''} administrator "
                "rights, but no terminal is available to prompt for a password: "
                "they may fail. Re-run in a terminal, pre-authenticate with "
                "`sudo --validate`, or drop them with --no-sudo.",
            )
        # An internal-only selection stays silent: each manager's own sudo fails
        # fast and surfaces through its error path.
        return

    if not escalating:
        # Internal-only selection on a cold cache (a stock macOS cask/fink run):
        # return without prompting. Most such runs never escalate, so an up-front
        # password prompt on every run would be the mirror-image regression. The
        # silent-call stall notice covers the rare mid-run prompt instead.
        return

    echo(
        f"{ids} need{'s' if len(escalating) == 1 else ''} administrator rights to "
        f"{ctx.command.name}: enter your password.",
        err=True,
    )
    # ``sudo --prompt`` expands %-escapes; manager IDs are plain slugs, so the escaping
    # is belt-and-braces.
    prompt = f"[mpm] password for {ids}: ".replace("%", "%%")
    prompt_cli = ("sudo", "--validate", "--prompt", prompt)
    if subprocess.run(prompt_cli, check=False).returncode != 0:
        logging.warning(
            "Could not acquire sudo credentials: managers needing root may fail.",
        )
        return
    _start_sudo_keepalive(ctx)


class _StallWatchdog(logging.Handler):
    """Warn when a CLI call that may hide a ``sudo`` password prompt goes silent.

    A manager that escalates internally (:py:attr:`CLIExecutor.internal_sudo
    <meta_package_manager.execution.CLIExecutor.internal_sudo>`) can raise a
    ``sudo`` prompt from inside its own commands. The child reads ``stdin`` from
    ``/dev/null`` and its output streams to ``DEBUG`` logs, so on a cold
    credential cache the prompt lands invisibly on ``/dev/tty``: the run looks
    stuck until the mutating timeout kills it. When :py:func:`prime_sudo` left the
    cache cold, :py:meth:`CLIExecutor.run
    <meta_package_manager.execution.CLIExecutor.run>` arms this watchdog around
    the spawn: once :py:data:`_STALL_NOTICE_DELAY` seconds pass without a fresh
    output line, a daemon thread logs one ``WARNING`` naming the manager and
    quoting its last line, so the user can tell a hidden prompt from a slow
    download and answer it on the terminal while it still waits. Each silence
    episode warns at most once; a fresh line starts a new episode.

    The watchdog doubles as the sole handler of :py:attr:`tee`, the logger
    :py:meth:`CLIExecutor.run <meta_package_manager.execution.CLIExecutor.run>`
    hands to :py:func:`click_extra.execution.run_cli` in place of the root logger:
    :py:meth:`emit` tracks the child's activity, then forwards every record
    verbatim to the root logger, whose level click-extra's ``--verbosity``
    manages, keeping the display byte-identical to an un-teed run at every
    verbosity.

    .. note::

        Considered alternative: a ``SUDO_ASKPASS`` helper. ``brew`` documents
        passing ``--askpass`` to its internal ``sudo`` whenever that variable is
        set, so mpm could export a helper into the child environment and rebrand
        the hidden prompt itself ("[mpm] cask needs your password..."), working
        even under hardened sudoers policies whose timestamps the priming cache
        cannot serve (see :py:data:`_SUDO_CACHE_WARM`). Rejected for now: the
        helper reads the raw password and pipes it to ``sudo`` (a security
        surface this notice avoids entirely), it needs a side channel to pause
        the spinner that would smear its prompt, and it only covers tools
        honoring the variable (``brew`` does, ``fink``'s plain ``sudo`` re-exec
        does not). Revisit if this notice proves insufficient in the field; the
        scoped ``sudo = true`` opt-in documented in ``docs/sudo.md`` already
        covers users wanting a guaranteed up-front prompt.
    """

    tee: logging.Logger
    """Stand-in destination for ``run_cli``'s streamed records while armed.

    Deliberately a direct :py:class:`logging.Logger` construction, never
    :py:func:`logging.getLogger`: unregistered, each armed call gets a private tee
    that concurrent calls cannot cross-contaminate; parentless, its records cannot
    propagate straight to the root handlers, which would bypass the root level
    gate and leak ``DEBUG`` lines at default verbosity. Its ``DEBUG`` level lets
    every record reach :py:meth:`emit`: dropping is the root logger's decision.
    """

    def __init__(self, manager_id: str) -> None:
        """Arm the watchdog for one CLI call of ``manager_id``."""
        super().__init__()
        self._manager_id = manager_id
        self._started = time.monotonic()
        # Latest child activity, one ``(monotonic timestamp, output line)`` pair.
        # Written by emit() in a single reference assignment and read the same way
        # by the notice thread, so the pair stays consistent without a lock
        # (free-threading safe). Starts at arming time, with no line seen yet.
        self._activity: tuple[float, str | None] = (self._started, None)
        # Activity timestamp of the silence episode already noticed, so each
        # episode warns at most once. Touched by the notice thread only.
        self._noticed: float | None = None
        # Instantiated directly, not via getLogger: the tee must stay out of the
        # registry (re-arming would reuse it, stacking handlers) and have no
        # parent, so this handler is its only sink and nothing double-emits.
        self.tee = logging.Logger(  # noqa: LOG001
            f"mpm-stall-tee-{manager_id}", logging.DEBUG
        )
        self.tee.addHandler(self)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Track child activity, then forward ``record`` verbatim to the root.

        Only the streamed output lines refresh the activity state: they are the
        records carrying a ``label`` attribute (``run_cli`` labels the child's
        output lines only, never its own prompt-disclosure or PID-tracking lines),
        and only genuine output vouches that the child is not blocked on a prompt.

        Forwarding re-enters :py:meth:`logging.Logger.log` on the root logger so
        its level gate (the one click-extra's ``--verbosity`` manages) and its
        handlers apply exactly as if ``run_cli`` had logged there directly.
        """
        try:
            message = record.getMessage()
            label = getattr(record, "label", None)
            root = logging.getLogger()
            if label is None:
                root.log(record.levelno, message)
            else:
                self._activity = (time.monotonic(), message)
                root.log(record.levelno, message, extra={"label": label})
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def _watch(self) -> None:
        """Notice-thread body: warn once per silence episode.

        A silence episode is identified by the timestamp of the latest activity: a
        fresh output line moves it, which re-arms the notice for the next silent
        stretch. Wakes at most every second (sooner when the delay itself is
        shorter) so a stop request is honored promptly.
        """
        while not self._stop.wait(min(1.0, _STALL_NOTICE_DELAY)):
            last_stamp, last_line = self._activity
            silence = time.monotonic() - last_stamp
            if silence < _STALL_NOTICE_DELAY or self._noticed == last_stamp:
                continue
            self._noticed = last_stamp
            if last_line is None:
                detail = "No output since the command started."
            else:
                # Cap the quoted line at 120 characters, ellipsis included.
                if len(last_line) > 120:
                    last_line = last_line[:119] + "…"
                detail = f'Last output: "{last_line}"'
            # WARNING survives the default verbosity, and click-extra's handler
            # prints it above any animating spinner frame. The wording never
            # instructs the user to type blindly: the prompt may not exist.
            logging.warning(
                f"No output for {int(silence)}s: may be waiting on a hidden "
                f"password prompt. {detail}",
                extra={"label": self._manager_id},
            )

    def stop(self) -> None:
        """Disarm: stop the notice thread, join it, and detach the handler."""
        self._stop.set()
        self._thread.join()
        self.close()
