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
"""Unit tests for the privilege-escalation machinery.

These exercise :func:`meta_package_manager.sudo.prime_sudo` and its keepalive with
a mocked ``subprocess.run`` (no test ever launches a real ``sudo``), the escalation
policy inventories across the manager pool, and the
:class:`meta_package_manager.sudo._StallWatchdog` end to end through
:class:`tests.fake_manager.FakeManager` (whose CLI is the Python interpreter, so
its subprocesses are real but harmless). The ``sudo --non-interactive`` command
wrapping of
``build_cli()``, the authentication-failure hint of ``run()`` and the CLI wiring
of ``prime_sudo`` stay in :mod:`tests.test_execution`.
"""

from __future__ import annotations

import logging
import subprocess
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import click
import pytest

from meta_package_manager.pool import pool
from meta_package_manager.sudo import (
    _SUDO_CACHE_WARM,
    _is_sudo_auth_failure,
    prime_sudo,
)

from .fake_manager import FakeManager

# Escalation policy inventories: which managers escalate through mpm and which run
# sudo themselves, pinned across the whole pool so a new manager cannot silently
# change the escalation story.


def test_default_sudo_matches_system_managers():
    """Exactly the system package managers (classes, their subclasses and bundled
    definitions alike) escalate by default; user-level managers do not, the
    dual-scope language managers (npm, pip, gem, cpan) keep their privileged
    markers dormant, and the polkit-native daemon clients (flatpak, fwupd, pkcon)
    never mark an operation at all."""
    escalating = {mid for mid, manager in pool.items() if type(manager).default_sudo}
    assert escalating == {
        "apk",
        "apt",
        "apt-mint",
        "cave",
        "deb-get",
        "dnf",
        "dnf5",
        "emerge",
        "eopkg",
        "macports",
        "pacman",
        "pkg",
        "pkg-tools",
        "pkgin",
        "ports",
        "slapt-get",
        "snap",
        "sorcery",
        "sun-tools",
        "swupd",
        "tazpkg",
        "urpmi",
        "xbps",
        "yum",
        "zypper",
    }
    for mid in (
        "brew",
        "cask",
        "npm",
        "pip",
        "gem",
        "cpan",
        "cargo",
        "flatpak",
        "fwupd",
        "pkcon",
    ):
        assert pool[mid].default_sudo is False


def test_internal_sudo_matches_internal_escalators():
    """Exactly the managers whose CLI runs ``sudo`` itself mid-run are marked, and
    none of them escalates through mpm (an internal escalator is never wrapped)."""
    internal = {mid for mid, manager in pool.items() if type(manager).internal_sudo}
    assert internal == {"cask", "fink", "pacaur", "pacstall", "paru", "topgrade", "yay"}
    for mid in sorted(internal):
        assert pool[mid].default_sudo is False


# Sudo priming: probe the credential cache non-interactively first, prompt once up
# front only for the managers mpm itself escalates, then keep the cache warm so a
# password prompt never stalls the concurrent fan-out.


def _escalating_manager() -> FakeManager:
    """A fake manager whose policy escalates, to trip prime_sudo."""
    manager = FakeManager()
    manager.sudo = True
    return manager


def _internal_manager() -> FakeManager:
    """A fake manager that escalates internally (like cask and fink): mpm never
    wraps it in ``sudo``, so prime_sudo only probes on its behalf."""
    manager = FakeManager()
    manager.internal_sudo = True
    return manager


@contextmanager
def prime_sudo_env(
    *,
    windows: bool = False,
    root: bool = False,
    stdin_tty: bool | None = None,
    stderr_tty: bool | None = None,
):
    """Patch the whole environment ``prime_sudo`` probes, yielding the ``run`` mock.

    Pins the platform (``windows``), the effective user (``root``) and the terminal
    state (``None`` leaves the real descriptor unpatched, for tests that never reach
    the TTY check), and replaces ``subprocess.run`` so no test ever launches a real
    ``sudo``. Callers set the mock's ``return_value``/``side_effect`` to shape the
    probe and prompt outcomes.
    """
    with ExitStack() as stack:
        stack.enter_context(
            patch("meta_package_manager.sudo.is_any_windows", return_value=windows),
        )
        stack.enter_context(
            patch(
                "meta_package_manager.sudo.os.geteuid",
                return_value=0 if root else 1000,
                create=True,
            ),
        )
        if stdin_tty is not None:
            stack.enter_context(patch("sys.stdin.isatty", return_value=stdin_tty))
        if stderr_tty is not None:
            stack.enter_context(patch("sys.stderr.isatty", return_value=stderr_tty))
        yield stack.enter_context(
            patch("meta_package_manager.sudo.subprocess.run"),
        )


