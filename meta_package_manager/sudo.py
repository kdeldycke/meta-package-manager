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

This module owns `sudo` credential priming ({func}`prime_sudo`) and its
background keepalive ({func}`_start_sudo_keepalive`), escalation-policy
resolution ({func}`_resolved_sudo`), sudo-failure detection
({func}`_is_sudo_auth_failure`), and the hidden-prompt stall watchdog
({class}`_StallWatchdog`). The execution engine
({mod}`meta_package_manager.execution`) consumes the policy pieces to wrap and
diagnose escalated commands; the CLI calls {func}`prime_sudo` at the top of
each mutating subcommand.

Why priming exists: a concurrent state-changing command mutes per-manager output
and feeds each child `stdin=/dev/null`, so a `sudo` password prompt raised
mid-run (by mpm's own `sudo --non-interactive` or by a manager that escalates
internally, like
Homebrew `cask`) lands invisibly on `/dev/tty` and can stall the run up to the
mutating timeout. Priming first probes the credential cache non-interactively:
found warm, it is silently kept alive for the whole run; found cold on a terminal,
the managers mpm itself escalates get a single up-front password prompt, naming
them and branded `[mpm]`. Internal escalators never prompt up front: their rare
cold-cache escalation is covered by the silent-call stall notice instead, raised
while the hidden prompt can still be answered.

```{note}
Everything in this module is UNIX-only: a Windows run returns early at
{func}`prime_sudo`'s guard and never arms the watchdog (the internal
escalators are macOS-only managers today).
```

```{todo}
Add `run0` and `pkexec` to {data}`ESCALATORS`, and `gsudo` for Windows, once
a user asks for one: `sudo` and `doas` cover the hosts that ship an escalator
in base today. Each needs its own probe and prompt argv and its own refusal
wordings, the way `doas` needed both. Emulate an option a backend cannot
express rather than failing on it: topgrade returns a hard error there, which
its users report as a bug
([topgrade-rs/topgrade#1435](https://github.com/topgrade-rs/topgrade/issues/1435)).
Windows needs more than a table entry, since {func}`prime_sudo` returns
before any of this on that platform.
```

```{todo}
Escalate to the user owning a manager's tree, not only to root. Every
{attr}`~Escalator.escalate_args` reaches root alone, so a manager installed
under another user's home (a shared Homebrew prefix on Linux, a nix profile
owned by someone else) has no route: `sudo --user` is what such a tree needs,
and `doas -u` its equivalent.
```

```{todo}
Decide escalation from the ownership of the target tree instead of a static
flag. `_resolved_sudo` reads a boolean, so the dormant privileged markers of
`pip`, `npm`, `gem` and `cpan` only wake through a global `--sudo` that
escalates every other selected manager too. Probing whether each install
root is really root-owned would let them escalate on their own evidence, and
skip with an explanation when the root belongs to the user.
```

```{todo}
Rebrand the hidden password prompt of an internal escalator with a
`SUDO_ASKPASS` helper, once the stall notice of `_StallWatchdog` proves
insufficient in the field. It is also the only route serving a hardened
`sudoers` policy, whose timestamps the primed cache cannot reach (see
`_SUDO_CACHE_WARM`). That class records why the helper was rejected first,
and any implementation has to answer the same three points: the raw password
it handles, the spinner it must pause, and the tools it never reaches
(`brew` honors the variable, `fink`'s plain `sudo` re-exec does not).
```
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import cache
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

Counted on a terminal, during a mutating call of a manager that runs `sudo`
internally ({attr}`CLIExecutor.internal_sudo
<meta_package_manager.execution.CLIExecutor.internal_sudo>`). Long enough that
ordinary quiet stretches (dependency resolution, download lulls that still tick
progress lines) rarely trip it, yet far below
{data}`~meta_package_manager.execution.MUTATING_TIMEOUT`, so the user gets the
hint while the hidden password prompt can still be answered. See
{class}`_StallWatchdog`.
"""

_STALL_NOTICE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"install", "remove", "upgrade", "upgrade_all"},
)
"""Operations whose commands may block on an interactive internal `sudo`.

