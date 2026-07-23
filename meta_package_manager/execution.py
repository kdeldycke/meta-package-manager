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

Runs *one* manager's CLI in one subprocess: the
{class}`meta_package_manager.execution.CLIExecutor` mixin (which
{class}`meta_package_manager.manager.PackageManager` inherits) locates the binary
and runs it, the {class}`meta_package_manager.execution.CLIError` exception carries
a failed call's result, and {func}`meta_package_manager.execution.highlight_cli_name`
themes a binary's name.

Scheduling *many* managers at once is the next altitude up, and lives in
{mod}`meta_package_manager.dispatch`: the concurrent fan-out primitives, the
lock families and the shared `✓`/`✗` trail. The `sudo` machinery that cuts
across both altitudes (credential priming, the keepalive, the hidden-prompt stall
watchdog) lives in {mod}`meta_package_manager.sudo`: this module only consumes
it, to wrap escalated commands and diagnose their failures.

```{note}
The name and intent mirror {mod}`click_extra.execution` from the sibling
[click-extra](https://github.com/kdeldycke/click-extra) project, where the
generic layers now live: the concurrency primitives (`run_jobs`/`run_lanes`
driven by `mpm --jobs`), the single-subprocess engine
({func}`click_extra.execution.run_cli`, which disclosed invocations and
streams output to the logs), and the Ctrl+C machinery
({func}`click_extra.execution.install_interrupt_handler` terminating the
in-flight children registered by `run_cli`). This module keeps what is
package-manager policy: per-operation timeouts, sudo escalation, cooldown
enforcement and dry-run.
```
"""

from __future__ import annotations

import logging
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from textwrap import dedent, indent, shorten
from typing import ClassVar, Final

from boltons.iterutils import unique
from boltons.strutils import strip_ansi
from click_extra.execution import (
    INDENT,
    args_cleanup,
    format_cli_prompt,
    highlight_bin_name,
    run_cli,
)
from click_extra.spinner import Spinner
from click_extra.theme import get_current_theme as theme
from extra_platforms import UNIX, current_platform, is_any_windows

from .sudo import (
    _STALL_NOTICE_OPERATIONS,
    _SUDO_CACHE_WARM,
    _SUDO_ESCALATION_PREFIX,
    _is_sudo_auth_failure,
    _resolved_sudo,
    _StallWatchdog,
)
from .version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator
    from datetime import timedelta

    from click_extra.envvar import TEnvVars
    from click_extra.execution import TArg, TNestedArgs

    from .version import TokenizedString

DIAGNOSIS_TAIL_LINES: Final = 10
"""Trailing lines of a failed command's report relayed at `WARNING`.