def test_prime_sudo_skips_when_no_manager_escalates():
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env() as run:
        prime_sudo(ctx, [FakeManager()])
    run.assert_not_called()


def test_prime_sudo_skips_on_windows():
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(windows=True) as run:
        prime_sudo(ctx, [_escalating_manager()])
    run.assert_not_called()


def test_prime_sudo_skips_when_root():
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(root=True) as run:
        prime_sudo(ctx, [_escalating_manager()])
    run.assert_not_called()


@pytest.mark.parametrize("simulation_flag", ("dry_run", "plan"))
def test_prime_sudo_skips_on_simulation(simulation_flag):
    """Neither a dry run nor a plan run executes a state-changing CLI, so both skip
    the sudo prompt."""
    ctx = click.Context(click.Command("mpm"))
    manager = _escalating_manager()
    setattr(manager, simulation_flag, True)
    with prime_sudo_env() as run:
        prime_sudo(ctx, [manager])
    run.assert_not_called()


def test_prime_sudo_warns_without_tty(caplog):
    """A cold cache off-terminal: the probe still runs first, then one warning
    names the managers left to fail fast instead of blocking on a prompt."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=False) as run, caplog.at_level(logging.WARNING):
        run.return_value = subprocess.CompletedProcess((), 1)
        prime_sudo(ctx, [_escalating_manager()])
    # The non-interactive probe is the only subprocess: no prompt can be answered.
    assert run.call_count == 1
    assert run.call_args.args[0] == ("sudo", "--non-interactive", "--validate")
    assert any(
        "fakemanager needs administrator rights" in record.getMessage()
        and "no terminal" in record.getMessage()
        for record in caplog.records
    )


def test_prime_sudo_authenticates_and_keeps_alive_on_tty():
    """A cold cache on a terminal: probe first, then one branded password prompt,
    then the keepalive until the context closes."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        run.side_effect = (
            subprocess.CompletedProcess((), 1),  # Cold-cache probe.
            subprocess.CompletedProcess((), 0),  # Successful password prompt.
        )
        try:
            prime_sudo(ctx, [_escalating_manager()])
            # The non-interactive probe runs first, then authenticates once, up
            # front, before the fan-out, with the branded prompt.
            assert run.call_count == 2
            assert run.call_args_list[0].args[0] == (
                "sudo",
                "--non-interactive",
                "--validate",
            )
            prompt_argv = run.call_args_list[1].args[0]
            assert prompt_argv[:3] == ("sudo", "--validate", "--prompt")
            assert prompt_argv[3].startswith("[mpm] password for ")
            assert "fakemanager" in prompt_argv[3]
            assert _SUDO_CACHE_WARM.is_set()
        finally:
            # Stop the keep-alive (a stop callback was registered on the context)
            # while subprocess.run is still patched, so no real sudo escapes the
            # test.
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()


def test_prime_sudo_is_idempotent():
    """A second call on the same context is a no-op: one probe, ever."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [_escalating_manager()])
            prime_sudo(ctx, [_escalating_manager()])
        finally:
            ctx.close()
    assert run.call_count == 1
    assert run.call_args.args[0] == ("sudo", "--non-interactive", "--validate")


def test_prime_sudo_warm_probe_stays_silent_on_tty(capsys):
    """A warm credential cache (pre-authenticated, NOPASSWD): no notice, no
    prompt, just the keepalive until the context closes."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [_escalating_manager()])
            assert run.call_count == 1
            assert run.call_args.args[0] == ("sudo", "--non-interactive", "--validate")
            assert _SUDO_CACHE_WARM.is_set()
        finally:
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()
    assert capsys.readouterr().err == ""


def test_prime_sudo_warm_probe_keeps_alive_off_tty(caplog):
    """The probe short-circuits before the terminal check: a CI job with
    pre-cached credentials gets the keepalive instead of the no-terminal
    warning."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=False) as run, caplog.at_level(logging.WARNING):
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [_escalating_manager()])
            assert run.call_count == 1
            assert _SUDO_CACHE_WARM.is_set()
        finally:
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()
    assert not caplog.records


def test_prime_sudo_cold_internal_only_never_prompts_on_tty(capsys, caplog):
    """A cold cache with only internal escalators (a stock cask/fink selection)
    probes, then returns without prompting: most such runs never escalate, and
    the stall notice covers the rare mid-run prompt instead."""
    ctx = click.Context(click.Command("mpm"))
    with (
        prime_sudo_env(stdin_tty=True, stderr_tty=True) as run,
        caplog.at_level(logging.WARNING),
    ):
        run.return_value = subprocess.CompletedProcess((), 1)
        try:
            prime_sudo(ctx, [_internal_manager()])
        finally:
            ctx.close()
    assert run.call_count == 1
    assert run.call_args.args[0] == ("sudo", "--non-interactive", "--validate")
    assert not _SUDO_CACHE_WARM.is_set()
    assert not caplog.records
    assert capsys.readouterr().err == ""


def test_prime_sudo_cold_internal_only_stays_silent_off_tty(caplog):
    """Off-terminal, an internal-only selection gets no warning: each manager's
    own sudo fails fast and surfaces through its error path."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=False) as run, caplog.at_level(logging.WARNING):
        run.return_value = subprocess.CompletedProcess((), 1)
        try:
            prime_sudo(ctx, [_internal_manager()])
        finally:
            ctx.close()
    assert run.call_count == 1
    assert not _SUDO_CACHE_WARM.is_set()
    assert not caplog.records