Matched against {attr}`CLIExecutor._active_operation
<meta_package_manager.execution.CLIExecutor._active_operation>` when arming the
stall watchdog: the mutating operations whose installers may escalate mid-flight
(`restore` stamps `"install"`, so it is covered). `sync` and `cleanup` are
excluded on purpose, to avoid false notices on `brew update`/`brew cleanup`,
whose long silent phases never escalate. The trade-off is a known gap: `fink`
does re-exec `fink selfupdate`/`fink cleanup` through `sudo`, so a cold-cache
`mpm sync`/`mpm cleanup` of `fink` can still stall unflagged on a hidden
prompt.
"""

_SUDO_CACHE_WARM: Final = threading.Event()
"""Set while the priming keepalive believes the credential cache is warm.

Armed by {func}`_start_sudo_keepalive` and cleared when the context closes. A warm
cache serves internal escalations ({attr}`CLIExecutor.internal_sudo
<meta_package_manager.execution.CLIExecutor.internal_sudo>`) silently, so the
silent-call stall watchdog skips arming while this flag is set.

The keepalive keeps the flag honest mid-run: a refresh that finds the
credentials gone clears it, with one warning per drop, so later spawns arm the
watchdog again, and a refresh that succeeds after a re-authentication sets it
back. Homebrew is the known cache killer: every `brew` command resets the
`sudo` timestamp at startup, on purpose (see `docs/sudo.md`).

```{note}

The flag records that `mpm` holds a validated credential, assuming sudo's default
timestamp semantics. Under a hardened sudoers policy (`timestamp_timeout=0`, or a
`timestamp_type` keyed to the process rather than the terminal) a manager's own
child `sudo` may not be able to spend that credential, and its mid-run prompt then
goes unflagged. Priming still authenticates; only the watchdog is suppressed.
```
"""

@dataclass(frozen=True)
class Escalator:
    """One privilege-escalation binary, and the argv dialects mpm drives it with.

    Everything specific to an escalator lives here, so the rest of the module
    reasons about escalation without naming a binary. The dialects are not
    interchangeable: `doas` is not a `sudo` clone with another name, it takes
    short options only and has no way to authenticate without running a command.
    """

    id: str
    """The binary's name, and the value the `sudo_command` override selects it by."""

    escalate_args: tuple[str, ...]
    """Argv prefix escalating a manager command, non-interactively.

    Non-interactive on purpose: a prompt raised inside the concurrent fan-out
    lands on a terminal nobody is watching (see {func}`prime_sudo`). Emitted by
    {meth}`CLIExecutor.build_cli
    <meta_package_manager.execution.CLIExecutor.build_cli>` and matched back by
    {meth}`CLIExecutor.run <meta_package_manager.execution.CLIExecutor.run>` to
    recognize an escalation failure, so the two sites must stay in lockstep.
    """

    probe_args: tuple[str, ...]
    """Argv reading the credential cache without ever prompting.

    `sudo` answers this without running anything (`--validate`); `doas` has no
    such mode, so it runs `true` as the cheapest harmless command.
    """

    prompt_args: tuple[str, ...]
    """Argv authenticating the user up front, interactively, once per run."""

    refreshable: bool
    """Whether {attr}`probe_args` can also serve as a keepalive tick.

    True only where the escalator caches credentials on a schedule mpm can
    reason about. `doas` persistence is opt-in per rule in `doas.conf`, so a
    recurring probe would report a drop on every tick for the majority of hosts,
    where no rule asks for it. Those escalators get no keepalive thread at all.
    """

    brands_prompt: bool
    """Whether the escalator can be told what password prompt to print.

    `sudo --prompt` can; `doas` cannot. The notice {func}`prime_sudo` echoes
    before authenticating names the managers either way, so an unbranded prompt
    loses the `[mpm]` marker, not the explanation.
    """