CLIs conclude with their actual error, so the tail is where the diagnosis
lives; the cap keeps a verbose failure (a source build's compiler spew) from
flooding the default view. The raw streams are always available in full, live,
at `DEBUG`.
"""


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

    @property
    def diagnosis(self) -> str:
        """The command's own account of its failure, capped for log relay.

        Prefers `<stderr>`, the conventional stream for error reporting, and
        falls back on `<stdout>` for the tools that report failures there
        (steamcmd); a command that died silently is reduced to its exit code.
        Only the last {data}`DIAGNOSIS_TAIL_LINES` lines are kept, behind a
        counter of the truncated ones: errors conclude streams.
        """
        report = self.error.strip() or self.output.strip()
        if not report:
            return f"Exited {self.code} with no output."
        lines = report.splitlines()
        hidden = len(lines) - DIAGNOSIS_TAIL_LINES
        if hidden > 0:
            plural = "lines" if hidden > 1 else "line"
            lines = [
                f"(...) {hidden} earlier {plural} truncated.",
                *lines[-DIAGNOSIS_TAIL_LINES:],
            ]
        return "\n".join(lines)


_MUTATING_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"install", "upgrade", "upgrade_all", "remove", "sync", "cleanup"},
)
"""State-changing operations, matched against {attr}`CLIExecutor._active_operation`.

Under `mpm --plan` their CLI calls are captured into {data}`PLAN_RECORDER`
instead of being executed, while the read-only queries (`installed`, `outdated`,
`search`) still run so the plan resolves against real system state. `restore`
re-stamps `install` on the manager, so it is covered here.
"""

VERSION_PROBE: Final = "version"
"""Pseudo-operation stamped on {attr}`CLIExecutor._active_operation` during
version detection.

Not a member of {class}`meta_package_manager.capabilities.Operations` (no
subcommand routes it), but it participates in the same per-operation machinery:
{data}`OPERATION_TIMEOUTS` binds it to the short read-only cap, and
{meth}`CLIExecutor.run` demotes its command disclosure to `DEBUG` so the
per-candidate probes cannot drown the `INFO` narration.
"""

_DIAGNOSIS_EXEMPT_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"doctor", VERSION_PROBE},
)
"""Operations whose failed runs skip the `WARNING` diagnosis relay.

Version probes fire for every candidate manager on selection, so a broken
binary would otherwise warn on every single run: their failures stay at
`DEBUG` with the rest of the discovery narration. `doctor` relays each
manager's full report verbatim on its own terms and reclaims the failure-gate
entry (see {meth}`meta_package_manager.manager.PackageManager.doctor`): the
relay would print the same findings twice.
"""


def format_plan_command(
    cmd_args: Iterable[str],
    extra_env: TEnvVars | None = None,
) -> str:
    """Render a captured `mpm --plan` command as a copy-pasteable shell line.

    Unlike {func}`click_extra.execution.format_cli_prompt` (styled, and prefixed
    with a `$` prompt sigil for logs and dry-runs), this returns a plain, unstyled,
    shell-quoted line: the forced environment assignments followed by the resolved
    binary and its arguments, ready to paste into a terminal or pipe into a shell.
    See the plan-mode branch of {meth}`CLIExecutor.run`.
    """
    env_prefix = "".join(
        f"{name}={shlex.quote(str(value))} "
        for name, value in (extra_env or {}).items()
    )
    command = " ".join(shlex.quote(str(arg)) for arg in cmd_args)
    return f"{env_prefix}{command}"


class _PlanRecorder:
    """Thread-safe sink for the mutating commands captured under `mpm --plan`.

    {meth}`CLIExecutor.run` records into it from the fan-out's worker threads
    (hence the lock); the CLI drains it once, on the main thread, when the context
    closes (see the plan-mode wiring in {func}`meta_package_manager.cli.mpm`).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: list[tuple[str, str]] = []

    def reset(self) -> None:
        """Drop any commands left over from a previous in-process invocation."""
        with self._lock:
            self._commands.clear()

    def record(self, manager_id: str, command: str) -> None:
        """Store one captured `command` attributed to `manager_id`."""
        with self._lock:
            self._commands.append((manager_id, command))

    def render(self) -> tuple[str, ...]:
        """Return the captured commands grouped by manager ID.

        The sort is stable, so each manager keeps the order its commands were
        captured in (a manager runs its own commands serially), while the managers
        themselves are ordered deterministically regardless of the concurrent
        capture order across the fan-out.
        """
        with self._lock:
            ordered = sorted(self._commands, key=lambda entry: entry[0])
        return tuple(command for _manager_id, command in ordered)


PLAN_RECORDER: Final = _PlanRecorder()
"""Process-wide sink for {meth}`CLIExecutor.run`'s plan-mode captures.

A module-level singleton because `run` executes in the fan-out's worker threads,
where the click context is not reliably reachable. See {class}`_PlanRecorder`.
"""


def highlight_cli_name(path: Path | None, match_names: Iterable[str]) -> str | None:
    """Highlight the binary name in the provided `path`.

    The name is only highlighted when it matches one of the recognized
    `match_names`, so an unrecognized binary stays plain. Matching is
    insensitive to case on Windows and case-sensitive on other platforms, thanks
    to `os.path.normcase`.

    The rendering is delegated to
    {func}`click_extra.execution.highlight_bin_name`, the same helper behind
    the `$`-prompt and spawn-trace log lines, so the `mpm managers` table and
    the logs can never drift apart.
    """
    if path is None:
        return None

    if any(
        os.path.normcase(ref_name).startswith(os.path.normcase(path.name))
        for ref_name in match_names
    ):
        return highlight_bin_name(str(path))
    return str(path)


READ_ONLY_TIMEOUT: Final = 120
"""Default timeout (seconds) for read-only probes and queries.

These operations only inspect state, so a short cap lets a wedged binary fail fast
instead of stalling the whole run. The value is generous enough for legitimately
slow scans (a freshly-pulled `guix search` walking every package's metadata)
while still being far below {data}`MUTATING_TIMEOUT`.
"""

MUTATING_TIMEOUT: Final = 500
"""Default timeout (seconds) for operations that change system state.

Installs, upgrades, removals, channel syncs and cleanups routinely build from
source, download large archives or pull entire channels, so they need a long cap.
Kept identical to the historical global default so these operations behave exactly
as before when no explicit `--timeout` is given.
"""

DEFAULT_TIMEOUT: Final = MUTATING_TIMEOUT
"""Fallback timeout (seconds) for a CLI call whose operation is unknown.

Defaults to the conservative {data}`MUTATING_TIMEOUT`: when in doubt, wait
rather than risk killing a legitimate long-running command.
"""

OPERATION_TIMEOUTS: Final[dict[str, int]] = {
    VERSION_PROBE: READ_ONLY_TIMEOUT,
    "installed": READ_ONLY_TIMEOUT,
    "outdated": READ_ONLY_TIMEOUT,
    "orphans": READ_ONLY_TIMEOUT,
    "search": READ_ONLY_TIMEOUT,
    "install": MUTATING_TIMEOUT,
    "upgrade": MUTATING_TIMEOUT,
    "upgrade_all": MUTATING_TIMEOUT,
    "remove": MUTATING_TIMEOUT,
    "sync": MUTATING_TIMEOUT,
    "cleanup": MUTATING_TIMEOUT,
    # Read-only by contract, but deep integrity scans (`pkg check --checksums`)
    # outlast the read-only cap, and a timeout kill would misreport as ill health.
    "doctor": MUTATING_TIMEOUT,
}
"""Per-operation timeout defaults, applied only when the user has set no explicit
`--timeout` (or per-manager `timeout` override).

Keyed by the {class}`meta_package_manager.capabilities.Operations` member name,
plus the special `"version"` detection probe. The keys are validated against the
`Operations` enum by the test suite so the two never drift apart. An operation
absent from this map resolves to {data}`DEFAULT_TIMEOUT`.
"""

SPINNER_DELAY: Final = 0.1
"""Seconds a CLI call must run before its progress spinner appears.

Kept short so the spinner surfaces almost immediately on any call that is not
instant: prompt feedback makes `mpm` feel responsive from the start rather than
stalled during the first second. Only the quickest calls (cached version probes,
trivial metadata queries) finish within this delay and stay silent; anything
slower (a `guix search`, a source build) shows the spinner right away.
"""


class CLIExecutor:
    """Locate a manager's CLI on the system and run it.

    Mixin inherited by {class}`meta_package_manager.manager.PackageManager`. Owns the
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
        multiple versions of the same executable were named `python` or `python3`.

    By default, this property's value is derived from the manager's ID (see the
    `MetaPackageManager.__init__` method above).
    """

    cli_search_path: tuple[str, ...] = ()
    """List of additional path to help {program}`mpm` hunt down the package manager CLI.

    Must be a list of strings whose order dictates the search sequence.

    Most of the time unnecessary:
    {func}`meta_package_manager.manager.PackageManager.cli_path` works well on all
    platforms.
    """

    extra_env: ClassVar[TEnvVars | None] = None
    """Additional environment variables to add to the current context.

    Automatically applied on each
    {func}`meta_package_manager.manager.PackageManager.run_cli` calls.
    """

    pre_cmds: tuple[str, ...] = ()
    """Global list of pre-commands to add before before invoked CLI.

    Automatically added to each
    {func}`meta_package_manager.manager.PackageManager.run_cli` call.

    Used to prepend [sudo](https://www.sudo.ws) or other system utilities.
    """

    pre_args: tuple[str, ...] = ()
    post_args: tuple[str, ...] = ()
    """Global list of options used before and after the invoked package manager CLI.

    Automatically added to each
    {func}`meta_package_manager.manager.PackageManager.run_cli` call.

    Essentially used to force silencing, low verbosity or no-color output.
    """

    version_cli_options: tuple[str, ...] = ("--version",)
    """CLI options used to produce the version of the package manager.

    The raw output produced by the package manager CLI will be parsed with the
    {attr}`version_regexes <meta_package_manager.manager.PackageManager.version_regexes>`
    below to extract the version number.
    """

    version_cli: str | None = None
    """Alternate binary probed for the manager's version, instead of the main CLI.

    Some manager suites expose no version flag on any of their own binaries (OpenBSD's
    `pkg_add`/`pkg_info`, Solaris' `pkgadd`/`pkginfo`): they ship with the base
    system and are versioned with the OS itself. Naming a `version_cli` (like
    `uname`) makes the version probe run that binary with
    {attr}`version_cli_options` and parse its output with
    {attr}`version_regexes`, while every operation keeps using the manager's own
    {attr}`cli_path`. The binary is resolved with
    {meth}`~meta_package_manager.manager.PackageManager.which`; the version resolves
    to `None` (manager not {attr}`fresh
    <meta_package_manager.manager.PackageManager.fresh>`) when it is not found.
    """

    version_regexes: tuple[str, ...] = (r"(?P<version>\S+)",)
    """Regular expressions used to extract the version number.

    This property must be a tuple of strings, each of which is a valid regular
    expression that must contain a [group](https://docs.python.org/3/library/re.html#index-18) named `<version>`.

    The first of these regexes producing a match and returning non-empty `<version>`
    group will be used as the version string of the package manager.

    That version string will then be sanitized and normalized by
    {func}`meta_package_manager.manager.PackageManager.version`.

    By default match the first part that is space-separated.

    ```{caution}
    These regexes are compiled with {data}`re.MULTILINE` only. They are
    *not* compiled with {data}`re.VERBOSE`, so literal whitespace in the
    pattern is significant and matches whitespace in the CLI output.
    ```
    """

    stop_on_error: bool = False
    """Tell the manager to either raise or continue on errors."""

    dry_run: bool = False
    """Do not actually perform any action, just simulate CLI calls."""

    plan: bool = False
    """Capture state-changing CLI calls for inspection instead of running them.

    Set by `mpm --plan`. Unlike {attr}`dry_run` (which simulates *every* call,
    read-only queries included), plan mode lets the read-only queries (`installed`,
    `outdated`, `search`) run for real so the resolved plan reflects actual
    system state, and records only the state-changing commands (see
    {data}`_MUTATING_OPERATIONS`) into {data}`PLAN_RECORDER`.
    """

    timeout: int | None = None
    """Maximum number of seconds to wait for a CLI call to complete.

    `None` means the user expressed no explicit preference: the effective cap is
    then resolved per-operation by `_resolve_timeout()` from
    {data}`OPERATION_TIMEOUTS`. A non-`None` value (the `--timeout` flag or a
    per-manager override) wins for every operation.
    """

    _active_operation: str | None = None
    """Name of the operation this manager is currently performing.

    Stamped by {meth}`meta_package_manager.pool.ManagerPool._select_managers`
    just before the manager is handed to a subcommand, and by the {attr}`version`
    probe. Consumed by {meth}`_resolve_timeout` to pick a per-operation default.
    `None` (no known operation) falls back to {data}`DEFAULT_TIMEOUT`.
    """

    progress: bool = False
    """Whether CLI calls may show a progress spinner while they block.

    Set by the CLI to an interactive, human-facing run only (a TTY, no serialized
    output, not at DEBUG verbosity). Even when `True` the spinner still
    self-suppresses off a TTY: see `_make_spinner()`. Defaults to `False` so
    programmatic use stays silent.
    """

    cooldown: timedelta | None = None
    """Minimum age a release must have before it can be installed or upgraded.

    When set, the manager refuses to bring in any package version published more
    recently than `cooldown` ago. This is a mitigation against supply-chain
    attacks: a malicious release is typically detected and pulled within days of
    publication, so a waiting period keeps freshly-published (and potentially
    compromised) versions out of the system. `None` disables the gate.

    Only managers able to natively enforce a release-age limit honor this; see
    {attr}`cooldown_env_var` and {attr}`supports_cooldown`.
    """

    require_cooldown_support: bool = True
    """Require native {attr}`cooldown` support to run install/upgrade.

    By default (`True`, fail-closed), when a {attr}`cooldown` is requested,
    install and upgrade operations are skipped for managers lacking native
    release-age support, so nothing slips in unguarded. Setting this to `False`
    opts into running those operations anyway, without the safeguard.
    """

    sudo: bool | None = None
    """User escalation policy: run this manager's privileged commands with `sudo`.

    `None` (the default) means the user expressed no preference, so the built-in
    {attr}`default_sudo` decides. `True`/`False` force escalation on or off for
    every operation this manager marks privileged (a `build_cli(..., sudo=True)` call).
    Set globally by `mpm --sudo` / `mpm --no-sudo` and per manager by the
    `[mpm.managers.<id>] sudo` config key, the latter winning (see
    {meth}`meta_package_manager.pool.ManagerPool._select_managers`).

    Only privileged operations on UNIX are ever escalated. A manager that escalates
    *internally* ({attr}`internal_sudo`) has no such markers and is never wrapped
    in `sudo` by `mpm`: its own `sudo` reuses the credential cache when
    {func}`~meta_package_manager.sudo.prime_sudo` finds it already warm, and is
    otherwise covered by the silent-call notice in {meth}`run`.
    """

    default_sudo: bool = False
    """Built-in escalation default, used when {attr}`sudo` is `None`.

    `False` on the base: most managers install into user-writable trees and never need
    root. The system package managers whose privileged operations require root (`apt`,
    `dnf`, `pacman`, `zypper`, ...) set this to `True` so their
    `build_cli(..., sudo=True)` operations escalate out of the box, while staying
    switchable off through {attr}`sudo` (`--no-sudo` or config) for rootless setups.
    """

    internal_sudo: bool = False
    """Marks a manager whose CLI invokes `sudo` itself mid-run.

    Homebrew `cask` runs it from installer artifacts, `fink` re-execs its
    root commands through it, and the AUR helpers call `sudo pacman` for their
    install steps. mpm never wraps such a manager's commands: either none of its
    operations carry a `build_cli(..., sudo=True)` marker (`cask`, `fink`),
    or its `default_sudo = False` policy leaves the markers it inherits
    unescalated (the AUR helpers). Running the tool under `sudo` is often
    forbidden outright (`brew` refuses root, `makepkg` refuses to build).
    Consumed by {func}`~meta_package_manager.sudo.prime_sudo`, whose
    opportunistic probe keeps an already-warm credential cache alive for these
    internal escalations, and by the silent-call notice in {meth}`run`, which
    flags a possibly-hidden password prompt on a cold cache.

    Forcing `sudo = true` on such a manager (config key or `--sudo`) still
    never wraps its commands, but does promote it into the up-front prompt path of
    {func}`~meta_package_manager.sudo.prime_sudo`.
    """

    cooldown_env_var: ClassVar[str | None] = None
    """Environment variable this manager reads to honor a {attr}`cooldown`.

    `None` (the default) means the manager has no native release-age mechanism and
    cannot honor a cooldown. A subclass that sets this string advertises support (see
    {attr}`supports_cooldown`); the value produced by {meth}`cooldown_env_value`
    is then injected into the environment of every CLI call.
    """

    windows_creation_flags: int = 0
    """Additional Windows process creation flags OR-ed with `CREATE_NO_WINDOW`.

    Use this on individual managers to control how their subprocess is attached
    to the calling process's console. For example, setting this to
    `subprocess.DETACHED_PROCESS` (`0x8`) fully detaches the child from the
    parent's console. Any grandchild process (like a COM server or installer EXE)
    that calls `GenerateConsoleCtrlEvent(0)` on exit will then fail silently
    because there is no console to broadcast to.

    No-op on non-Windows platforms (`getattr` returns `0` for Windows-only flags).
    """

    windows_processes_to_cleanup: tuple[str, ...] = ()
    """Windows process image names to forcibly terminate after each CLI call.

    When a package manager spawns grandchild processes that outlive the direct
    subprocess (like winget's `WindowsPackageManagerServer.exe` COM server),
    those orphans can linger and consume resources. List the image names here so
    they are killed after `communicate()` returns.

    No-op on non-Windows platforms.
    """

    cli_errors: list[CLIError]
    """Accumulate all CLI errors encountered by the package manager."""

    _last_run: tuple[int, str, str] | None = None
    """`(exit code, <stdout>, <stderr>)` of the most recent completed {meth}`run`.

    `None` until a run completes, and reset to `None` at the start of each run, so
    a spawn that never finished (timeout, interrupt, missing binary) leaves no stale
    result behind. Consumed by
    {meth}`meta_package_manager.manager.PackageManager.doctor`, whose health verdict
    is the exit code alone and whose report merges both streams: the return value of
    {meth}`run` carries neither. Safe to read right after the call under mpm's
    dispatch model, where a manager never runs two of its own invocations at once.
    """

    run_cache: dict[tuple, tuple[int, str, str]] | None = None
    """Optional cache that de-duplicates identical CLI runs within a lock family.

    `None` by default, which disables caching: every {meth}`run` call spawns its own
    subprocess. {func}`meta_package_manager.dispatch.dispatch` injects one shared dict
    into all the managers of a multi-manager lock-family lane (see
    {data}`meta_package_manager.dispatch.SHARED_LOCK_FAMILIES`) for the duration of
    that lane, so members resolving to a byte-identical command (`brew` and `cask`
    both running `brew update` for {command}`mpm sync`) run the subprocess once and
    replay the cached `(code, output, error)` for the rest. The replay still walks
    {meth}`run`'s logging and failure gate, so a failed shared command is attributed
    to every member. Keyed on the resolved command line and its environment, so only
    genuinely identical invocations collapse.
    """

    def __init__(self) -> None:
        """Initialize `cli_errors` list."""
        self.cli_errors = []

    @property
    def supports_cooldown(self) -> bool:
        """Whether this manager can natively enforce a release-age {attr}`cooldown`."""
        return self.cooldown_env_var is not None

    def cooldown_env_value(self) -> str:
        """Render {attr}`cooldown` as the value of {attr}`cooldown_env_var`.

        Defaults to the RFC 3339 timestamp of the most recent release date still
        allowed, i.e. now minus the cooldown. Managers whose environment variable
        expects another format (a number of minutes, a bare day count, ...) override
        this.
        """
        assert self.cooldown is not None
        cutoff = datetime.now(tz=timezone.utc) - self.cooldown
        return cutoff.isoformat()

    def cooldown_rounded_up(self, unit_seconds: int) -> str:
        """Render {attr}`cooldown` as an integer count of `unit_seconds`-long
        units, rounded up.

        Helper for the {meth}`cooldown_env_value` overrides of managers whose native
        release-age knob expects a unit count rather than the default RFC 3339 timestamp
        (npm's day-based `min-release-age`, pnpm's minute-based `minimumReleaseAge`).
        Sub-unit cooldowns round up so the gate over-protects rather than silently
        collapsing to `0` (the "no cooldown" sentinel).
        """
        assert self.cooldown is not None
        return str(math.ceil(self.cooldown.total_seconds() / unit_seconds))

    def cooldown_env(self) -> TEnvVars:
        """Environment fragment enforcing the {attr}`cooldown`, empty when inactive.

        Returns an empty mapping unless a {attr}`cooldown` is set *and* the manager
        supports it. Merged into the environment of every {meth}`run` call.
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

        This is like our own implementation of `shutil.which()`, with the difference
        that it is capable of returning all the possible paths of the provided file
        names, in all environment path, not just the first one that match. And on
        Windows, prevents matching of CLI in the current directory, which takes
        precedence on other paths.

        Returns all files matching any `cli_names`, by iterating over all folders in
        this order:

        * folders provided by {attr}`cli_search_path
          <meta_package_manager.manager.PackageManager.cli_search_path>`,
        * then in all the default places specified by the environment variable (i.e.
          `os.getenv("PATH")`).

        Only returns files that exists and are not empty.

        ```{caution}

        Symlinks are not resolved, because some manager like [Homebrew on Linux relies on some sort of symlink-based trickery](https://github.com/kdeldycke/meta-package-manager/pull/188) to set
        environment variables.
        ```
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
        # But on Windows, there is this special `PATHEXT` environment variable to
        # tell you what file suffixes are executable. We have to search for any
        # variation of the CLI name with any of these suffixes.
        # Code below is inspired by the original implementation of `shutil.which()`:
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

            Additonnaly use `os.path.normcase` on Windows to exclude duplicates
            produced by case-insensitive filesystems.
            """
            return os.path.normcase(path.resolve())

        # Deduplicate search paths while keeping their order and original value, as the
        # normalization process happens with the `key` lookup.
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
        """Emulates the `which` command.

        Based on the `search_all_cli()` method.
        """
        for cli_path_found in self.search_all_cli([cli_name]):
            return cli_path_found
        return None

    def sibling_cli(self, name: str, *, same_dir: bool = False) -> Path:
        """Resolve the path of a sibling binary of the manager's main CLI.

        Some managers ship as a suite of binaries (`xbps-install`/`xbps-query`,
        `pkg_add`/`pkg_info`, emerge's `qlist`): an operation then runs a
        sibling instead of the main CLI. By default the sibling is searched like the
        main CLI itself ({meth}`which`, honoring {attr}`cli_search_path`), and
        a missing binary raises {exc}`FileNotFoundError` rather than silently
        falling back to the wrong program.

        `same_dir=True` instead takes the sibling from the directory of
        {attr}`cli_path`, without an existence probe: suites installing all
        their binaries side by side (XBPS, Nix) guarantee the neighbor, and
        resolving it from the same directory can never mix two installations. A
        genuinely missing file then surfaces at spawn time.
        """
        if same_dir:
            assert self.cli_path is not None
            return self.cli_path.parent / name
        sibling_path = self.which(name)
        if not sibling_path:
            msg = f"{name} not found"
            raise FileNotFoundError(msg)
        return sibling_path

    @cached_property
    def cli_path(self) -> Path | None:
        """Fully qualified path to the canonical package manager binary.

        Try each CLI names provided by {attr}`cli_names
        <meta_package_manager.manager.PackageManager.cli_names>`, in each system path
        provided by {attr}`cli_search_path
        <meta_package_manager.manager.PackageManager.cli_search_path>`. In that order.
        Then returns the first match.

        Executability of the CLI will be separately assessed later by the
        {func}`meta_package_manager.manager.PackageManager.executable` method below.
        """
        if self.cli_names is not None:
            for cli_path in self.search_all_cli(self.cli_names):
                return cli_path
        return None

    @cached_property
    def version(self) -> TokenizedString | None:
        """Invoke the manager and extract its own reported version string.

        Returns a parsed and normalized version in the form of a
        {class}`meta_package_manager.version.TokenizedString` instance.

        Skipped on platforms where the manager is not supported, even if
        {attr}`cli_path` resolved to an executable: that binary almost
        certainly belongs to a different tool that happens to share the
        same name (e.g. GNU `make` on macOS getting matched by the
        FreeBSD `ports` manager), so probing it would either misreport
        the version or surface confusing error output.
        """
        # `supported` is declared on the `PackageManager` subclass, not on
        # this mixin: mypy does not see it, but every concrete instance does.
        if not self.supported:  # type: ignore[attr-defined]
            return None
        if self.executable:
            # An alternate version binary must resolve, or the version is unknowable.
            version_cli_path = None
            if self.version_cli:
                version_cli_path = self.which(self.version_cli)
                if not version_cli_path:
                    logging.debug(f"Version binary {self.version_cli!r} not found.")
                    return None
            # Version detection is a fast liveness probe, so tag it as a read-only
            # operation: a wedged binary then trips the short timeout instead of the
            # long mutating one. Safe to leave set: `_select_managers` re-stamps the
            # real operation before any subcommand runs, and an explicit `--timeout`
            # still wins inside `_resolve_timeout`.
            self._active_operation = VERSION_PROBE
            output = self.run_cli(
                self.version_cli_options,
                override_cli_path=version_cli_path,
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

    @contextmanager
    def acting_as(
        self,
        operation: str | None = None,
        *,
        stop_on_error: bool | None = None,
    ) -> Iterator[None]:
        """Temporarily adjust the manager's execution state, restoring it on exit.

        `operation` re-stamps {attr}`_active_operation` (the per-operation
        timeout and watchdog key) for the duration of the block; `None` leaves
        the current stamp untouched. `stop_on_error` likewise overrides the
        failure policy when set: the per-package state changers run their action
        under `stop_on_error=True` so a botched operation raises and is recorded
        by the caller instead of being silently accumulated.

        The public seam for callers needing a scoped state override: the CLI
        layer must never poke {attr}`_active_operation` or {attr}`stop_on_error`
        directly.
        """
        previous_operation = self._active_operation
        previous_stop = self.stop_on_error
        if operation is not None:
            self._active_operation = operation
        if stop_on_error is not None:
            self.stop_on_error = stop_on_error
        try:
            yield
        finally:
            self._active_operation = previous_operation
            self.stop_on_error = previous_stop

    def _resolve_timeout(self) -> int:
        """Resolve the timeout (in seconds) for the current CLI call.

        Precedence, most specific first:

        1. An explicit {attr}`timeout` (the user's `--timeout` flag or a
           per-manager `timeout` override) wins for every operation.
        2. Otherwise the per-operation default keyed on {attr}`_active_operation`
           (see {data}`OPERATION_TIMEOUTS`).
        3. An unknown operation falls back to {data}`DEFAULT_TIMEOUT`.
        """
        if self.timeout is not None:
            return self.timeout
        if self._active_operation is None:
            return DEFAULT_TIMEOUT
        return OPERATION_TIMEOUTS.get(self._active_operation, DEFAULT_TIMEOUT)

    def _make_spinner(self) -> Spinner:
        """Build a (not-yet-started) progress spinner for the current CLI call.

        The label combines the manager ID and the active operation, so a slow call
        reads like the command it runs (`guix search`, `brew install`). The
        spinner is disabled unless {attr}`progress` is set; even then it only
        animates on a TTY (see {class}`click_extra.Spinner`), so it stays silent
        when output is piped or captured.
        """
        manager_id = self.id  # type: ignore[attr-defined]
        operation = self._active_operation
        label = f"{manager_id} {operation}" if operation else str(manager_id)
        # Append the elapsed time so a long call (a slow `guix search`) reads as
        # "⠙ guix search (12.3s)" rather than looking stuck.
        return Spinner(
            label,
            delay=SPINNER_DELAY,
            enabled=None if self.progress else False,
            timer=True,
        )

    def _cleanup_windows_processes(self) -> None:
        """Forcibly terminate the lingering grandchildren this manager is known to
        leave behind on Windows (see {attr}`windows_processes_to_cleanup`).

        No-op on non-Windows platforms and for managers with no cleanup list.
        """
        if not is_any_windows():
            return
        for proc_name in self.windows_processes_to_cleanup:
            subprocess.run(
                ("taskkill", "/F", "/T", "/IM", proc_name),
                capture_output=True,
                timeout=5,
                check=False,
            )

    def run(
        self,
        *args: TArg | TNestedArgs,
        extra_env: TEnvVars | None = None,
        must_succeed: bool = False,
    ) -> str:
        """Run a shell command, return the output and accumulate error messages.

        `args` is allowed to be a nested structure of iterables, in which case it will
        be recursively flatten, then `None` will be discarded, and finally each item
        casted to strings.

        Running commands with that method takes care of:
          * disclosing the invocation at `INFO` (the reproducible `$`-prompt
            line with forced environment variables) and streaming the raw output
            live to `DEBUG`, prefixed with the manager ID, via
            {func}`click_extra.execution.run_cli`
          * flagging, on a terminal, the mutating call of an internal escalator
            that goes silent on a cold credential cache and may be blocked on a
            hidden password prompt (see
            {class}`~meta_package_manager.sudo._StallWatchdog`)
          * detaching every other call into its own POSIX session and process
            group, so a timeout or Ctrl+C reaps the whole process tree and a
            wedged grandchild cannot linger as an orphan; the flagged call
            above keeps the controlling terminal so its `sudo` prompt stays
            answerable
          * removing ANSI escape codes from
            {attr}`subprocess.CompletedProcess.stdout` and
            {attr}`subprocess.CompletedProcess.stderr`
          * returning ready-to-use normalized strings (dedented and stripped)
          * letting `mpm --dry-run` and `mpm --stop-on-error` have
            expected effect on execution

        :param must_succeed: if `True`, raise
            {class}`meta_package_manager.manager.CLIError` when the command
            fails, regardless of the user-facing {attr}`stop_on_error`
            preference, rather than accumulating the error for an end-of-run
            summary. Use for calls whose output is parsed (JSON, XML, regex),
            where a swallowed failure would be indistinguishable from empty
            results. A non-zero exit that leaves `<stderr>` empty is tolerated
            as a benign status code (`npm` and `pnpm outdated` exit `1`
            when updates exist); only the per-package state changers, which run
            under a patched {attr}`stop_on_error`, treat every non-zero exit
            as a failure. See the failure gate below for details.
        """
        # Reset the last-run snapshot so an early return (timeout, interrupt,
        # missing binary) cannot leave a stale result for the consumers below.
        self._last_run = None
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
            # Replay the peer's result: the subprocess is skipped, but the failure
            # gate below still runs, so this manager is marked like the peer. INFO,
            # like the command disclosure it stands in for: it explains why this
            # manager shows no prompt line of its own.
            code, output, error = cached
            logging.info(f"Reuse lock-family peer result: {cli_msg}")
        elif self.plan and self._active_operation in _MUTATING_OPERATIONS:
            # Plan mode: record the state-changing command for inspection instead of
            # running it. Read-only queries (and force_exec calls, which patch plan
            # off) fall through to real execution below, so the plan resolves against
            # actual system state. See _MUTATING_OPERATIONS and PLAN_RECORDER.
            # `id` is declared on the `PackageManager` subclass, not this mixin.
            plan_command = format_plan_command(clean_args, extra_env)
            PLAN_RECORDER.record(self.id, plan_command)  # type: ignore[attr-defined]
        elif self.dry_run and not self.plan:
            logging.warning(f"Dry-run: {cli_msg}")
        else:
            # `id` is declared on the `PackageManager` subclass, not this mixin.
            manager_id: str = self.id  # type: ignore[attr-defined]
            # The invocation is disclosed at INFO so `--verbosity INFO` shows (and
            # lets the user reproduce) every CLI mpm runs on the system. The
            # version-detection probes stay at DEBUG: they are discovery, fired
            # for every candidate manager, and would drown the narration.
            command_level = (
                logging.DEBUG
                if self._active_operation == VERSION_PROBE
                else logging.INFO
            )
            effective_timeout = self._resolve_timeout()
            spinner = self._make_spinner()
            # A mutating command of an internal escalator (cask, fink) may block
            # on a hidden `sudo` password prompt when prime_sudo() found no warm
            # credential cache to keep alive. Arm the stall watchdog around the
            # spawn so the silence is flagged, on the terminal where the prompt
            # waits, while it can still be answered.
            watchdog = None
            if (
                self.internal_sudo
                and self._active_operation in _STALL_NOTICE_OPERATIONS
                and sys.stderr.isatty()
                and not _SUDO_CACHE_WARM.is_set()
            ):
                watchdog = _StallWatchdog(manager_id)
            try:
                # run_cli() owns the spawn: it registers the child in click-extra's
                # live-process registry (so the SIGINT handler installed by mpm's
                # CLI terminates it on Ctrl+C), streams the raw output to DEBUG
                # logs line by line (prefixed with the manager ID), and enforces
                # the timeout. The spinner wraps the whole call; its 0.1s delay
                # keeps it invisible while the invocation line is disclosed.
                try:
                    with spinner:
                        result = run_cli(
                            clean_args,
                            extra_env=extra_env,
                            timeout=effective_timeout,
                            label=manager_id,
                            command_level=command_level,
                            windows_creation_flags=self.windows_creation_flags,
                            # Detach the child into its own POSIX session and
                            # process group, so timeout and Ctrl+C kill the
                            # whole tree and a wedged grandchild (mas) cannot
                            # linger as an orphan. The armed watchdog marks the
                            # one call that may legitimately prompt: it keeps
                            # the controlling terminal, or the internal sudo
                            # could not reach /dev/tty. mpm's own escalations
                            # run sudo --non-interactive and never prompt, so
                            # they always detach. No-op on Windows.
                            start_new_session=watchdog is None,
                            # The tee routes each streamed record through the
                            # armed watchdog before the root logger. `None` is
                            # run_cli's default, the untouched root-logger path.
                            log=watchdog.tee if watchdog is not None else None,
                        )
                finally:
                    # Disarm on every exit of the spawn: success, spawn failure,
                    # timeout and Ctrl+C all stop the notice thread before their
                    # handlers below log their own diagnosis.
                    if watchdog is not None:
                        watchdog.stop()
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
            except subprocess.TimeoutExpired:
                # The spinner was stopped by the `with` teardown as the exception
                # propagated, so the warning below lands on a clean line. run_cli
                # already killed the child: its whole POSIX process group when
                # detached into its own session, its whole tree on Windows.
                self._cleanup_windows_processes()
                msg = f"Timed out after {effective_timeout}s."
                logging.warning(msg, extra={"label": manager_id})
                exception = CLIError(None, "", msg)
                if must_succeed or self.stop_on_error:
                    raise exception
                self.cli_errors.append(exception)
                return ""
            except KeyboardInterrupt:
                # run_cli killed the child before re-raising; the spinner was
                # stopped by the `with` teardown.
                msg = "Subprocess interrupted by a console signal."
                logging.warning(msg, extra={"label": manager_id})
                exception = CLIError(None, "", msg)
                self.cli_errors.append(exception)
                return ""
            code = result.returncode
            output = result.stdout or ""
            error = result.stderr or ""
            self._cleanup_windows_processes()

        # Publish a freshly produced result — real or dry-run — so lock-family peers
        # replay it instead of re-running, collapsing identical invocations even under
        # --dry-run (where the first member logs the command and the rest are silent
        # cache hits). Skipped when this run was itself a hit. Normalization below is
        # idempotent, so caching the raw result here is equivalent.
        if cache is not None and cached is None:
            cache[cache_key] = (code, output, error)

        # Normalize messages. The raw streams were already narrated live to DEBUG
        # by run_cli, so nothing is re-dumped here: what follows only shapes the
        # returned value for parsing.
        if error:
            error = dedent(strip_ansi(error).strip())
        if output:
            output = dedent(strip_ansi(output).strip())

        # Snapshot the completed run for consumers needing more than the returned
        # <stdout>: the exit code and <stderr> (see the attribute docstring).
        self._last_run = (code, output, error)

        # Detect a failed run.
        #
        # By default a non-zero exit code is only treated as a failure when the
        # command *also* wrote to <stderr>. Many read-only CLIs use a non-zero
        # code as a status while writing their payload to <stdout> and leaving
        # <stderr> empty: `npm` and `pnpm outdated` exit 1 when updates
        # exist. Flagging those would break the parsing of their output, so a
        # silent <stderr> earns the benefit of the doubt.
        #
        # The per-package state changers (install/remove/upgrade <packages>/
        # restore) cannot afford that tolerance. They run under a patched
        # `stop_on_error` with `must_succeed` left False, and there a
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
            # for my password?"). The tailored message stands in for the generic
            # diagnosis relay below: the raw "password is required" tail carries
            # less than the fix.
            is_escalation = clean_args[:2] == _SUDO_ESCALATION_PREFIX
            if is_escalation and _is_sudo_auth_failure(error):
                logging.warning(
                    "Needs administrator rights but sudo has no cached "
                    "credentials; re-run in a terminal, or with `mpm --sudo` to "
                    "authenticate once up front.",
                    extra={"label": self.id},  # type: ignore[attr-defined]
                )
            # Relay the command's own account of the failure at WARNING, the
            # moment it happened: the diagnosis is in hand right here, and a
            # mutating operation cannot be re-run at DEBUG to regenerate it (the
            # failed run may have half-applied its changes, and a cooldown may
            # block the retry). Only a *failed* run earns the relay: a successful
            # command's <stderr> chatter stays at DEBUG. Also skipped at DEBUG
            # verbosity, where run_cli already streamed the raw output inline.
            # See https://github.com/kdeldycke/meta-package-manager/issues/1968.
            elif (
                self._active_operation not in _DIAGNOSIS_EXEMPT_OPERATIONS
                and logging.getLogger().getEffectiveLevel() > logging.DEBUG
            ):
                logging.warning(
                    exception.diagnosis,
                    extra={"label": self.id},  # type: ignore[attr-defined]
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
        """Build the package manager CLI by combining the custom `*args` with the
        package manager's global parameters.

        Returns a tuple of strings.

        Helps the construction of CLI's repeating patterns and makes the code easier to
        read. Just pass the specific `*args` and the full CLI string will be composed
        out of the globals, following this schema:

        ```{code-block} shell-session

        $ [<pre_cmds>|sudo --non-interactive] <cli_path> <pre_args> <*args> <post_args>
        ```

        * {attr}`self.pre_cmds <meta_package_manager.manager.PackageManager.pre_cmds>`
          is added before the CLI path.

        * {attr}`self.cli_path <meta_package_manager.manager.PackageManager.cli_path>`
          is used as the main binary to execute.

        * {attr}`self.pre_args <meta_package_manager.manager.PackageManager.pre_args>`
          and {attr}`self.post_args
          <meta_package_manager.manager.PackageManager.post_args>`  globals are added
          before and after the provided `*args`.

        Each additional set of elements can be disabled with their respective flag:

        * `auto_pre_cmds=False`  to skip the automatic addition of
          {attr}`self.pre_cmds <meta_package_manager.manager.PackageManager.pre_cmds>`
        * `auto_pre_args=False`  to skip the automatic addition of
          {attr}`self.pre_args <meta_package_manager.manager.PackageManager.pre_args>`
        * `auto_post_args=False` to skip the automatic addition of
          {attr}`self.post_args <meta_package_manager.manager.PackageManager.post_args>`

        Each global set of elements can be locally overridden with:

        * `override_pre_cmds=tuple()`
        * `override_cli_path=str`
        * `override_pre_args=tuple()`
        * `override_post_args=tuple()`

        On UNIX, an operation marked privileged (`sudo=True`) is escalated only when
        the per-manager policy opts in ({attr}`sudo`, falling back to
        {attr}`default_sudo`). It is then run through [sudo](https://www.sudo.ws)
        with `--non-interactive` (it spends the credential cache warmed by
        {func}`~meta_package_manager.sudo.prime_sudo` and fails fast rather than
        blocking on a password prompt).
        When escalation applies, `override_pre_cmds` is not allowed to be set and
        `auto_pre_cmds` is forced to `False`. A non-UNIX host never escalates.
        """
        # Apply delegation overrides if set by a DelegatedMethod descriptor.
        delegate_path = getattr(self, "_delegate_cli_path", None)
        if delegate_path is not None:
            override_cli_path = override_cli_path or delegate_path
            auto_post_args = False

        params: list[TArg | TNestedArgs] = []

        # Resolve whether this privileged operation is actually escalated: the caller
        # marks the operation as needing root (`sudo`), the per-manager policy opts in
        # (the `sudo` override, else `default_sudo`), and the platform has `sudo`.
        # A non-UNIX host simply does not escalate rather than raising.
        escalate = bool(sudo and _resolved_sudo(self) and current_platform() in UNIX)
        # Sudo replaces any pre-command, be it overridden or automatic.
        # `--non-interactive` spends the credential cache warmed up front by
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
        """Build and run the package manager CLI by combining the custom `*args` with
        the package manager's global parameters.

        After the CLI is built with the
        {meth}`meta_package_manager.manager.PackageManager.build_cli` method, it is
        executed with the {meth}`meta_package_manager.manager.PackageManager.run`
        method, augmented with environment variables from {attr}`self.extra_env
        <meta_package_manager.manager.PackageManager.extra_env>`.

        All parameters are the same as
        {meth}`meta_package_manager.manager.PackageManager.build_cli`, plus:

        * `auto_extra_env=False` to skip the automatic addition of
          {attr}`self.extra_env <meta_package_manager.manager.PackageManager.extra_env>`
        * `override_extra_env=dict()` to locally overrides the later
        * `force_exec` ignores the `mpm --dry-run`, `mpm --stop-on-error`
          and `mpm --plan` options to force the execution and completion of the
          command. It is used for reads whose output is needed regardless (version
          detection, `yarn global dir`), which must run for real even when the
          user asked to simulate or to only plan mutations.
        * `must_succeed` raises on non-zero exit regardless of
          `mpm --stop-on-error`. See {meth}`run` for details.
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

        # Temporarily lift the --dry-run, --stop-on-error and --plan user options
        # to force this read to run and complete (see the force_exec note in the
        # docstring above), restoring them right after.
        if force_exec:
            previous = (self.dry_run, self.stop_on_error, self.plan)
            self.dry_run = self.stop_on_error = self.plan = False
            try:
                return self.run(*cli, extra_env=extra_env, must_succeed=must_succeed)
            finally:
                self.dry_run, self.stop_on_error, self.plan = previous

        return self.run(*cli, extra_env=extra_env, must_succeed=must_succeed)
