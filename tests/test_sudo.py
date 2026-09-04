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

These exercise {func}`meta_package_manager.sudo.prime_sudo` and its keepalive with
a mocked `subprocess.run` (no test ever launches a real `sudo`), the escalation
policy inventories across the manager pool, and the
{class}`meta_package_manager.sudo._StallWatchdog` end to end through
{class}`tests.fake_manager.FakeManager` (whose CLI is the Python interpreter, so
its subprocesses are real but harmless). The `sudo --non-interactive` command
wrapping of
`build_cli()`, the authentication-failure hint of `run()` and the CLI wiring
of `prime_sudo` stay in {mod}`tests.test_execution`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click_extra.spinner import Spinner
from extra_platforms import UNIX, is_any_windows

from meta_package_manager.pool import pool
from meta_package_manager.sudo import (
    _SUDO_CACHE_WARM,
    ESCALATION,
    ESCALATORS,
    Escalator,
    _is_permission_failure,
    _is_sudo_auth_failure,
    _is_sudo_denied,
    inspect_install_root,
    prime_sudo,
    resolve_escalator,
)

from .fake_manager import FakeManager

# Platform-dependent import: `pwd` does not exist on Windows, where the tests
# consuming it are skipped.
if not is_any_windows():
    import pwd

# A UNIX platform to force build_cli's platform gate deterministically,
# independent of the host the tests run on. Not imported from
# tests.test_execution, which already imports from this module.
_UNIX_PLATFORM = next(iter(UNIX))

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
        "aptitude",
        "cave",
        "dkp-pacman",
        "deb-get",
        "dnf",
        "dnf5",
        "emerge",
        "eopkg",
        "ips",
        "macports",
        "nala",
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
    """Exactly the managers whose CLI runs `sudo` itself mid-run are marked, and
    none of them escalates through mpm (an internal escalator is never wrapped)."""
    internal = {mid for mid, manager in pool.items() if type(manager).internal_sudo}
    assert internal == {
        "am",
        "aura",
        "cask",
        "fink",
        "pacaur",
        "pacstall",
        "paru",
        "pikaur",
        "topgrade",
        "trizen",
        "yay",
    }
    for mid in sorted(internal):
        assert pool[mid].default_sudo is False


# Sudo priming: probe the credential cache non-interactively first, prompt once up
# front only for the managers mpm itself escalates, then keep the cache warm so a
# password prompt never stalls the concurrent fan-out.


@pytest.fixture(autouse=True)
def _clear_escalator_cache():
    """Keep the `PATH`-derived escalator choice from leaking between tests.

    `resolve_escalator` caches on the assumption that `PATH` does not move
    mid-run, which a test patching `shutil.which` breaks in both directions.
    """
    resolve_escalator.cache_clear()
    yield
    resolve_escalator.cache_clear()


@contextmanager
def only_escalator(escalator_id: str | None, *, selected: str | None = None):
    """Pretend the host carries exactly `escalator_id`, or none at all.

    `selected` drives the process-wide choice the CLI would have recorded, so a
    test can force an escalator the way `--sudo-command` does.

    The binary is also pinned as genuine, so `resolve_escalator` never spends a
    `subprocess.run` on {meth}`~meta_package_manager.sudo.Escalator.is_genuine`.
    That keeps the call counts these tests assert on measuring credential
    probes alone, and keeps a pretended host from probing the real one. A test
    about an impostor patches `is_genuine` itself instead.
    """
    with (
        patch(
            "meta_package_manager.sudo.shutil.which",
            side_effect=lambda name: (
                f"/usr/bin/{name}" if name == escalator_id else None
            ),
        ),
        patch.object(Escalator, "is_genuine", return_value=True),
    ):
        resolve_escalator.cache_clear()
        ESCALATION.select(selected)
        try:
            yield
        finally:
            ESCALATION.select(None)
            # Entries computed under the patched `shutil.which` must not
            # outlive it: the helper is imported by other test modules that
            # carry no cache-clearing fixture of their own.
            resolve_escalator.cache_clear()


def _prompt_argv(run):
    """The argv of the interactive prompt, found by shape rather than by index.

    `prime_sudo` spawns a variable number of non-interactive probes before it
    prompts, so a positional lookup breaks whenever one is added. The prompt is
    the only call carrying `--prompt` (or, for `doas`, the only one without a
    non-interactive flag).
    """
    for call in run.call_args_list:
        argv = call.args[0]
        if "--prompt" in argv:
            return argv
    raise AssertionError(f"no branded prompt among {run.call_args_list}")