ESCALATORS: Final[tuple[Escalator, ...]] = (
    Escalator(
        id="sudo",
        escalate_args=("sudo", "--non-interactive"),
        probe_args=("sudo", "--non-interactive", "--validate"),
        prompt_args=("sudo", "--validate"),
        refreshable=True,
        brands_prompt=True,
    ),
    Escalator(
        id="doas",
        # `doas` parses short options only, so the long-form convention of
        # `docs/cli-parameters.md` cannot apply here: `-n` is the whole
        # vocabulary for "do not prompt".
        escalate_args=("doas", "-n"),
        probe_args=("doas", "-n", "true"),
        prompt_args=("doas", "true"),
        refreshable=False,
        brands_prompt=False,
    ),
)
"""Every escalator mpm can drive, in the order it prefers them.

`sudo` comes first so a host carrying both keeps the behavior it has today, and
the `sudo_command` override exists for the user who wants the other one. The
order only decides auto-detection: an explicit override always wins.
"""

_SUDO_KEEPALIVE_INTERVAL: Final = 60
"""Seconds between `sudo --non-interactive --validate` credential-cache
refreshes during a run.

Comfortably under sudo's default `timestamp_timeout` (5 minutes), so the cache warmed
by {func}`prime_sudo` stays valid for the whole command. A host configured with a
shorter `timestamp_timeout` may still see a mid-run escalation re-prompt or fail.
"""

_SUDO_PRIMED: Final = "mpm_sudo_primed"
"""`ctx.meta` key marking that {func}`prime_sudo` already ran this invocation."""


@cache
def resolve_escalator(override: str | None = None) -> Escalator | None:
    """The escalator mpm drives, or `None` when the host carries none.

    With no `override`, returns the first entry of {data}`ESCALATORS` whose
    binary is on `PATH`, so a host without `sudo` still escalates through
    whatever it does have. An `override` names one by its
    {attr}`~Escalator.id` and is honored even when the binary is missing, so
    the failure names the escalator the user asked for instead of silently
    falling back to another one.

    Cached on the override, since `PATH` does not move mid-run. Tests changing
    what is installed must call `resolve_escalator.cache_clear()`.
    """
    if override is not None:
        for escalator in ESCALATORS:
            if escalator.id == override:
                return escalator
        # An unknown name is a configuration error, not a reason to escalate
        # through something the user did not ask for.
        logging.warning(
            f"Unknown sudo_command {override!r}: expected one of "
            f"{', '.join(e.id for e in ESCALATORS)}. Managers needing root may fail.",
        )
        return None
    for escalator in ESCALATORS:
        if shutil.which(escalator.id):
            return escalator
    return None


def _resolved_sudo_command(managers: Iterable[CLIExecutor]) -> str | None:
    """The `sudo_command` override shared by `managers`, if any set one.

    The override is a global choice that the pool copies onto every selected
    manager, so the first value found speaks for the run.
    """
    for manager in managers:
        if manager.sudo_command is not None:
            return manager.sudo_command
    return None


def _resolved_sudo(manager: CLIExecutor) -> bool:
    """Whether `manager` escalates: its
    {attr}`~meta_package_manager.execution.CLIExecutor.sudo` override if set,
    else its built-in
    {attr}`~meta_package_manager.execution.CLIExecutor.default_sudo`."""
    return manager.sudo if manager.sudo is not None else manager.default_sudo


def _names_an_escalator(error: str) -> bool:
    """Whether `error` is prefixed by one of the escalators mpm drives.

    Both matchers below key on wordings plain enough to appear in an unrelated
    command's output (`doas` reports an unauthorized user as the bare errno
    string `Operation not permitted`), so they only trust a line the escalator
    signed with its own name.
    """
    return any(f"{escalator.id}:" in error for escalator in ESCALATORS)


def _is_sudo_auth_failure(error: str) -> bool:
    """Whether the escalator is refusing to authenticate non-interactively.

    `sudo --non-interactive` and `doas -n` write one of these to `<stderr>` when
    they have no cached credentials
    and cannot prompt for a password (nothing cached, no controlling terminal, no
    askpass helper). Lets {meth}`CLIExecutor.run
    <meta_package_manager.execution.CLIExecutor.run>` turn an opaque escalation
    failure into an actionable hint.

    The wordings are not interchangeable across implementations: `sudo-rs`, the
    Rust rewrite Ubuntu ships as the default `sudo` since `25.10`, answers
    `sudo: interactive authentication is required` where the original says
    `sudo: a password is required`. Matching only the latter left every
    escalation failure on a current Ubuntu unrecognized, and the hint unprinted.
    """
    lowered = error.lower()
    return _names_an_escalator(lowered) and any(
        marker in lowered
        for marker in (
            "a password is required",
            "a terminal is required",
            "interactive authentication is required",
            "no tty present",
            "askpass",
            # Three `doas` wordings, identical in OpenBSD's own `doas.c` and in
            # opendoas: `-n` meeting a rule without `nopass` answers
            # `Authentication required`, a password prompt with no terminal to
            # read from answers `a tty is required` (where sudo says *terminal*,
            # already matched above), and a rejected password answers
            # `Authentication failed`.
            "authentication required",
            "a tty is required",
            "authentication failed",
        )
    )


