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
import threading
import time
from unittest.mock import patch

import pytest
from click_extra.execution import _LIVE_PROCESSES, terminate_live_processes
from extra_platforms import ALL_PLATFORMS, UNIX, is_any_windows

from meta_package_manager.capabilities import Operations
from meta_package_manager.execution import (
    DEFAULT_TIMEOUT,
    MUTATING_TIMEOUT,
    OPERATION_TIMEOUTS,
    READ_ONLY_TIMEOUT,
    SPINNER_DELAY,
    CLIError,
)
from meta_package_manager.pool import pool

from .fake_manager import FakeManager

# A UNIX and a non-UNIX platform to force build_cli's platform gate deterministically,
# independent of the host the tests run on.
_UNIX_PLATFORM = next(iter(UNIX))
_NON_UNIX_PLATFORM = next(p for p in ALL_PLATFORMS if p not in UNIX)


def test_operation_timeouts_cover_all_operations():
    """Every routable operation must have a per-operation timeout default, so the
    map and the ``Operations`` enum never drift apart."""
    for operation in Operations:
        assert operation.name in OPERATION_TIMEOUTS


def test_read_only_tier_is_shorter_than_mutating_tier():
    """Read-only probes fail faster than state-changing operations."""
    assert READ_ONLY_TIMEOUT < MUTATING_TIMEOUT
    # Unknown operations stay on the conservative (long) side.
    assert DEFAULT_TIMEOUT == MUTATING_TIMEOUT


@pytest.mark.parametrize("active_operation", (None, "version", "search", "install"))
def test_resolve_timeout_explicit_wins(active_operation):
    """An explicit timeout (``--timeout`` or per-manager override) wins for every
    operation, including unknown ones."""
    manager = FakeManager()
    manager.timeout = 42
    manager._active_operation = active_operation
    assert manager._resolve_timeout() == 42


@pytest.mark.parametrize(
    ("active_operation", "expected"),
    (
        ("version", READ_ONLY_TIMEOUT),
        ("installed", READ_ONLY_TIMEOUT),
        ("outdated", READ_ONLY_TIMEOUT),
        ("search", READ_ONLY_TIMEOUT),
        ("install", MUTATING_TIMEOUT),
        ("upgrade", MUTATING_TIMEOUT),
        ("upgrade_all", MUTATING_TIMEOUT),
        ("remove", MUTATING_TIMEOUT),
        ("sync", MUTATING_TIMEOUT),
        ("cleanup", MUTATING_TIMEOUT),
    ),
)
def test_resolve_timeout_per_operation(active_operation, expected):
    """With no explicit timeout, each operation resolves to its tier default."""
    manager = FakeManager()
    manager.timeout = None
    manager._active_operation = active_operation
    assert manager._resolve_timeout() == expected


def test_resolve_timeout_unknown_operation_falls_back_to_default():
    """A CLI call with no known operation gets the conservative default."""
    manager = FakeManager()
    manager.timeout = None
    manager._active_operation = None
    assert manager._resolve_timeout() == DEFAULT_TIMEOUT


def test_make_spinner_disabled_without_progress():
    """Without the progress opt-in, the spinner is forced off."""
    manager = FakeManager()
    manager.progress = False
    assert manager._make_spinner().enabled is False


def test_make_spinner_defers_to_tty_with_progress():
    """With progress on, the spinner is left to auto-detect a TTY at runtime."""
    manager = FakeManager()
    manager.progress = True
    assert manager._make_spinner().enabled is None


def test_make_spinner_label_includes_manager_and_operation():
    manager = FakeManager()
    manager._active_operation = "search"
    label = manager._make_spinner().label
    assert manager.id in label
    assert "search" in label


def test_make_spinner_label_without_operation():
    manager = FakeManager()
    manager._active_operation = None
    assert manager._make_spinner().label == str(manager.id)


def test_make_spinner_uses_configured_delay():
    assert FakeManager()._make_spinner().delay == SPINNER_DELAY


# Tiny cross-platform CLIs that exit non-zero, differing only in which stream
# carries the diagnostic. ``FakeManager`` runs the Python interpreter as its
# binary, so ``run_cli("-c", ...)`` executes these directly.
FAIL_ON_STDOUT = "import sys; sys.stdout.write('boom'); sys.exit(8)"
"""Fails the steamcmd way: a non-zero exit with its message on ``<stdout>`` and an
empty ``<stderr>``."""
FAIL_ON_STDERR = "import sys; sys.stderr.write('boom'); sys.exit(8)"
"""Fails the conventional way: a non-zero exit with its message on ``<stderr>``."""