@pytest.mark.parametrize(
    "probe_error",
    (
        pytest.param(FileNotFoundError, id="not-found"),
        pytest.param(PermissionError, id="not-executable"),
    ),
)
def test_prime_sudo_warns_when_sudo_cannot_run(caplog, probe_error):
    """A UNIX host whose sudo is missing or not executable gets one warning instead
    of the probe crashing prime_sudo. Both raise an OSError subclass from the probe."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env() as run, caplog.at_level(logging.WARNING):
        run.side_effect = probe_error
        prime_sudo(ctx, [_escalating_manager()])
    assert not _SUDO_CACHE_WARM.is_set()
    assert any(
        "sudo could not be run" in record.getMessage() for record in caplog.records
    )


@pytest.mark.parametrize(
    ("manager_ids", "expected_notice", "expected_prompt"),
    (
        pytest.param(
            ("alpha",),
            "alpha needs administrator rights to upgrade: enter your password.",
            "[mpm] password for alpha: ",
            id="singular",
        ),
        pytest.param(
            ("beta", "alpha"),
            "alpha, beta need administrator rights to upgrade: enter your password.",
            "[mpm] password for alpha, beta: ",
            id="plural-sorted",
        ),
    ),
)
def test_prime_sudo_notice_names_managers_and_subcommand(
    capsys, manager_ids, expected_notice, expected_prompt
):
    """The password notice names the sorted escalating managers (with a verb
    agreeing in number) and the subcommand; the sudo prompt is branded alike."""
    ctx = click.Context(click.Command("upgrade"))
    managers = []
    for manager_id in manager_ids:
        manager = _escalating_manager()
        manager.id = manager_id
        managers.append(manager)
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        # Cold probe, then a failed password prompt: no keepalive to tear down.
        run.return_value = subprocess.CompletedProcess((), 1)
        try:
            prime_sudo(ctx, managers)
        finally:
            ctx.close()
    assert expected_notice in capsys.readouterr().err
    assert run.call_args_list[1].args[0] == (
        "sudo",
        "--validate",
        "--prompt",
        expected_prompt,
    )


@pytest.mark.parametrize(
    "manager_ids",
    (
        pytest.param(("alpha", "beta"), id="plain-slugs"),
        # Adversarial ids a creative future prompt must still neutralize: sudo expands
        # %h/%H/%p/%u/%U in --prompt, and %% collapses to a literal %.
        pytest.param(("we%ird", "100%"), id="percent"),
        pytest.param(("%p", "%u%H"), id="sudo-escapes"),
        pytest.param(("a%%b",), id="pre-doubled"),
    ),
)
def test_sudo_prompt_respects_sudo_constraints(manager_ids):
    """Whatever the prompt copy becomes, the ``--prompt`` argument handed to ``sudo``
    must stay within sudo's constraints.

    Locks the properties rather than the wording, so a future rewording trips here
    only if it breaks sudo: every ``%`` must be doubled (``sudo --prompt`` expands
    ``%h``/``%H``/``%p``/``%u``/``%U``, and a lone ``%`` is undefined), the prompt
    must be a single line (a newline would detach the ask from the input cursor),
    and it must end with a space so the typed password is not glued to the text.
    """
    ctx = click.Context(click.Command("upgrade"))
    managers = []
    for manager_id in manager_ids:
        manager = _escalating_manager()
        manager.id = manager_id
        managers.append(manager)
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        # Cold probe, then a failed password prompt: no keepalive to tear down.
        run.return_value = subprocess.CompletedProcess((), 1)
        try:
            prime_sudo(ctx, managers)
        finally:
            ctx.close()
    prompt_argv = run.call_args_list[1].args[0]
    assert prompt_argv[:3] == ("sudo", "--validate", "--prompt")
    prompt = prompt_argv[3]
    assert prompt
    # Doubling check: with every %% pair removed, no expandable % may remain.
    assert "%" not in prompt.replace("%%", "")
    assert "\n" not in prompt
    assert "\r" not in prompt
    assert prompt.endswith(" ")


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        ("sudo: a password is required", True),
        ("sudo: a terminal is required to read the password", True),
        ("sudo: no tty present and no askpass program specified", True),
        ("SUDO: A PASSWORD IS REQUIRED", True),
        ("", False),
        ("error: package not found", False),
        ("sudo: command not found", False),
    ),
)
def test_is_sudo_auth_failure(error, expected):
    assert _is_sudo_auth_failure(error) is expected


# Stall watchdog: a mutating call of an internal escalator (cask, fink) that goes
# silent on a cold credential cache may be blocked on a hidden sudo password
# prompt. run() arms _StallWatchdog around the spawn to flag the silence.


def _stalling_script(line: str, sleep: float) -> str:
    """A one-liner that prints ``line``, flushes, then stays silent for ``sleep``
    seconds, mimicking an installer blocked on a hidden prompt."""
    return f"import sys, time; print({line!r}); sys.stdout.flush(); time.sleep({sleep})"


def test_stall_watchdog_notices_silent_internal_escalator(monkeypatch, caplog):
    """A mutating call of an internal escalator, on a terminal with a cold cache,
    warns once per silence episode, naming the manager and quoting its last
    output line."""
    assert not _SUDO_CACHE_WARM.is_set()
    manager = FakeManager()
    manager.internal_sudo = True
    manager._active_operation = "install"
    monkeypatch.setattr("meta_package_manager.sudo._STALL_NOTICE_DELAY", 0.2)
    with (
        patch("sys.stderr.isatty", return_value=True),
        caplog.at_level(logging.WARNING),
    ):
        manager.run_cli("-c", _stalling_script("installer may ask", 2))
    notices = [
        record
        for record in caplog.records
        if "hidden password prompt" in record.getMessage()
    ]
    assert notices
    assert all(record.label == manager.id for record in notices)
    assert all(record.getMessage().startswith("No output for ") for record in notices)
    # A slow interpreter startup may trip an extra no-output-yet notice before the
    # line arrives; the episode quoting the line warns exactly once.
    quoting = [
        record
        for record in notices
        if 'Last output: "installer may ask"' in record.getMessage()
    ]
    assert len(quoting) == 1


@pytest.mark.parametrize(
    ("active_operation", "internal_sudo", "warm_cache", "tty"),
    (
        pytest.param("installed", True, False, True, id="read-only-operation"),
        pytest.param("install", False, False, True, id="no-internal-sudo"),
        pytest.param("install", True, True, True, id="warm-cache"),
        pytest.param("install", True, False, False, id="off-tty"),
    ),
)
def test_stall_watchdog_negative_gates(
    monkeypatch, caplog, active_operation, internal_sudo, warm_cache, tty
):
    """Each arming gate individually disarms the watchdog: no notice fires even
    when the call stays silent for far longer than the (shortened) delay."""
    manager = FakeManager()
    manager.internal_sudo = internal_sudo
    manager._active_operation = active_operation
    monkeypatch.setattr("meta_package_manager.sudo._STALL_NOTICE_DELAY", 0.2)
    if warm_cache:
        _SUDO_CACHE_WARM.set()
    try:
        with (
            patch("sys.stderr.isatty", return_value=tty),
            caplog.at_level(logging.WARNING),
        ):
            manager.run_cli("-c", _stalling_script("quiet stretch", 1))
    finally:
        _SUDO_CACHE_WARM.clear()
    assert not any(
        "hidden password prompt" in record.getMessage() for record in caplog.records
    )


def test_stall_watchdog_tee_gates_debug_lines_at_default_verbosity(caplog):
    """An armed call still hides child output lines at the default WARNING level:
    the tee forwards them through the root logger's level gate instead of
    bypassing it."""
    manager = FakeManager()
    manager.internal_sudo = True
    manager._active_operation = "install"
    with (
        patch("sys.stderr.isatty", return_value=True),
        caplog.at_level(logging.WARNING),
    ):
        manager.run_cli("-c", "print('tee gated line')")
    assert not any("tee gated line" in record.getMessage() for record in caplog.records)


def test_stall_watchdog_tee_forwards_verbatim_at_debug(caplog):
    """At DEBUG verbosity an armed call streams child lines through the tee with
    the same message, level and manager label as an un-teed run."""
    manager = FakeManager()
    manager.internal_sudo = True
    manager._active_operation = "install"
    with (
        patch("sys.stderr.isatty", return_value=True),
        caplog.at_level(logging.DEBUG),
    ):
        manager.run_cli("-c", "print('tee forwarded line')")
    records = [
        record
        for record in caplog.records
        if record.getMessage() == "tee forwarded line"
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].label == manager.id
