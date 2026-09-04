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
Add a Windows escalator, `gsudo` or the `sudo.exe` shipping with Windows 11
`24H2`. Two things block it, and neither is a {data}`ESCALATORS` entry.
{func}`prime_sudo` returns before any of this machinery on that platform, so
Windows has to join it first. And nothing there answers
{attr}`~Escalator.probe_args`, which reads an exit code: `gsudo status --json`
reports `IsElevated` and `CacheAvailable` without prompting, exactly the
question worth asking, but it exits `0` whatever the answer is, so reading it
means parsing output.

Measured against `gsudo 2.6.1` on Windows 11 `21H2`, so an implementation need
not rediscover it: stdout and exit codes pass through faithfully; a failed
elevation exits `999`, truncated to `231` through a POSIX caller, and says
`Error: Unable to connect to the elevated service.`, naming neither `gsudo` nor
`sudo`; and `gsudo --version` opens `gsudo v2.6.1`, which is the identity
marker. Neither backend can fail instead of prompting, both gating on a UAC
dialog, and asking for a password on the command line is an open request
upstream ([microsoft/sudo#7](https://github.com/microsoft/sudo/issues/7)).

Three traps to encode: `gsudo -n` means *new window* rather than
non-interactive, its cache is scoped to the calling process unless `--pid 0`
widens it, and Windows' own `sudo` defaults to `forceNewWindow`, which breaks
output capture and needs `sudo run --inline`. Emulate an option a backend
cannot express rather than failing on it: topgrade returns a hard error there,
which its users report as a bug
([topgrade-rs/topgrade#1435](https://github.com/topgrade-rs/topgrade/issues/1435)).
```

```{todo}
Escalate to the user owning a manager's tree, not only to root: every
{attr}`~Escalator.escalate_args` reaches root alone, where `sudo --user` and
`doas -u` could reach the owner. The one legitimate case is a multi-user nix
install, whose foreign-owned profiles are a first-class upstream
configuration. A shared Homebrew prefix is not: Homebrew's
[support tiers](https://docs.brew.sh/Support-Tiers) file "Multi-user Homebrew
environments where multiple users share the same installation" as
unsupported, so smoothing that setup over (as topgrade does for its brew
step) would carry a burden upstream itself refuses. Stays unbuilt until a
nix user asks.
```

```{todo}
Rebrand the hidden password prompt of an internal escalator with a
`SUDO_ASKPASS` helper, once the stall notice of `_StallWatchdog` proves
insufficient in the field. It is also the only route serving a hardened
`sudoers` policy, whose timestamps the primed cache cannot reach (see
`_SUDO_CACHE_WARM`). That class records why the helper was rejected first,
and any implementation has to answer its two remaining points: the raw
password it handles, and the tools it never reaches (`brew` honors the
variable, `fink`'s plain `sudo` re-exec does not). The third, a still
terminal for the prompt, {func}`_hidden_prompt_risk` now provides.
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
    from pathlib import Path

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

    passwordless_probe_args: tuple[str, ...] | None
    """Argv asking whether *one named command* runs without a password, or `None`.

    Completed with the command's path by {func}`_escalation_is_passwordless`.
    `sudo --list -- <command>` answers precisely, reporting the command when the
    policy grants it unauthenticated and failing under `--non-interactive` when a
    password would be wanted. `doas` has no such query and gets `None`.

    Needed because {attr}`probe_args` answers a *different* question. `sudo
    --validate` refuses whenever any matching `sudoers` entry requires a
    password, even when the entry that would actually run the command is tagged
    `NOPASSWD`. openSUSE stacks exactly that pair: its stock `ALL ALL=(ALL) ALL`
    sits under the `NOPASSWD` rule `docs/sudo.md` recommends, so `--validate`
    reports a cold cache on a host where every escalation in fact runs untouched,
    and mpm warned that managers "may fail" before they went on to succeed.
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

    identity_args: tuple[str, ...] | None = None
    """Argv proving the binary on `PATH` is this escalator, not a stand-in.

    A name on `PATH` is not proof of the dialect behind it: Alpine's
    `doas-sudo-shim` installs `/usr/bin/sudo` as a shell script forwarding to
    `doas`, and it accepts `--non-interactive` alone out of everything mpm
    sends. So {attr}`escalate_args` works there while every probe dies on
    `unrecognized option`, and mpm reads that as a cold credential cache on a
    host where escalation in fact runs untouched.

    Run by {meth}`is_genuine`, which needs the argv to authenticate nothing and
    to cost nothing: `sudo --version` reports the build and exits `0` on real
    sudo, where the shim rejects the option and exits `1`. `None` where no
    stand-in is known, which is every escalator but `sudo`.
    """

    identity_markers: tuple[str, ...] | None = None
    """Substrings {attr}`identity_args` prints when the binary is genuine, any
    one of which is proof.

    Matched against `<stdout>` on a zero exit. Kept beside the argv because
    exit status alone is too weak a signal: a stand-in free to accept the
    option would pass on the returncode.

    Several markers rather than one because a reimplementation brands its own
    banner: `sudo --version` prints `Sudo version 1.9.17` on the original and
    `sudo-rs 0.2.13` on the Rust rewrite Ubuntu ships as its default `sudo`
    since `25.10`. Matching the first alone rejected sudo-rs as a stand-in, and
    {func}`resolve_escalator` then fell through to `doas` on a host carrying
    both, inverting the documented preference. Upstream's `SUDO_RS_VERSION`
    override replaces the number and never the `sudo-rs` prefix, so the prefix
    is what the second marker keys on.

    Both markers are the ones sudo-rs itself sorts the two implementations by:
    its test framework reads the same banner, stripping `Sudo version ` to
    recognize the original and treating everything else as its own
    (`test-framework/sudo-test/src/lib.rs`).
    """

    def resolved_probe_args(self) -> tuple[str, ...]:
        """{attr}`probe_args`, with any `{pid}` token replaced by mpm's own id.

        Only `pkexec` needs it. Its probe is `pkcheck`, polkit's own
        authorization query, which asks about a *subject* rather than about the
        caller and refuses to guess one: without `--process` it exits `126` on
        `Subject not specified`. Every other escalator answers for whoever runs
        it and carries no token, so the substitution is a no-op there.
        """
        pid = str(os.getpid())
        return tuple(arg.replace("{pid}", pid) for arg in self.probe_args)

    def is_genuine(self) -> bool:
        """Whether the binary on `PATH` really is this escalator.

        `True` when the escalator declares no {attr}`identity_args`, so an
        escalator opts into the check rather than out of it.
        """
        if not self.identity_args:
            return True
        try:
            probe = subprocess.run(
                self.identity_args,
                capture_output=True,
                check=False,
                text=True,
                encoding="UTF-8",
            )
        except OSError:
            # The binary vanished between `which()` and here, or is not
            # executable. Either way it cannot be driven.
            return False
        # `stdout` is `None` whenever the output was not captured, so it is
        # normalized rather than trusted to be a string.
        stdout = probe.stdout or ""
        return probe.returncode == 0 and any(
            marker in stdout for marker in self.identity_markers or ()
        )


ESCALATORS: Final[tuple[Escalator, ...]] = (
    Escalator(
        id="sudo",
        escalate_args=("sudo", "--non-interactive"),
        probe_args=("sudo", "--non-interactive", "--validate"),
        passwordless_probe_args=("sudo", "--non-interactive", "--list", "--"),
        prompt_args=("sudo", "--validate"),
        refreshable=True,
        brands_prompt=True,
        identity_args=("sudo", "--version"),
        identity_markers=("Sudo version", "sudo-rs"),
    ),
    Escalator(
        id="doas",
        # `doas` parses short options only, so the long-form convention of
        # `docs/cli-parameters.md` cannot apply here: `-n` is the whole
        # vocabulary for "do not prompt".
        escalate_args=("doas", "-n"),
        probe_args=("doas", "-n", "true"),
        passwordless_probe_args=None,
        prompt_args=("doas", "true"),
        refreshable=False,
        brands_prompt=False,
    ),
    Escalator(
        id="run0",
        # `--pipe` passes the caller's file descriptors straight through rather
        # than allocating a pseudo TTY, which is what keeps a captured listing
        # byte-clean and its exit code intact. run0 picks that mode on its own
        # when no descriptor is a TTY, so the switch only pins what it would
        # infer. The trailing `--` shields a manager's own flags from run0's
        # getopt, which would otherwise claim any it recognizes.
        escalate_args=("run0", "--pipe", "--no-ask-password", "--"),
        # No `--validate` before systemd 262, so the cheapest harmless command
        # stands in for one, exactly as it does for `doas`.
        probe_args=("run0", "--pipe", "--no-ask-password", "true"),
        passwordless_probe_args=None,
        prompt_args=("run0", "--pipe", "true"),
        # polkit owns the authorization and retains it per session, so there is
        # no timestamp for mpm to extend: `-v` creates one and `-k` revokes it,
        # and nothing refreshes one.
        refreshable=False,
        # The password prompt belongs to whichever polkit agent answers, built
        # from the action's own message. run0 has no `--prompt`, and
        # systemd/systemd#33902 asks for control over that text.
        brands_prompt=False,
        identity_args=("run0", "--version"),
        # run0 reports the systemd version it ships with, not one of its own.
        identity_markers=("systemd",),
    ),
    Escalator(
        id="pkexec",
        # No `--` separator: pkexec stops parsing at the first non-option and
        # would try to execute `--` itself. Nothing is at risk without one,
        # since the first argument mpm appends is the manager's absolute path,
        # which is already a non-option. `--keep-cwd` holds the working
        # directory, which pkexec otherwise resets to the target user's home.
        escalate_args=("pkexec", "--keep-cwd"),
        # pkexec carries no non-interactive switch and no validate mode: it
        # always executes a program, and asking it anything either prompts or
        # dies for want of an agent. `pkcheck` is polkit's own query tool and
        # the only way to read the answer without doing either, reporting `0`
        # when the action is authorized and `2` when it is not.
        probe_args=(
            "pkcheck",
            "--action-id",
            "org.freedesktop.policykit.exec",
            "--process",
            "{pid}",
        ),
        passwordless_probe_args=None,
        prompt_args=("pkexec", "--keep-cwd", "true"),
        # polkit owns retention, and the action pkexec defaults to is
        # `auth_admin` rather than `auth_admin_keep`, so nothing is kept at all
        # unless the host says otherwise.
        refreshable=False,
        brands_prompt=False,
    ),
    # ```{todo}
    # Carry {attr}`CLIExecutor.extra_env
    # <meta_package_manager.execution.CLIExecutor.extra_env>` through `run0`.
    # It runs the command in a fresh service that inherits nothing, so the four
    # managers injecting an environment lose it: `nala`, `tazpkg` and `urpmi`
    # each force `LC_ALL=C` to pin their parsers against a translated locale,
    # and `ports` forces `BATCH=yes` to stay out of an interactive dialog.
    # run0 reads `--setenv=NAME=VALUE`, but {meth}`CLIExecutor.build_cli
    # <meta_package_manager.execution.CLIExecutor.build_cli>` assembles the
    # argv without ever seeing the environment, which is resolved beside it,
    # so the splice needs that plumbed in first. Exposure is near zero
    # meanwhile: run0 is only ever selected on a host carrying neither `sudo`
    # nor `doas`, and all four of those managers ship on distributions that
    # carry `sudo`. A user who hits it can pin `--sudo-command sudo`.
    # ```
)
"""Every escalator mpm can drive, in the order it prefers them.

`sudo` comes first so a host carrying both keeps the behavior it has today, and
the `sudo_command` override exists for the user who wants the other one. The
order only decides auto-detection: an explicit override always wins.

`run0` comes last for the same reason, one step further: it needs a running
polkit to authorize anything, so a host carrying a working `sudo` or `doas`
keeps it, and run0 answers for the systemd hosts that ship neither.

`pkexec` closes the list, and auto-detection essentially never reaches it: it
ships wherever polkit does, which is nearly every desktop Linux, and those
carry `sudo` too. It is there for `--sudo-command pkexec`, and it only works
where a polkit rule already grants `org.freedesktop.policykit.exec`, since it
cannot escalate without prompting. The probe is what keeps that honest: a host
without the rule reports a cold cache and its managers decline to run, rather
than each of them stopping on a prompt inside the fan-out.
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
    binary is on `PATH` and passes {meth}`~Escalator.is_genuine`, so a host
    without `sudo` still escalates through whatever it does have, and one whose
    `sudo` is a stand-in for another escalator drives that other one directly.
    An `override` names one by its {attr}`~Escalator.id` and is honored even
    when the binary is missing, so the failure names the escalator the user
    asked for instead of silently falling back to another one.

    Cached on the override, since `PATH` does not move mid-run and the identity
    probe costs a subprocess. Tests changing what is installed must call
    `resolve_escalator.cache_clear()`.
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
    installed = tuple(e for e in ESCALATORS if shutil.which(e.id))
    for escalator in installed:
        if escalator.is_genuine():
            return escalator
    # Every installed escalator failed its identity probe. Falling back to the
    # first one still beats reporting none: a stand-in that answers no probe
    # usually still escalates, and Alpine's `doas-sudo-shim` only reaches this
    # line on a host whose `doas` was removed from under it.
    if installed:
        logging.debug(
            f"{installed[0].id} does not identify as itself: driving it anyway.",
        )
        return installed[0]
    return None


class _EscalationChoice:
    """Which escalator this process drives, resolved once per invocation.

    Escalation is a property of the machine, not of a manager: every manager
    that escalates on a given host escalates through the same binary. Keeping
    the choice here rather than on each manager is what makes that a statement
    the code makes rather than one a reader has to infer from every copy
    holding the same value.
    """

    def __init__(self) -> None:
        self._override: str | None = None

    def select(self, override: str | None) -> None:
        """Record the user's `--sudo-command`, or `None` to auto-detect.

        Called once at the top of the CLI group. It always assigns, so a
        previous in-process invocation (the test suite drives the CLI
        repeatedly) cannot leak its choice into this one.
        """
        self._override = override

    def resolve(self) -> Escalator | None:
        """The escalator to drive, or `None` when the host carries none."""
        return resolve_escalator(self._override)


ESCALATION: Final = _EscalationChoice()
"""Process-wide escalator selection.

A module-level singleton for the same reason as
{data}`~meta_package_manager.execution.PLAN_RECORDER`:
{meth}`CLIExecutor.build_cli
<meta_package_manager.execution.CLIExecutor.build_cli>` needs it from the
fan-out's worker threads, where the click context is not reliably reachable.
"""


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

    `run0` needs its own branch. It hands the refusal to systemd's bus layer,
    which signs it with neither `run0` nor any sudo wording, so the guard below
    would drop it. The prefix is stable across both refusal paths: polkit
    denying a `--no-ask-password` call answers `... Access denied as the
    requested operation requires interactive authentication`, and a denied
    interactive one answers the same `Access denied` alone. Both read as an
    authentication failure rather than a denial, which is the conservative
    call: a prompt may still authorize, and a user polkit grants nothing simply
    fails it, the same prompt-then-fail path a `sudo` hiding its denial takes.
    """
    lowered = error.lower()
    # The polkit-brokered pair sign nothing with their own name, so each is
    # matched on a phrase distinctive enough to stand without the guard below:
    # systemd's bus layer words run0's refusal, while pkexec's comes from the
    # authentication agent it failed to raise, or from the prompt a user
    # dismissed. A dismissal is an authentication failure and not a denial,
    # since answering the next one would authorize the call.
    if any(
        marker in lowered
        for marker in (
            "failed to start transient service unit: access denied",
            "error creating textual authentication agent",
            "error executing command as another user: request dismissed",
            "error executing command as another user: no authentication agent",
        )
    ):
        return True
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
    catalog), `sudo` before `1.9` and `sudo-rs`'s *list* denial (`may not run
    sudo on`, `src/common/error.rs`), the historic sudoers lecture (`is not in
    the sudoers file`), and both implementations' per-command denial (`is not
    allowed to execute`), and `doas`, which reports the bare errno string of
    `EPERM` instead.

    `sudo-rs` denies a `--validate` differently from a `--list`, which matters
    because {attr}`~Escalator.probe_args` runs the former first: a user no
    `sudoers` rule matches gets `I'm sorry {user}. I'm afraid I can't do that`
    (`Error::Authorization`) where `--list` says `may not run sudo`. Matching
    only the list wording left a non-sudoer on Ubuntu `25.10` and later being
    prompted for a password that could never authorize them.
    """
    lowered = error.lower()
    if any(
        marker in lowered
        for marker in (
            "is not allowed to run sudo",
            "may not run sudo",
            "is not in the sudoers file",
            "is not allowed to execute",
            # pkexec, where polkit answered rather than the user: a prompt
            # cannot change this one, unlike the dismissal it words otherwise.
            "error executing command as another user: not authorized",
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
    #
    # `sudo-rs`'s validate denial names no tool either, quoting HAL 9000
    # instead, so it joins the guarded group and rides the `sudo: ` prefix its
    # own diagnostic path writes.
    return _names_an_escalator(lowered) and (
        "operation not permitted" in lowered
        or "is not enabled" in lowered
        or "afraid i can't do that" in lowered
    )


def _is_permission_failure(error: str) -> bool:
    """Whether `error` reads as a filesystem permission refusal.

    Consumed by the failure gate of {meth}`CLIExecutor.run
    <meta_package_manager.execution.CLIExecutor.run>` to recognize a dormant
    privileged marker ({attr}`CLIExecutor._dormant_sudo
    <meta_package_manager.execution.CLIExecutor._dormant_sudo>`) meeting the
    root-owned tree it exists for. No `stat` of mpm's own is needed: the tool
    already performed the probe, and its own message usually names the very
    directory. The markers cover the wordings of the managers carrying dormant
    markers today: npm (`EACCES: permission denied, access
    '/usr/local/lib/node_modules'`), gem (`You don't have write permissions
    for the /Library/Ruby/Gems/3.4.0 directory`), and pip and cpan (plain
    `Permission denied` from the interpreter and the shell).
    """
    lowered = error.lower()
    return any(
        marker in lowered
        for marker in (
            "permission denied",
            "write permissions",
            "eacces",
        )
    )


@dataclass(frozen=True)
class InstallRoot:
    """Ownership snapshot of the tree a manager's global installs write into.

    Built by {func}`inspect_install_root` from a manager's own
    {attr}`~meta_package_manager.manager.PackageManager.install_root` probe.
    Diagnosis only, by decision: deciding escalation from this snapshot was
    assessed and rejected, since silently running a manager as root on
    filesystem evidence nobody reviewed is a posture change no diagnostic
    payoff justifies. The scoped `sudo = true` override stays the one road to
    escalating a dormant marker, and the failure-gate hint
    ({func}`_is_permission_failure`) is what names it.
    """

    path: Path
    """The install root itself."""

    owner_uid: int
    """Numeric owner of the root directory."""

    owner_name: str
    """The owner's account name, or the bare uid when no account matches."""


def inspect_install_root(manager: PackageManager) -> InstallRoot | None:
    """Resolve and stat `manager`'s install root, or `None` when unknowable.

    `None` covers every dead end: a non-POSIX host (the ownership model does
    not apply, and `pwd` does not exist), a manager with no discovery verb, a
    probe that fails, and a resolved path that does not exist. The probe shells
    out, so failures of any kind are swallowed: this is diagnosis, and it must
    never break the command it decorates.
    """
    if not hasattr(os, "getuid"):
        return None
    try:
        path = manager.install_root
    except Exception:  # noqa: BLE001
        # The probe runs the manager's own CLI: any failure means "unknown".
        return None
    if path is None:
        return None
    try:
        uid = path.stat().st_uid
    except OSError:
        return None
    # Deferred on purpose: `pwd` does not exist on Windows, returned above.
    import pwd

    try:
        owner_name = pwd.getpwuid(uid).pw_name
    except KeyError:
        owner_name = str(uid)
    return InstallRoot(path=path, owner_uid=uid, owner_name=owner_name)


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
                escalator.resolved_probe_args(),
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


def _escalation_is_passwordless(
    escalator: Escalator,
    managers: Iterable[PackageManager],
) -> bool:
    """Whether every command mpm escalates already runs without a password.

    Asked only after {attr}`~Escalator.probe_args` reported a cold cache, and
    answering the question that probe cannot: `sudo --validate` refuses while any
    matching `sudoers` entry wants a password, where
    {attr}`~Escalator.passwordless_probe_args` names one command and reports the
    rule that would actually run it. A host whose policy grants every escalated
    command unauthenticated therefore needs no prompt, no warning and no
    keepalive, having no credential to keep.

    Conservative on every uncertainty: an escalator with no such query, a manager
    whose binary was not found, or a single command the policy does not clear
    unauthenticated all answer `False` and leave the cold-cache path to handle it.
    """
    if escalator.passwordless_probe_args is None:
        return False
    cli_paths: set[Path] = set()
    for manager in managers:
        if not _resolved_sudo(manager):
            continue
        if manager.cli_path is None:
            return False
        cli_paths.add(manager.cli_path)
    if not cli_paths:
        return False
    for cli_path in sorted(cli_paths):
        probe_cli = (*escalator.passwordless_probe_args, str(cli_path))
        logging.debug(f"Probe the {escalator.id} policy: {' '.join(probe_cli)}")
        try:
            probe = subprocess.run(probe_cli, capture_output=True, check=False)
        except OSError:
            return False
        if probe.returncode != 0:
            return False
    return True


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

    escalator = ESCALATION.resolve()
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

    probe_args = escalator.resolved_probe_args()
    try:
        logging.debug(
            f"Probe the {escalator.id} credential cache: {' '.join(probe_args)}",
        )
        probe = subprocess.run(
            probe_args,
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

    if _escalation_is_passwordless(escalator, managers):
        # No credential is involved, so there is none to prompt for, refresh or
        # lose mid-run. The flag still goes up: it gates the stall watchdog, and
        # nothing can stall on a password the policy never asks for.
        logging.info(
            f"The {escalator.id} policy runs every escalated command without a "
            "password: no prompt needed.",
        )
        _SUDO_CACHE_WARM.set()
        ctx.call_on_close(_SUDO_CACHE_WARM.clear)
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
        f"{ctx.command.name}.",
        err=True,
    )
    prompt_cli = escalator.prompt_args
    if escalator.brands_prompt:
        # `sudo --prompt` expands %-escapes, and `%p` is the account whose password
        # is wanted. That is not always the invoking user: a `targetpw`, `rootpw` or
        # `runaspw` policy asks for another one, and openSUSE ships `targetpw` by
        # default, so a prompt naming the caller would send its users to type the
        # wrong password. Manager IDs are plain slugs, but are escaped anyway so one
        # carrying a `%` cannot smuggle in an escape of its own. An escalator that
        # cannot be told what to print falls back to its own prompt, under the
        # notice echoed above.
        escaped_ids = ids.replace("%", "%%")
        prompt = f"[mpm] password for %p (running {escaped_ids}): "
        prompt_cli = (*prompt_cli, "--prompt", prompt)
    if subprocess.run(prompt_cli, check=False).returncode != 0:
        logging.warning(
            f"Could not acquire {escalator.id} credentials: managers needing root "
            "may fail.",
        )
        return
    _start_sudo_keepalive(ctx, escalator)


def _hidden_prompt_risk(internal_sudo: bool, operation: str | None) -> bool:
    """Whether a call may block on a `sudo` password prompt the user cannot see.

    True for a mutating call of a manager that escalates internally
    ({attr}`CLIExecutor.internal_sudo
    <meta_package_manager.execution.CLIExecutor.internal_sudo>`), made on a
    terminal while the credential cache is cold. Those are the conditions under
    which the tool's own `sudo` prompts for a password nothing has primed.

    {meth}`CLIExecutor.run <meta_package_manager.execution.CLIExecutor.run>`
    reads it once per call and spends it twice, so the two responses cannot drift
    apart: it arms {class}`_StallWatchdog`, and it holds the call's spinner still.

    The still spinner is what makes the prompt answerable. `sudo` writes its
    prompt to `/dev/tty` with no trailing newline, so the prompt sits on the live
    terminal line. An animated call repaints that line every
    {data}`~meta_package_manager.execution.SPINNER_DELAY` seconds, which erases
    the prompt within one frame. Nothing repaints it, so the user reads a notice
    about a prompt they cannot see, and the run dies at
    {data}`~meta_package_manager.execution.MUTATING_TIMEOUT`.

    A concurrent batch draws one aggregate indicator instead of these per-call
    spinners, and that one is never in the way: the predicate also holds such a
    manager back to the sequential tail of
    {func}`~meta_package_manager.dispatch.dispatch`, which runs once the batch,
    and its indicator, are done.
    """
    return (
        internal_sudo
        and operation in _STALL_NOTICE_OPERATIONS
        and sys.stderr.isatty()
        and not _SUDO_CACHE_WARM.is_set()
    )


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
    download. Each silence episode warns at most once; a fresh line starts a new
    episode.

    The notice only pays off because of the still spinner:
    {func}`_hidden_prompt_risk` arms both for the same call, so a prompt the tool
    prints stays on screen to be answered. A notice raised while an animation
    erases that prompt names the stall but cannot end it.

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
    surface this notice avoids entirely), and it only covers tools honoring
    the variable (`brew` does, `fink`'s plain `sudo` re-exec does not). The
    scoped `sudo = true` opt-in documented in `docs/sudo.md` already covers
    users wanting a guaranteed up-front prompt. Its third original reason, a
    side channel to pause the spinner that would smear its prompt, is spent:
    {func}`_hidden_prompt_risk` already leaves such a call a still terminal,
    holding its spinner and scheduling it clear of the batch indicator.
    ```

    ```{note}

    One terminal state defeats the notice, and it is not a defect this class
    can repair. Keeping the child in mpm's process group is what lets its
    `sudo` reach the terminal at all, so when that group is *not* the
    terminal's foreground group, the read earns `SIGTTIN` and the kernel stops
    the whole group, mpm included: the notice thread is stopped along with the
    process it would warn about. Measured on a shell without job control
    (`ssh -tt host 'mpm …'`), where `ps` reports `mpm`, the helper and `sudo`
    all in state `T` at `do_signal_stop`. An interactive run puts mpm in the
    foreground group and the notice fires normally, so this reaches the
    frontends that spawn mpm from a pty without making it the foreground job.
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