@pytest.mark.parametrize(
    ("stop_on_error", "must_succeed", "script", "expectation"),
    (
        # The steamcmd-on-Windows regression: in the action context (a patched
        # stop_on_error, no must_succeed) a non-zero exit with an empty <stderr>
        # must now be a failure, not a silent success.
        pytest.param(True, False, FAIL_ON_STDOUT, "raise", id="action-empty-stderr"),
        # A parsed read (must_succeed) tolerates the same exit as a benign status
        # code, like npm and pnpm outdated exiting 1 when updates exist.
        pytest.param(False, True, FAIL_ON_STDOUT, "tolerate", id="read-empty-stderr"),
        # Neither opt-in: the lenient default tolerates it too.
        pytest.param(
            False, False, FAIL_ON_STDOUT, "tolerate", id="default-empty-stderr"
        ),
        # A conventional failure (<stderr> populated) still raises when the caller
        # demanded success, whether via the action context or must_succeed...
        pytest.param(True, False, FAIL_ON_STDERR, "raise", id="action-stderr"),
        pytest.param(False, True, FAIL_ON_STDERR, "raise", id="read-stderr"),
        # ...and is accumulated for the end-of-run summary otherwise.
        pytest.param(False, False, FAIL_ON_STDERR, "accumulate", id="default-stderr"),
    ),
)
def test_run_failure_gate(stop_on_error, must_succeed, script, expectation):
    """The failure gate decides raise / accumulate / tolerate from the exit code,
    the ``<stderr>`` content, and the ``stop_on_error``/``must_succeed`` context."""
    manager = FakeManager()
    manager.stop_on_error = stop_on_error

    if expectation == "raise":
        with pytest.raises(CLIError) as excinfo:
            manager.run_cli("-c", script, must_succeed=must_succeed)
        assert excinfo.value.code == 8
    elif expectation == "accumulate":
        manager.run_cli("-c", script, must_succeed=must_succeed)
        assert [error.code for error in manager.cli_errors] == [8]
    else:  # tolerate.
        output = manager.run_cli("-c", script, must_succeed=must_succeed)
        assert output == "boom"
        assert manager.cli_errors == []


# CLIExecutor.run_cache: lock-family peers replay a byte-identical command instead of
# re-running it. Each script appends a byte to a marker file, so its length counts how
# many subprocesses actually ran.


def _append_script(marker, payload="x", tail=""):
    """A one-liner that appends ``payload`` to ``marker``, then runs ``tail``."""
    return f"open({str(marker)!r}, 'a').write({payload!r}); {tail}"


def test_run_cache_replays_identical_command(tmp_path):
    """With a shared cache, a byte-identical command runs the subprocess once."""
    marker = tmp_path / "runs.log"
    script = _append_script(marker)
    cache: dict = {}
    first, second = FakeManager(), FakeManager()
    first.run_cache = second.run_cache = cache

    out_first = first.run_cli("-c", script)
    out_second = second.run_cli("-c", script)

    # The subprocess ran exactly once; the peer was served from the shared cache.
    assert marker.read_text() == "x"
    assert out_first == out_second == ""


def test_run_cache_disabled_by_default(tmp_path):
    """Without a cache, identical commands each spawn their own subprocess."""
    marker = tmp_path / "runs.log"
    script = _append_script(marker)
    manager = FakeManager()
    assert manager.run_cache is None

    manager.run_cli("-c", script)
    manager.run_cli("-c", script)

    assert marker.read_text() == "xx"


def test_run_cache_replays_failure_to_every_member(tmp_path):
    """A cached failure is re-attributed to each peer, though the command runs once."""
    marker = tmp_path / "runs.log"
    script = _append_script(
        marker, tail="import sys; sys.stderr.write('boom'); sys.exit(8)"
    )
    cache: dict = {}
    first, second = FakeManager(), FakeManager()
    first.stop_on_error = second.stop_on_error = False
    first.run_cache = second.run_cache = cache

    first.run_cli("-c", script)
    second.run_cli("-c", script)

    # One real execution, but both managers recorded the failure for the trail.
    assert marker.read_text() == "x"
    assert [error.code for error in first.cli_errors] == [8]
    assert [error.code for error in second.cli_errors] == [8]


def test_run_cache_keeps_distinct_commands_apart(tmp_path):
    """Only byte-identical invocations collapse; different args each run."""
    marker = tmp_path / "runs.log"
    manager = FakeManager()
    manager.run_cache = {}

    manager.run_cli("-c", _append_script(marker, "a"))
    manager.run_cli("-c", _append_script(marker, "b"))

    assert marker.read_text() == "ab"