def _escalating_manager() -> FakeManager:
    """A fake manager whose policy escalates, to trip prime_sudo."""
    manager = FakeManager()
    manager.sudo = True
    return manager


def _internal_manager() -> FakeManager:
    """A fake manager that escalates internally (like cask and fink): mpm never
    wraps it in `sudo`, so prime_sudo only probes on its behalf."""
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
    """Patch the whole environment `prime_sudo` probes, yielding the `run` mock.

    Pins the platform (`windows`), the effective user (`root`) and the terminal
    state (`None` leaves the real descriptor unpatched, for tests that never reach
    the TTY check), and replaces `subprocess.run` so no test ever launches a real
    `sudo`. Callers set the mock's `return_value`/`side_effect` to shape the
    probe and prompt outcomes.

    The escalator is pinned to `sudo` rather than detected, since a Windows
    runner carries none on `PATH` and detection finding nothing would return
    from `prime_sudo` before the paths these tests exercise. A test wanting a
    different host nests its own {func}`only_escalator`, whose patch then wins.
    """
    with ExitStack() as stack:
        stack.enter_context(only_escalator("sudo"))
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
    # Two non-interactive probes and no prompt: the cache is cold, the policy
    # grants nothing unauthenticated, and nothing could be answered off-terminal.
    assert [call.args[0][:3] for call in run.call_args_list] == [
        ("sudo", "--non-interactive", "--validate"),
        ("sudo", "--non-interactive", "--list"),
    ]
    assert any(
        "fakemanager needs administrator rights" in record.getMessage()
        and "no terminal" in record.getMessage()
        for record in caplog.records
    )


def test_prime_sudo_skips_the_prompt_under_a_passwordless_policy(caplog):
    """A cold cache whose policy still runs every escalated command unauthenticated.

    `sudo --validate` refuses whenever *any* matching `sudoers` entry wants a
    password, so the `NOPASSWD` rule `docs/sudo.md` recommends reads as a cold
    cache once a distribution's stock `ALL ALL=(ALL) ALL` sits beside it.
    openSUSE ships exactly that pair, where mpm used to warn that managers "may
    fail" and then watch them succeed. Off-terminal on purpose: that is the path
    the spurious warning came from, and a policy needing no password needs no
    terminal either.
    """
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=False) as run, caplog.at_level(logging.WARNING):

        def answer(argv, **kwargs):
            """A cold credential cache over a policy that clears the command."""
            return subprocess.CompletedProcess((), 0 if "--list" in argv else 1)

        run.side_effect = answer
        try:
            prime_sudo(ctx, [_escalating_manager()])
            assert _SUDO_CACHE_WARM.is_set()
        finally:
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()
    assert not caplog.records
    assert not any("--prompt" in call.args[0] for call in run.call_args_list)