def _is_sudo_denied(error: str) -> bool:
    """Whether `error` is `sudo` reporting the user is not authorized to run it.

    Distinct from {func}`_is_sudo_auth_failure`: an authentication failure means
    the cache is cold and a password would unblock, while a denial means the
    `sudoers` policy grants this user nothing, so a prompt could only collect a
    password `sudo` then rejects. {func}`prime_sudo` skips its up-front prompt on
    a denial.

    The detection is opportunistic: some `sudo` configurations reveal the denial
    to a non-interactive `--validate` while others hide it behind `a password is
    required` (authenticating before disclosing authorization), and the hidden
    case simply keeps today's prompt-then-fail path. The markers cover, in
    order: `sudo` since `1.9` (`is not allowed to run sudo on`, per its message
    catalog), `sudo` before `1.9` and `sudo-rs`'s validate denial (`may not run
    sudo on`, `src/common/error.rs`), the historic sudoers lecture (`is not in
    the sudoers file`), and both implementations' per-command denial (`is not
    allowed to execute`), and `doas`, which reports the bare errno string of
    `EPERM` instead.
    """
    lowered = error.lower()
    if any(
        marker in lowered
        for marker in (
            "is not allowed to run sudo",
            "may not run sudo",
            "is not in the sudoers file",
            "is not allowed to execute",
        )
    ):
        return True
    # Two opendoas answers, both measured on a runner and both leaving nothing
    # for a password to fix. An unmatched rule ends in `errc(1, EPERM, NULL)`,
    # printing the bare errno string of EPERM and nothing more specific; a
    # missing `doas.conf` ends in `err(1, "doas is not enabled, %s")`, which is
    # what an installed-but-unconfigured host answers (`doas.c`). The errno
    # string is one any command could print, so both count only on a line doas
    # signed. The sudo wordings above need no such guard: each already names
    # sudo itself, and sudo prefixes none of them.
    return _names_an_escalator(lowered) and (
        "operation not permitted" in lowered or "is not enabled" in lowered
    )