def test_run_cache_collapses_dry_run(caplog):
    """Under --dry-run a family's identical command is announced once, not per member."""
    cache: dict = {}
    first, second = FakeManager(), FakeManager()
    first.dry_run = second.dry_run = True
    first.run_cache = second.run_cache = cache

    with caplog.at_level(logging.WARNING):
        first.run_cli("-c", "pass")
        second.run_cli("-c", "pass")

    # The command is announced once; the peer is a silent (INFO) cache hit.
    dry_run_lines = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Dry-run:")
    ]
    assert len(dry_run_lines) == 1
    # The first dry-run still seeded the cache, so the peer had something to reuse.
    assert len(cache) == 1


# Interrupt handling: the live-subprocess registry and the SIGINT handler live in
# click_extra.execution (and are tested there). This checks mpm's side of the
# contract: CLIExecutor.run() must route its subprocess through run_cli() so the
# child lands in that registry for the duration of the call.


def test_run_registers_live_process_then_discards_it():
    """run() tracks its subprocess while it runs, and drops it once done.

    A background call parks in a real subprocess. Once it is registered,
    terminate_live_processes() unblocks it, and run_cli()'s ``finally`` clears the
    registry: this is the exact path the SIGINT handler drives on Ctrl+C.
    """
    manager = FakeManager()

    def call():
        manager.run_cli("-c", "import time; time.sleep(30)")

    worker = threading.Thread(target=call)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not _LIVE_PROCESSES and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _LIVE_PROCESSES, "run() should register its live subprocess"
        # Terminating the child unblocks the parked run() call.
        terminate_live_processes()
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        terminate_live_processes()
        worker.join(timeout=5)
    # run_cli()'s finally discarded the child once it was reaped.
    assert not _LIVE_PROCESSES


# Privilege escalation: a per-op marker gated by a per-manager policy, escalated with
# `sudo --non-interactive`. The priming, keepalive, policy inventories and stall
# watchdog are covered
# in test_sudo.py; these exercise the wrapping and failure-hint paths of execution.py.


def test_build_cli_escalates_with_sudo_n_when_policy_on():
    """A privileged op escalates to `sudo --non-interactive` when the manager's
    policy opts in."""
    manager = FakeManager()
    manager.sudo = True
    with patch(
        "meta_package_manager.execution.current_platform", return_value=_UNIX_PLATFORM
    ):
        cli = manager.build_cli("install", "pkg", sudo=True)
    assert cli[:2] == ("sudo", "--non-interactive")


def test_build_cli_no_escalation_when_policy_off():
    """`--no-sudo` (policy False) drops escalation even on a privileged op."""
    manager = FakeManager()
    manager.sudo = False
    with patch(
        "meta_package_manager.execution.current_platform", return_value=_UNIX_PLATFORM
    ):
        cli = manager.build_cli("install", "pkg", sudo=True)
    assert "sudo" not in cli


def test_build_cli_no_escalation_off_unix():
    """A non-UNIX host never escalates (no crash), even with policy on."""
    manager = FakeManager()
    manager.sudo = True
    with patch(
        "meta_package_manager.execution.current_platform",
        return_value=_NON_UNIX_PLATFORM,
    ):
        cli = manager.build_cli("install", "pkg", sudo=True)
    assert "sudo" not in cli


def test_build_cli_marker_required_for_escalation():
    """Policy on but no per-op marker (sudo=False default) means no escalation."""
    manager = FakeManager()
    manager.sudo = True
    with patch(
        "meta_package_manager.execution.current_platform", return_value=_UNIX_PLATFORM
    ):
        cli = manager.build_cli("list")
    assert "sudo" not in cli


def test_npm_sudo_marker_dormant_until_opted_in():
    """npm marks its global installs privileged, but stays unescalated until the user
    opts in via --sudo / config (default_sudo is False)."""
    from meta_package_manager.managers.npm import NPM

    manager = NPM()
    assert manager.default_sudo is False
    with patch(
        "meta_package_manager.execution.current_platform", return_value=_UNIX_PLATFORM
    ):
        assert "sudo" not in manager.build_cli("update", sudo=True)
        manager.sudo = True
        assert manager.build_cli("update", sudo=True)[:2] == (
            "sudo",
            "--non-interactive",
        )