def test_prime_sudo_authenticates_and_keeps_alive_on_tty():
    """A cold cache on a terminal: probe first, then one branded password prompt,
    then the keepalive until the context closes."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:

        def answer(argv, **kwargs):
            """Cold cache, and a policy granting nothing unauthenticated, so the
            interactive prompt is the only call that succeeds. Keyed on argv
            rather than on call order, which the probes ahead of it may shift."""
            code = 0 if "--prompt" in argv else 1
            return subprocess.CompletedProcess((), code)

        run.side_effect = answer
        try:
            prime_sudo(ctx, [_escalating_manager()])
            # The non-interactive probe runs first, then authenticates once, up
            # front, before the fan-out, with the branded prompt.
            assert run.call_args_list[0].args[0] == (
                "sudo",
                "--non-interactive",
                "--validate",
            )
            prompt_argv = _prompt_argv(run)
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


def _wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Poll `predicate` until it holds or `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_keepalive_drop_warns_once_and_rearms(monkeypatch, caplog):
    """A refresh finding the credentials gone (Homebrew resets them on every
    command) clears the warm flag, with one warning per drop, and a later
    successful refresh sets the flag back, saying so at INFO."""
    monkeypatch.setattr("meta_package_manager.sudo._SUDO_KEEPALIVE_INTERVAL", 0.01)
    ctx = click.Context(click.Command("mpm"))
    refresh_rc = [0]

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, refresh_rc[0])

    def drop_warnings():
        return [
            record
            for record in caplog.records
            if "primed for this run are gone" in record.getMessage()
        ]

    with prime_sudo_env() as run, caplog.at_level(logging.INFO):
        run.side_effect = fake_run
        try:
            prime_sudo(ctx, [_escalating_manager()])
            assert _SUDO_CACHE_WARM.is_set()
            # Drop the credentials: the next refresh finds them gone.
            refresh_rc[0] = 1
            assert _wait_for(lambda: not _SUDO_CACHE_WARM.is_set())
            # Let several more failing refreshes pass: the drop warns only once.
            time.sleep(0.1)
            assert len(drop_warnings()) == 1
            # A re-authentication in this terminal re-warms the cache.
            refresh_rc[0] = 0
            assert _wait_for(_SUDO_CACHE_WARM.is_set)
        finally:
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()
    assert len(drop_warnings()) == 1
    assert all(record.levelno == logging.WARNING for record in drop_warnings())
    assert any(
        "warm again" in record.getMessage() and record.levelno == logging.INFO
        for record in caplog.records
    )


def test_prime_sudo_narrates_warm_probe_at_info(caplog):
    """A warm probe and the keepalive arming both tell their story at INFO, so
    a `--verbosity INFO` run shows why no password prompt appeared."""
    ctx = click.Context(click.Command("mpm"))
    with prime_sudo_env() as run, caplog.at_level(logging.INFO):
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [_escalating_manager()])
        finally:
            ctx.close()
    messages = [record.getMessage() for record in caplog.records]
    assert any("credential cache warm" in message for message in messages)
    assert any("Keeping the sudo credentials fresh" in message for message in messages)


def test_prime_sudo_narrates_internal_only_skip_at_info(caplog):
    """The decision to not prompt for an internal-only selection surfaces at
    INFO, never as a warning."""
    ctx = click.Context(click.Command("mpm"))
    with (
        prime_sudo_env(stdin_tty=True, stderr_tty=True) as run,
        caplog.at_level(logging.INFO),
    ):
        run.return_value = subprocess.CompletedProcess((), 1)
        prime_sudo(ctx, [_internal_manager()])
    skips = [
        record
        for record in caplog.records
        if "no up-front prompt" in record.getMessage()
    ]
    assert len(skips) == 1
    assert skips[0].levelno == logging.INFO


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


def test_prime_sudo_denied_user_skips_prompt(caplog):
    """A probe reporting a sudoers denial skips the password prompt even on a
    terminal: a password could only be collected then rejected. One warning
    names the managers and the remedy."""
    ctx = click.Context(click.Command("mpm"))
    with (
        prime_sudo_env(stdin_tty=True, stderr_tty=True) as run,
        caplog.at_level(logging.WARNING),
    ):
        run.return_value = subprocess.CompletedProcess(
            (),
            1,
            stderr=b"Sorry, user kevin may not run sudo on host.\n",
        )
        prime_sudo(ctx, [_escalating_manager()])
    # The non-interactive probe is the only subprocess: no prompt is raised.
    assert run.call_count == 1
    assert not _SUDO_CACHE_WARM.is_set()
    assert any(
        "not authorized to run sudo" in record.getMessage()
        and "fakemanager" in record.getMessage()
        and "--no-sudo" in record.getMessage()
        for record in caplog.records
    )


def test_prime_sudo_denied_internal_only_stays_silent(caplog):
    """A sudoers denial with only internal escalators selected stays silent:
    each manager's own sudo surfaces the denial through its error path."""
    ctx = click.Context(click.Command("mpm"))
    with (
        prime_sudo_env(stdin_tty=True, stderr_tty=True) as run,
        caplog.at_level(logging.WARNING),
    ):
        run.return_value = subprocess.CompletedProcess(
            (),
            1,
            stderr=b"Sorry, user kevin may not run sudo on host.\n",
        )
        prime_sudo(ctx, [_internal_manager()])
    assert run.call_count == 1
    assert not caplog.records