def _start_sudo_keepalive(ctx: Context, escalator: Escalator) -> None:
    """Keep the credential cache of `escalator` fresh for the rest of the invocation.

    Marks the cache warm whatever the escalator, but only spawns the refreshing
    thread for a {attr}`~Escalator.refreshable` one: an escalator whose
    persistence is opt-in per rule would report a drop on every tick of a host
    that never asked for it, which is noise rather than news. The flag can then
    go stale, exactly as its own docstring already admits for a hardened
    `sudoers` policy.

    Refreshes the cache every {data}`_SUDO_KEEPALIVE_INTERVAL` seconds so a long
    fan-out does not outlast sudo's timestamp and re-prompt mid-flight. Output is
    captured so a failed refresh cannot smear the aggregate spinner drawing on
    stderr. Sets {data}`_SUDO_CACHE_WARM` for the run, and keeps it honest: a
    refresh finding the credentials gone (a manager reset them, Homebrew does on
    every command, or a strict `sudoers` policy expired them) clears the flag and
    warns, once per drop, so the stall watchdog re-arms for later spawns; a
    refresh succeeding again, after the user re-authenticates in this terminal,
    sets it back. The refresh never re-prompts by design: only a command that
    needs the credentials may. The daemon thread is stopped and the flag cleared
    when the context closes (normal exit or Ctrl+C both run close callbacks).
    """
    stop = threading.Event()

    def keepalive() -> None:
        while not stop.wait(_SUDO_KEEPALIVE_INTERVAL):
            refresh = subprocess.run(
                escalator.probe_args,
                capture_output=True,
                check=False,
            )
            # A refresh racing the teardown must not touch the flag the
            # teardown just cleared.
            if stop.is_set():
                break
            if refresh.returncode == 0:
                if not _SUDO_CACHE_WARM.is_set():
                    logging.info("The sudo credentials are warm again.")
                else:
                    logging.debug("Refreshed the sudo credentials.")
                _SUDO_CACHE_WARM.set()
            elif _SUDO_CACHE_WARM.is_set():
                _SUDO_CACHE_WARM.clear()
                logging.warning(
                    "The sudo credentials primed for this run are gone: a "
                    "manager reset them (every Homebrew command does) or the "
                    "sudoers policy expired them. Managers needing root may "
                    "prompt or fail.",
                )
            else:
                logging.debug("The sudo credentials are still gone.")

    _SUDO_CACHE_WARM.set()
    if not escalator.refreshable:
        logging.info(
            f"{escalator.id} credentials cannot be refreshed on a schedule: "
            "they hold for as long as its own persistence rules say.",
        )
        ctx.call_on_close(_SUDO_CACHE_WARM.clear)
        return

    logging.info(f"Keeping the {escalator.id} credentials fresh for the whole run.")
    thread = threading.Thread(target=keepalive, daemon=True)
    thread.start()

    def teardown() -> None:
        stop.set()
        # The thread leaves its wait promptly once stopped; join it so a
        # refresh still in flight cannot set the flag back after the clear
        # below. The timeout bounds a Ctrl+C exit if sudo itself wedges.
        thread.join(timeout=2)
        _SUDO_CACHE_WARM.clear()

    ctx.call_on_close(teardown)