@pytest.mark.skipif(is_any_windows(), reason="escalation is UNIX-only")
def test_run_hints_when_sudo_cannot_authenticate(tmp_path, monkeypatch, caplog):
    """A real `sudo --non-interactive` that cannot authenticate triggers the actionable hint.

    A fake `sudo` on ``PATH`` mimics "no cached credentials", so the whole
    build_cli → subprocess → failure-gate → hint path runs for real, without root.
    """
    fake_sudo = tmp_path / "sudo"
    fake_sudo.write_text("#!/bin/sh\necho 'sudo: a password is required' >&2\nexit 1\n")
    fake_sudo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    manager = FakeManager()
    manager.sudo = True
    with patch(
        "meta_package_manager.execution.current_platform", return_value=_UNIX_PLATFORM
    ):
        cli = manager.build_cli("-c", "pass", sudo=True)
        assert cli[:2] == ("sudo", "--non-interactive")
        with caplog.at_level(logging.WARNING):
            manager.run(*cli)
    assert any("mpm --sudo" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "args",
    (
        pytest.param(("install", "fake-pkg"), id="install"),
        pytest.param(("upgrade", "--all"), id="upgrade-all"),
        pytest.param(("upgrade", "fake-pkg"), id="upgrade-packages"),
        pytest.param(("remove", "fake-pkg"), id="remove"),
        pytest.param(("sync",), id="sync"),
        pytest.param(("cleanup",), id="cleanup"),
    ),
)
def test_mutating_subcommands_prime_sudo(invoke, fake_pool, args):
    """Every mutating subcommand authenticates sudo up front, so a future command
    cannot silently skip the priming."""
    with patch("meta_package_manager.cli.prime_sudo") as prime:
        invoke("--dry-run", *args)
    assert prime.called, f"`mpm {args[0]}` did not call prime_sudo"


def test_restore_primes_sudo(invoke, fake_pool, tmp_path):
    """`restore` fans installs out too, so it also primes sudo up front."""
    toml_file = tmp_path / "backup.toml"
    toml_file.write_text("")
    with patch("meta_package_manager.cli.prime_sudo") as prime:
        invoke("--dry-run", "restore", str(toml_file))
    assert prime.called


def test_read_subcommand_does_not_prime_sudo(invoke, fake_pool):
    """A read-only command never escalates, so it must not prompt for sudo."""
    with patch("meta_package_manager.cli.prime_sudo") as prime:
        invoke("--dry-run", "installed")
    assert not prime.called


@pytest.mark.parametrize(
    ("args", "expected_operation"),
    (
        pytest.param(("remove", "fake-pkg-alpha"), "remove", id="remove"),
        pytest.param(("upgrade", "fake-pkg-alpha"), "upgrade", id="upgrade-packages"),
    ),
)
def test_sourced_operation_restamps_active_operation(
    invoke, fake_pool, monkeypatch, args, expected_operation
):
    """A sourced ``remove``/``upgrade <packages>`` restores the real operation stamp
    before its mutating fan-out.

    Source discovery re-selects the managers with ``installed``, which re-stamps
    ``_active_operation = "installed"`` on the shared singletons. Left uncorrected, the
    mutating commands would resolve the read-only timeout and skip the escalator stall
    watchdog (both keyed on ``_active_operation``). This drives the real selection flow,
    unlike the watchdog unit tests that stamp the attribute by hand: it fails if the
    dispatch stops restoring the stamp.
    """
    # The sourced dispatch fetches the acting manager through ``pool.get``; return the
    # fake so a real task is built. ``fake-pkg-alpha`` is in the fake's installed set,
    # so an untied spec resolves to it without touching a real binary.
    monkeypatch.setattr(pool, "get", lambda manager_id: fake_pool)
    # Cooldown gating is host-dependent; permit unconditionally so the task is built.
    monkeypatch.setattr(
        "meta_package_manager.cli.cooldown_permits", lambda manager: True
    )
    invoke("--dry-run", *args)
    assert fake_pool._active_operation == expected_operation


def test_untied_install_search_runs_under_read_only_stamp(
    invoke, fake_pool, monkeypatch
):
    """The untied-install priority search runs under the ``search`` stamp, not
    ``install``.

    The search is read-only and can never escalate, so it must not resolve the mutating
    timeout nor arm the internal-escalator stall watchdog (both keyed on
    ``_active_operation``). Without the stamp, a slow ``brew search`` of a cask would be
    misread as a hidden password prompt.
    """
    recorded = {}

    def fake_search(*, extended, exact, query):
        recorded["operation"] = fake_pool._active_operation
        return iter(())

    monkeypatch.setattr(fake_pool, "refiltered_search", fake_search)
    # An untied name the fake does not install is unmatched, so it drops onto the
    # sequential priority search that probes each manager with refiltered_search.
    invoke("--dry-run", "install", "unmatched-name")
    assert recorded["operation"] == Operations.search.name