@pytest.mark.skipif(
    is_any_windows(),
    reason="The POSIX ownership check is skipped on Windows.",
)
@pytest.mark.parametrize(
    ("mode", "expect_warning"),
    (
        pytest.param(0o755, False, id="trusted"),
        pytest.param(0o777, True, id="world-writable"),
    ),
)
def test_prime_sudo_audits_escalated_binaries(tmp_path, caplog, mode, expect_warning):
    """The binary of a manager mpm escalates gets the config-file tamper test:
    one warning per manager when others can modify it, and the escalation still
    proceeds (the probe still runs)."""
    ctx = click.Context(click.Command("mpm"))
    binary = tmp_path / "fake-mpm"
    binary.write_text("#!/bin/sh\n", encoding="UTF-8")
    binary.chmod(mode)
    manager = _escalating_manager()
    manager.cli_path = binary
    with prime_sudo_env(stdin_tty=False) as run, caplog.at_level(logging.WARNING):
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [manager])
        finally:
            ctx.close()
    assert run.call_count == 1
    tamper_warnings = [
        record
        for record in caplog.records
        if "others can write to it" in record.getMessage()
    ]
    if expect_warning:
        assert len(tamper_warnings) == 1
        assert str(binary) in tamper_warnings[0].getMessage()
        assert tamper_warnings[0].label == manager.id
    else:
        assert not tamper_warnings


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
            "alpha needs administrator rights to upgrade.",
            "[mpm] password for %p (running alpha): ",
            id="singular",
        ),
        pytest.param(
            ("beta", "alpha"),
            "alpha, beta need administrator rights to upgrade.",
            "[mpm] password for %p (running alpha, beta): ",
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
    assert _prompt_argv(run) == (
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
    """Whatever the prompt copy becomes, the `--prompt` argument handed to `sudo`
    must stay within sudo's constraints.

    Locks the properties rather than the wording, so a future rewording trips here
    only if it breaks sudo: the only expandable escapes left are the ones the
    prompt hands to sudo on purpose, every other `%` being doubled (`sudo
    --prompt` expands `%h`/`%H`/`%p`/`%u`/`%U`, and a lone `%` is undefined), the
    prompt must be a single line (a newline would detach the ask from the input
    cursor), and it must end with a space so the typed password is not glued to
    the text.

    A manager id is the untrusted half here: whatever it contains, it may never
    reach sudo as an escape.
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
    prompt_argv = _prompt_argv(run)
    assert prompt_argv[:3] == ("sudo", "--validate", "--prompt")
    prompt = prompt_argv[3]
    assert prompt
    # Doubling check: with every %% pair collapsed away, the only escapes left may
    # be the ones the prompt spells itself. Anything else came from a manager id.
    residual = prompt.replace("%%", "")
    for deliberate in ("%p",):
        residual = residual.replace(deliberate, "")
    assert "%" not in residual
    assert "\n" not in prompt
    assert "\r" not in prompt
    assert prompt.endswith(" ")


def test_sudo_prompt_names_the_account_that_owns_the_password():
    """The prompt defers to sudo's `%p` for whose password is wanted.

    Not the caller: a `targetpw`, `rootpw` or `runaspw` policy asks for another
    account, and openSUSE ships `Defaults targetpw`, so a prompt naming the
    invoking user sends every one of its users to type the wrong password.
    """
    ctx = click.Context(click.Command("upgrade"))
    manager = _escalating_manager()
    manager.id = "zypper"
    with prime_sudo_env(stdin_tty=True, stderr_tty=True) as run:
        run.return_value = subprocess.CompletedProcess((), 1)
        try:
            prime_sudo(ctx, [manager])
        finally:
            ctx.close()
    prompt = _prompt_argv(run)[3]
    assert prompt.startswith("[mpm] password for %p ")
    assert "zypper" in prompt


RUN0_REFUSAL = (
    "Failed to start transient service unit: Access denied as the requested "
    "operation requires interactive authentication. However, interactive "
    "authentication has not been enabled by the calling program."
)
"""What `run0` writes to `<stderr>` when polkit refuses a `--no-ask-password`
call, measured on Arch Linux running systemd 261.

Signed by neither `run0` nor any `sudo` wording, because systemd's bus layer
words it: the matchers need a branch of their own to see it at all.
"""


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        ("sudo: a password is required", True),
        ("sudo: a terminal is required to read the password", True),
        ("sudo: no tty present and no askpass program specified", True),
        ("SUDO: A PASSWORD IS REQUIRED", True),
        # sudo-rs, the default sudo of Ubuntu 25.10 and newer.
        ("sudo: interactive authentication is required", True),
        # The three doas wordings, shared by OpenBSD's doas and opendoas. The
        # first is what Alpine's doas 6.8.2 answers under `-n` for both a bare
        # `permit` rule and a cold `permit persist` one.
        ("doas: Authentication required", True),
        ("doas: a tty is required", True),
        ("doas: Authentication failed", True),
        # Both of run0's refusal paths share a prefix: the non-interactive one
        # measured above, and the bare `Access denied` an agent reports when it
        # asked and was refused.
        (RUN0_REFUSAL, True),
        ("Failed to start transient service unit: Access denied", True),
        # Unsigned by any escalator: a command of its own saying the same thing.
        ("build.sh: authentication required", False),
        ("", False),
        ("error: package not found", False),
        ("sudo: command not found", False),
    ),
)
def test_is_sudo_auth_failure(error, expected):
    assert _is_sudo_auth_failure(error) is expected


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        # sudo 1.9 and newer, per its message catalog.
        ("User kevin is not allowed to run sudo on host.", True),
        # sudo before 1.9, and sudo-rs's validate denial.
        ("Sorry, user kevin may not run sudo on host.", True),
        ("kevin is not in the sudoers file.", True),
        # The per-command denial, sudo and sudo-rs alike.
        (
            "Sorry, user kevin is not allowed to execute '/bin/sh' as root on host.",
            True,
        ),
        ("SORRY, USER KEVIN MAY NOT RUN SUDO ON HOST.", True),
        # sudo-rs denies a `--validate` by quoting HAL 9000 rather than naming
        # sudo, and `--validate` is the probe mpm runs first. Matching only the
        # `--list` wording above left a non-sudoer on Ubuntu 25.10 and later
        # being prompted for a password that could never authorize them.
        ("sudo: I'm sorry kevin. I'm afraid I can't do that", True),
        # The same quote from a command rather than an escalator stays inert.
        ("hal: I'm afraid I can't do that", False),
        # opendoas prints the bare errno string of EPERM for an unmatched rule.
        # Confirmed on Alpine's doas 6.8.2 against a config permitting another
        # user only.
        ("doas: Operation not permitted", True),
        # An installed but unconfigured doas, measured on a runner carrying no
        # `/etc/doas.conf`, and confirmed verbatim on Alpine's doas 6.8.2. No
        # password can fix it either.
        (
            "doas: doas is not enabled, /etc/doas.conf: No such file or directory",
            True,
        ),
        # run0 defers to polkit, whose refusal is an authentication failure
        # rather than a denial: a prompt may still authorize it.
        (RUN0_REFUSAL, False),
        # A cold cache is an authentication failure, never a denial.
        ("sudo: a password is required", False),
        ("sudo: interactive authentication is required", False),
        ("doas: Authentication required", False),
        # The same errno string, from a command rather than from an escalator,
        # must not read as a refusal: only a line the escalator signed counts.
        ("rm: cannot remove '/etc/hosts': Operation not permitted", False),
        ("", False),
        ("error: package not found", False),
    ),
)
def test_is_sudo_denied(error, expected):
    assert _is_sudo_denied(error) is expected


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        # npm, on a root-owned global prefix.
        (
            (
                "npm error Error: EACCES: permission denied, "
                "access '/usr/local/lib/node_modules'"
            ),
            True,
        ),
        # gem, on a system Ruby.
        (
            (
                "You don't have write permissions for the "
                "/Library/Ruby/Gems/3.4.0 directory."
            ),
            True,
        ),
        # pip and cpan, from the interpreter and the shell.
        ("[Errno 13] Permission denied: '/usr/lib/python3.12'", True),
        ("PERMISSION DENIED", True),
        ("error: package not found", False),
        ("sudo: a password is required", False),
        ("", False),
    ),
)
def test_is_permission_failure(error, expected):
    assert _is_permission_failure(error) is expected


@pytest.mark.skipif(
    is_any_windows(),
    reason="The POSIX ownership model does not apply on Windows.",
)
def test_inspect_install_root(tmp_path):
    """The snapshot carries the root's owner; every dead end answers `None`."""
    manager = FakeManager()

    manager.install_root = tmp_path
    root = inspect_install_root(manager)
    assert root is not None
    assert root.path == tmp_path
    assert root.owner_uid == os.getuid()
    assert root.owner_name == pwd.getpwuid(os.getuid()).pw_name

    manager.install_root = tmp_path / "not-there"
    assert inspect_install_root(manager) is None

    manager.install_root = None
    assert inspect_install_root(manager) is None


@pytest.mark.skipif(
    is_any_windows(),
    reason="The POSIX ownership model does not apply on Windows.",
)
def test_inspect_install_root_swallows_probe_failures():
    """A probe that dies means "unknown", never a crash of the command it
    decorates."""

    class _BrokenProbe(FakeManager):
        @property
        def install_root(self):
            raise RuntimeError("probe exploded")

    assert inspect_install_root(_BrokenProbe()) is None


@pytest.mark.parametrize(
    ("manager_id", "expected_argv"),
    (
        pytest.param("npm", ("prefix",), id="npm"),
        pytest.param("gem", ("environment", "gemdir"), id="gem"),
        pytest.param(
            "pip",
            ("-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"),
            id="pip",
        ),
    ),
)
def test_install_root_probes_run_the_documented_verb(manager_id, expected_argv):
    """Each override resolves its root through its own discovery verb, forced
    to run for real (`force_exec`) like the version probe."""
    manager = type(pool[manager_id])()
    calls = []

    def fake_run_cli(*args, **kwargs):
        calls.append((args, kwargs))
        return "/fake/root\n"

    manager.run_cli = fake_run_cli
    assert manager.install_root == Path("/fake/root")
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == expected_argv
    assert kwargs.get("force_exec") is True


# Escalator selection: which binary drives the escalation, and how each dialect
# reaches the argv, the probe and the prompt.


def test_escalator_registry_prefers_sudo():
    """`sudo` stays the first choice, so a host carrying several keeps the
    behavior it has today and only an explicit override moves it.

    `run0` is last on purpose: it authorizes through polkit and needs one
    running, so it answers for the systemd hosts shipping neither of the
    others rather than displacing a working escalator.
    """
    assert [e.id for e in ESCALATORS] == ["sudo", "doas", "run0"]


@pytest.mark.parametrize(
    ("installed", "expected"),
    (
        pytest.param("sudo", "sudo", id="sudo-only"),
        pytest.param("doas", "doas", id="doas-only"),
        pytest.param(None, None, id="neither"),
    ),
)
def test_resolve_escalator_detects_what_the_host_carries(installed, expected):
    with only_escalator(installed):
        escalator = resolve_escalator()
    assert (escalator.id if escalator else None) == expected


def _both_escalators_installed():
    """Pretend the host carries `sudo` and `doas` both, without pinning either
    as genuine, so the identity probe is what decides between them."""
    return patch(
        "meta_package_manager.sudo.shutil.which",
        side_effect=lambda name: f"/usr/bin/{name}",
    )


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    (
        # Real sudo, measured on Alpine 3.24.1 running sudo 1.9.17_p2.
        pytest.param(0, "Sudo version 1.9.17p2\n", True, id="real-sudo"),
        # sudo-rs brands its own banner, measured on Ubuntu 26.04, where it is
        # the default `sudo`. Matching `Sudo version` alone rejected it as a
        # stand-in and handed a host carrying doas too the wrong escalator.
        pytest.param(0, "sudo-rs 0.2.13-0ubuntu1\n", True, id="sudo-rs"),
        # Alpine's doas-sudo-shim 0.2.0-r0 rejects the option outright, its
        # parser sending every unknown long option to `die`.
        pytest.param(1, "", False, id="doas-sudo-shim"),
        # A stand-in free to accept the option is still not sudo, so the
        # marker is checked and not just the exit status.
        pytest.param(0, "some other tool 1.0\n", False, id="silent-impostor"),
        # Nothing captured at all.
        pytest.param(0, None, False, id="no-output"),
    ),
)
def test_escalator_identity_probe_reads_the_binary(returncode, stdout, expected):
    sudo = ESCALATORS[0]
    assert sudo.id == "sudo"
    with patch("meta_package_manager.sudo.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess((), returncode, stdout=stdout)
        assert sudo.is_genuine() is expected
    run.assert_called_once()
    assert run.call_args.args[0] == ("sudo", "--version")


def test_escalator_without_identity_args_is_genuine():
    """An escalator opts into the identity check by declaring the argv for it,
    so the ones with no known stand-in spend no subprocess."""
    doas = ESCALATORS[1]
    assert doas.id == "doas"
    assert doas.identity_args is None
    with patch("meta_package_manager.sudo.subprocess.run") as run:
        assert doas.is_genuine() is True
    run.assert_not_called()


def test_escalator_identity_probe_survives_a_missing_binary():
    """A binary that vanished between `which()` and the probe cannot be driven,
    rather than crashing the run."""
    with patch("meta_package_manager.sudo.subprocess.run", side_effect=OSError):
        assert ESCALATORS[0].is_genuine() is False


def test_resolve_escalator_skips_an_impostor_for_the_real_thing():
    """Alpine's `doas-sudo-shim` puts a `sudo` on `PATH` that forwards to
    `doas`, accepting `--non-interactive` and no other option mpm sends. Driving
    `doas` directly is what keeps the probes answering."""
    with (
        _both_escalators_installed(),
        patch.object(
            Escalator,
            "is_genuine",
            autospec=True,
            side_effect=lambda self: self.id != "sudo",
        ),
    ):
        resolve_escalator.cache_clear()
        escalator = resolve_escalator()
        resolve_escalator.cache_clear()
    assert escalator is not None
    assert escalator.id == "doas"


def test_resolve_escalator_keeps_sudo_on_a_sudo_rs_host():
    """A host whose `sudo` is sudo-rs keeps escalating through it, even carrying
    `doas` too.

    The identity probe reads the binary's own banner, and sudo-rs prints
    `sudo-rs <version>` where the original prints `Sudo version <version>`.
    Matching only the latter made `is_genuine` reject Ubuntu's default `sudo`,
    and the search then settled on `doas`, inverting the preference
    {data}`~meta_package_manager.sudo.ESCALATORS` documents.
    """
    with (
        _both_escalators_installed(),
        patch("meta_package_manager.sudo.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(
            (), 0, stdout="sudo-rs 0.2.13-0ubuntu1\n"
        )
        resolve_escalator.cache_clear()
        escalator = resolve_escalator()
        resolve_escalator.cache_clear()
    assert escalator is not None
    assert escalator.id == "sudo"


def test_resolve_escalator_falls_back_to_a_lone_impostor():
    """An impostor still escalates, so it beats reporting no escalator at all."""
    with (
        only_escalator("sudo"),
        patch.object(Escalator, "is_genuine", return_value=False),
    ):
        resolve_escalator.cache_clear()
        escalator = resolve_escalator()
        resolve_escalator.cache_clear()
    assert escalator is not None
    assert escalator.id == "sudo"


def test_resolve_escalator_override_wins_over_detection():
    """An override is honored even when its binary is missing, so the failure
    names the escalator the user asked for."""
    with only_escalator("sudo"):
        escalator = resolve_escalator("doas")
    assert escalator is not None
    assert escalator.id == "doas"


def test_resolve_escalator_rejects_an_unknown_name(caplog):
    with only_escalator("sudo"), caplog.at_level(logging.WARNING):
        assert resolve_escalator("please") is None
    assert any("Unknown sudo_command" in r.getMessage() for r in caplog.records)


def test_escalator_choice_is_machine_level():
    """The escalator is process-wide, never a manager attribute: a machine runs
    one of them, and every manager escalating on it uses that one.

    Guards both halves. No manager may carry the choice as an attribute, and the
    per-manager config section must refuse it, so `[mpm.managers.<id>]` can never
    make one manager escalate differently from its peers.
    """
    from meta_package_manager.definitions import OVERRIDABLE_FIELDS

    assert not hasattr(FakeManager(), "sudo_command")
    assert "sudo_command" not in OVERRIDABLE_FIELDS
    assert "sudo_command" not in pool.ALLOWED_EXTRA_OPTION


def test_per_manager_sudo_command_is_refused(invoke, tmp_path):
    """A `[mpm.managers.<id>] sudo_command` entry is rejected outright, naming
    the fields that are per-manager, rather than silently escalating one manager
    through another binary."""
    config = tmp_path / "config.toml"
    config.write_text(
        '[mpm.managers.apt]\nsudo_command = "doas"\n',
        encoding="UTF-8",
    )
    result = invoke("--config", str(config), "managers")
    assert result.exit_code != 0
    assert "mpm.managers.apt.sudo_command: unknown field" in result.stderr


def test_sudo_command_reaches_the_config_file(invoke, tmp_path):
    """`[mpm] sudo_command` is honored, and validated against the same choices
    as the flag: an unknown escalator is a usage error, not a silent fallback."""
    config = tmp_path / "config.toml"
    config.write_text('[mpm]\nsudo_command = "bogus"\n', encoding="UTF-8")
    result = invoke("--config", str(config), "managers")
    assert result.exit_code == 2
    assert "'bogus' is not one of 'sudo', 'doas'" in result.stderr


@pytest.mark.parametrize(
    ("escalator_id", "expected_prefix"),
    (
        pytest.param("sudo", ("sudo", "--non-interactive"), id="sudo"),
        # `doas` parses short options only: `-n` is its whole "do not prompt"
        # vocabulary, so the long-form convention cannot reach it.
        pytest.param("doas", ("doas", "-n"), id="doas"),
    ),
)
def test_build_cli_escalates_with_the_selected_binary(escalator_id, expected_prefix):
    manager = _escalating_manager()
    with (
        # Pin the platform gate too: a Windows host never escalates, whatever
        # the escalator, and this test's subject is the argv dialect.
        patch(
            "meta_package_manager.execution.current_platform",
            return_value=_UNIX_PLATFORM,
        ),
        only_escalator(escalator_id, selected=escalator_id),
    ):
        args = manager.build_cli("install", "pkg", sudo=True)
    assert tuple(str(a) for a in args[: len(expected_prefix)]) == expected_prefix


def test_build_cli_skips_escalation_without_an_escalator():
    """A host carrying neither binary runs the command unprivileged rather than
    prefixing a `sudo` that is not there."""
    manager = _escalating_manager()
    with only_escalator(None):
        args = manager.build_cli("install", "pkg", sudo=True)
    assert "sudo" not in [str(a) for a in args]
    assert "doas" not in [str(a) for a in args]


def test_prime_sudo_warns_without_any_escalator(caplog):
    ctx = click.Context(click.Command("mpm"))
    with (
        prime_sudo_env() as run,
        only_escalator(None),
        caplog.at_level(logging.WARNING),
    ):
        prime_sudo(ctx, [_escalating_manager()])
    run.assert_not_called()
    assert any("Found none of sudo, doas" in r.getMessage() for r in caplog.records)


def test_prime_sudo_probes_and_prompts_through_doas(capsys):
    """A doas host is probed with `doas -n true` and, on a cold cache, prompted
    with a bare `doas true`: it cannot be told what prompt to print, so the
    echoed notice carries the explanation instead."""
    ctx = click.Context(click.Command("upgrade"))
    manager = _escalating_manager()
    with (
        prime_sudo_env(stdin_tty=True, stderr_tty=True) as run,
        only_escalator("doas", selected="doas"),
    ):
        run.side_effect = (
            subprocess.CompletedProcess((), 1),  # Cold-cache probe.
            subprocess.CompletedProcess((), 0),  # Successful password prompt.
        )
        try:
            prime_sudo(ctx, [manager])
            assert run.call_args_list[0].args[0] == ("doas", "-n", "true")
            assert run.call_args_list[1].args[0] == ("doas", "true")
        finally:
            ctx.close()
    assert "needs administrator rights to upgrade" in capsys.readouterr().err


def test_doas_gets_no_keepalive_thread(caplog):
    """doas persistence is opt-in per rule, so a recurring probe would report a
    drop on every tick of a host that never asked for it. The cache is marked
    warm, without a thread refreshing it."""
    ctx = click.Context(click.Command("mpm"))
    manager = _escalating_manager()
    with (
        prime_sudo_env() as run,
        only_escalator("doas", selected="doas"),
        caplog.at_level(logging.INFO),
    ):
        run.return_value = subprocess.CompletedProcess((), 0)
        try:
            prime_sudo(ctx, [manager])
            assert _SUDO_CACHE_WARM.is_set()
            # The probe is the only subprocess: no refresh tick follows it.
            assert run.call_count == 1
        finally:
            ctx.close()
    assert not _SUDO_CACHE_WARM.is_set()
    assert any(
        "cannot be refreshed on a schedule" in r.getMessage() for r in caplog.records
    )


# Stall watchdog: a mutating call of an internal escalator (cask, fink) that goes
# silent on a cold credential cache may be blocked on a hidden sudo password
# prompt. run() arms _StallWatchdog around the spawn to flag the silence.


def _stalling_script(line: str, sleep: float) -> str:
    """A one-liner that prints `line`, flushes, then stays silent for `sleep`
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


@pytest.mark.parametrize(
    ("internal_sudo", "expected_enabled"),
    (
        pytest.param(True, False, id="armed-call-stays-still"),
        pytest.param(False, None, id="ordinary-call-animates"),
    ),
)
def test_hidden_prompt_risk_holds_the_spinner_still(internal_sudo, expected_enabled):
    """A call that may hide a `sudo` prompt builds its spinner disabled, leaving
    the terminal line the tool writes that prompt on: an animation repainting it
    erases the prompt and leaves the run to die at the mutating timeout. The
    control differs by the `internal_sudo` gate alone, and keeps `enabled=None`,
    the auto-detected animation of an ordinary call.
    """
    manager = FakeManager()
    manager.internal_sudo = internal_sudo
    manager._active_operation = "install"
    manager.progress = True
    built: list[bool | None] = []

    class RecordingSpinner(Spinner):
        def __init__(self, *args, **kwargs):
            built.append(kwargs["enabled"])
            super().__init__(*args, **kwargs)

    with (
        patch("sys.stderr.isatty", return_value=True),
        patch("meta_package_manager.execution.Spinner", RecordingSpinner),
    ):
        manager.run_cli("-c", "print('quick call')")
    assert built == [expected_enabled]


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