def prime_sudo(ctx: Context, managers: Iterable[PackageManager]) -> None:
    """Warm the `sudo` credential cache, up front, for a mutating fan-out.

    Probes the cache non-interactively (`sudo --non-interactive --validate`)
    before considering any
    prompt. A warm cache (pre-authenticated `sudo --validate`, a `NOPASSWD` rule, a
    recent run) is silently kept fresh for the whole invocation by
    {func}`_start_sudo_keepalive`, so every later escalation on the same
    terminal, mpm's own `sudo --non-interactive` as well as a manager's internal
    `sudo`
    ({attr}`CLIExecutor.internal_sudo
    <meta_package_manager.execution.CLIExecutor.internal_sudo>`), spends the cache
    instead of blocking on an invisible prompt inside the concurrent fan-out. Only
    a cold cache, on an interactive terminal, with managers that mpm itself
    escalates ({func}`_resolved_sudo`), triggers the interactive path: a notice
    naming the managers and the subcommand, then a single branded `sudo` password
    prompt.

    Before probing, the binary of each manager mpm escalates is audited with the
    same tamper test the config loader applies
    ({func}`~meta_package_manager.config.config_file_is_trusted`): a binary that
    others can modify, handed to `sudo`, runs their code as root, so it draws one
    warning per manager (see `docs/security.md`).

    Call at the top of each mutating subcommand, before the fan-out draws its
    spinner. Never prompts when:

    - Windows (no `sudo`) or the process is already root,
    - no selected manager escalates, through mpm or internally,
    - a dry run or a plan run (no state-changing CLI is executed),
    - already primed once this invocation (idempotent),
    - the `sudo` executable is missing (one warning is logged),
    - the probe finds the cache already warm (keepalive only, fully silent),
    - the probe reports the user is not authorized to run `sudo` at all
      ({func}`_is_sudo_denied`): one warning names the managers mpm escalates and
      the remedy, since a prompt could only collect a password `sudo` then
      rejects, while an internal-only selection stays silent,
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

    escalator = resolve_escalator(_resolved_sudo_command(managers))
    if escalator is None:
        # No escalator on PATH at all, or an override naming an unknown one
        # (which logged its own warning). Let unprivileged managers proceed.
        if escalating:
            logging.warning(
                f"Found none of {', '.join(e.id for e in ESCALATORS)} to escalate "
                f"{', '.join(escalating)} with: they may fail. Install one, or "
                "drop escalation with `--no-sudo` or a `[mpm] sudo = false` "
                "entry in your configuration file.",
            )
        return

    # Deferred on purpose: `config` pulls in the definitions machinery, which
    # imports back into this module through `manager` and `execution`.
    from .config import config_file_is_trusted

    for manager in managers:
        if not _resolved_sudo(manager):
            continue
        # The same file-plus-parent tamper test the config loader applies (see
        # `docs/security.md`): a binary that others can modify, handed to
        # `sudo`, runs their code as root. The warning does not block: like the
        # risky-override warning, existing setups keep working.
        cli_path = manager.cli_path
        if cli_path is not None and not config_file_is_trusted(cli_path):
            logging.warning(
                f"About to run {cli_path} as root, but it is not owned by you "
                "or root, or others can write to it or its directory. Fix its "
                "ownership and permissions, or drop escalation with "
                "`--no-sudo`.",
                extra={"label": manager.id},
            )

    try:
        logging.debug(
            f"Probe the {escalator.id} credential cache: "
            f"{' '.join(escalator.probe_args)}",
        )
        probe = subprocess.run(
            escalator.probe_args,
            capture_output=True,
            check=False,
        )
    except OSError:
        # Not on PATH (FileNotFoundError), or one that cannot be run: not executable
        # for this user (PermissionError), not a valid binary (OSError). Degrade to a
        # warning and let unprivileged managers proceed rather than crash.
        logging.warning(
            f"{escalator.id} could not be run: managers needing root may fail. "
            "Drop escalation with `--no-sudo` or a `[mpm] sudo = false` entry in "
            "your configuration file.",
        )
        return
    if probe.returncode == 0:
        # Cache already warm (a prior authentication, a passwordless rule):
        # keep it fresh,
        # silently. A CI job with pre-cached credentials thus gets the keepalive
        # instead of the no-terminal warning.
        logging.info(
            f"Found the {escalator.id} credential cache warm: no password prompt "
            "needed.",
        )
        _start_sudo_keepalive(ctx, escalator)
        return

    ids = ", ".join(escalating)
    probe_error = (probe.stderr or b"").decode("UTF-8", errors="replace")
    # The raw answer settles which cold case this is, and catches a wording no
    # matcher knows yet (the sudo-rs precedent, see _is_sudo_auth_failure).
    logging.debug(f"The {escalator.id} probe answered: {probe_error.strip()!r}")
    if _is_sudo_denied(probe_error):
        if escalating:
            logging.warning(
                f"{ids} need{'s' if len(escalating) == 1 else ''} administrator "
                f"rights, but you are not authorized to run {escalator.id} on "
                "this host: they will fail. Drop escalation with `--no-sudo` or "
                "a `[mpm] sudo = false` entry in your configuration file.",
            )
        # An internal-only selection stays silent, as on the no-terminal path:
        # each manager's own sudo surfaces the denial through its error path.
        return

    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        if escalating:
            logging.warning(
                f"{ids} need{'s' if len(escalating) == 1 else ''} administrator "
                "rights, but no terminal is available to prompt for a password: "
                f"they may fail. Re-run in a terminal, pre-authenticate with "
                f"`{' '.join(escalator.prompt_args)}`, or drop escalation with "
                "`--no-sudo` or a `[mpm] sudo = false` entry in your "
                "configuration file.",
            )
        # An internal-only selection stays silent: each manager's own sudo fails
        # fast and surfaces through its error path.
        return

    if not escalating:
        # Internal-only selection on a cold cache (a stock macOS cask/fink run):
        # return without prompting. Most such runs never escalate, so an up-front
        # password prompt on every run would be the mirror-image regression. The
        # silent-call stall notice covers the rare mid-run prompt instead.
        logging.info(
            "Only managers running sudo internally are selected, on a cold "
            "credential cache: no up-front prompt, the stall notice covers a "
            "hidden one.",
        )
        return

    echo(
        f"{ids} need{'s' if len(escalating) == 1 else ''} administrator rights to "
        f"{ctx.command.name}: enter your password.",
        err=True,
    )
    prompt_cli = escalator.prompt_args
    if escalator.brands_prompt:
        # `sudo --prompt` expands %-escapes; manager IDs are plain slugs, so the
        # escaping is belt-and-braces. An escalator that cannot be told what to
        # print falls back to its own prompt, under the notice echoed above.
        prompt = f"[mpm] password for {ids}: ".replace("%", "%%")
        prompt_cli = (*prompt_cli, "--prompt", prompt)
    if subprocess.run(prompt_cli, check=False).returncode != 0:
        logging.warning(
            f"Could not acquire {escalator.id} credentials: managers needing root "
            "may fail.",
        )
        return
    _start_sudo_keepalive(ctx, escalator)


class _StallWatchdog(logging.Handler):
    """Warn when a CLI call that may hide a `sudo` password prompt goes silent.

    A manager that escalates internally ({attr}`CLIExecutor.internal_sudo
    <meta_package_manager.execution.CLIExecutor.internal_sudo>`) can raise a
    `sudo` prompt from inside its own commands. The child reads `stdin` from
    `/dev/null` and its output streams to `DEBUG` logs, so on a cold
    credential cache the prompt lands invisibly on `/dev/tty`: the run looks
    stuck until the mutating timeout kills it. When {func}`prime_sudo` left the
    cache cold, or the keepalive later found it dropped mid-run,
    {meth}`CLIExecutor.run
    <meta_package_manager.execution.CLIExecutor.run>` arms this watchdog around
    the spawn: once {data}`_STALL_NOTICE_DELAY` seconds pass without a fresh
    output line, a daemon thread logs one `WARNING` naming the manager and
    quoting its last line, so the user can tell a hidden prompt from a slow
    download and answer it on the terminal while it still waits. Each silence
    episode warns at most once; a fresh line starts a new episode.

    The watchdog doubles as the sole handler of {attr}`tee`, the logger
    {meth}`CLIExecutor.run <meta_package_manager.execution.CLIExecutor.run>`
    hands to {func}`click_extra.execution.run_cli` in place of the root logger:
    {meth}`emit` tracks the child's activity, then forwards every record
    verbatim to the root logger, whose level click-extra's `--verbosity`
    manages, keeping the display byte-identical to an un-teed run at every
    verbosity.

    ```{note}

    Considered alternative: a `SUDO_ASKPASS` helper. `brew` documents
    passing `--askpass` to its internal `sudo` whenever that variable is
    set, so mpm could export a helper into the child environment and rebrand
    the hidden prompt itself ("[mpm] cask needs your password..."). Rejected:
    the helper reads the raw password and pipes it to `sudo` (a security
    surface this notice avoids entirely), it needs a side channel to pause
    the spinner that would smear its prompt, and it only covers tools
    honoring the variable (`brew` does, `fink`'s plain `sudo` re-exec
    does not). The scoped `sudo = true` opt-in documented in `docs/sudo.md`
    already covers users wanting a guaranteed up-front prompt.
    ```
    """

    tee: logging.Logger
    """Stand-in destination for `run_cli`'s streamed records while armed.

    Deliberately a direct {class}`logging.Logger` construction, never
    {func}`logging.getLogger`: unregistered, each armed call gets a private tee
    that concurrent calls cannot cross-contaminate; parentless, its records cannot
    propagate straight to the root handlers, which would bypass the root level
    gate and leak `DEBUG` lines at default verbosity. Its `DEBUG` level lets
    every record reach {meth}`emit`: dropping is the root logger's decision.
    """

    def __init__(self, manager_id: str) -> None:
        """Arm the watchdog for one CLI call of `manager_id`."""
        super().__init__()
        self._manager_id = manager_id
        self._started = time.monotonic()
        # Latest child activity, one `(monotonic timestamp, output line)` pair.
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
        """Track child activity, then forward `record` verbatim to the root.

        Only the streamed output lines refresh the activity state: they are the
        records carrying a `label` attribute (`run_cli` labels the child's
        output lines only, never its own prompt-disclosure or PID-tracking lines),
        and only genuine output vouches that the child is not blocked on a prompt.

        Forwarding re-enters {meth}`logging.Logger.log` on the root logger so
        its level gate (the one click-extra's `--verbosity` manages) and its
        handlers apply exactly as if `run_cli` had logged there directly.
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
