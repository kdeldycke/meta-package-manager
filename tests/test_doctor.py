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
"""Checks for the ``doctor`` operation and its dedicated contract.

Health comes from the diagnostic command's exit code alone, the report merges
``<stdout>`` and ``<stderr>``, and the diagnosis never inflates the end-of-run
error tally. The argv assertions monkeypatch the binary-resolution seams on the
pooled manager singletons, so they run identically on any host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from meta_package_manager.capabilities import Operations, implements
from meta_package_manager.execution import CLIError
from meta_package_manager.pool import pool

from .conftest import _patch_pool_with
from .fake_manager import FakeManager


@pytest.mark.parametrize(
    ("manager_id", "token"),
    (
        ("apt", "check"),
        ("brew", "doctor"),
        ("cask", "doctor"),
        ("composer", "diagnose"),
        ("dnf", "check"),
        ("flatpak", "--dry-run"),
        ("gem", "check"),
        ("mise", "doctor"),
        ("npm", "doctor"),
        ("pacman", "--check"),
        ("pip", "check"),
        ("pkg", "--checksums"),
        ("scoop", "checkup"),
        ("xbps", "--all"),
    ),
)
def test_doctor_cli_argv(monkeypatch, manager_id, token):
    """Each manager's diagnostic invocation carries its native verb."""
    manager = pool[manager_id]
    monkeypatch.setattr(
        manager, "cli_path", Path("/fake/bin") / manager.cli_names[0], raising=False
    )
    monkeypatch.setattr(manager, "which", lambda name: Path("/fake/bin") / name)
    monkeypatch.setattr(
        manager, "sibling_cli", lambda name, **kwargs: Path("/fake/bin") / name
    )
    tokens = tuple(str(arg) for arg in manager.doctor_cli())
    assert token in tokens


@pytest.mark.parametrize(
    "manager_id",
    ("apt", "brew", "cask", "dnf", "macports", "pacman", "pip", "tlmgr", "xbps"),
)
def test_doctor_supported(manager_id):
    assert implements(pool[manager_id], Operations.doctor) is True


@pytest.mark.parametrize("manager_id", ("cargo", "cave", "mas", "snap", "uv"))
def test_doctor_unsupported(manager_id):
    assert implements(pool[manager_id], Operations.doctor) is False


# Base orchestrator contract, driven through a stubbed run().


def _doctor_with_stubbed_run(monkeypatch, *, code, stdout, stderr, completed=True):
    """Run ``doctor()`` on a manager whose ``run`` mimics one executor outcome.

    Reproduces ``run()``'s observable surface: sets ``_last_run`` on completion
    (or leaves it ``None`` for a spawn that never finished), applies the failure
    gate's default tolerance (a non-zero exit only accumulates a ``CLIError``
    when ``<stderr>`` is non-empty), and returns ``<stdout>``.
    """
    manager = pool["mise"]
    monkeypatch.setattr(manager, "doctor_cli", lambda: ("doctor",))
    monkeypatch.setattr(manager, "cli_errors", [])

    def fake_run(*args, **kwargs):
        manager._last_run = (code, stdout, stderr) if completed else None
        if completed and code and stderr:
            manager.cli_errors.append(CLIError(code, stdout, stderr))
        elif not completed:
            manager.cli_errors.append(CLIError(None, "", "Timed out."))
        return stdout

    monkeypatch.setattr(manager, "run", fake_run)
    return manager


def test_doctor_healthy_merges_streams(monkeypatch):
    manager = _doctor_with_stubbed_run(
        monkeypatch, code=0, stdout="All good.", stderr="Note: chatter."
    )
    assert manager.doctor() == (True, "All good.\nNote: chatter.")
    assert manager.cli_errors == []


def test_doctor_unhealthy_from_stdout_only_exit(monkeypatch):
    """A non-zero exit with silent ``<stderr>`` (the pip check shape) is tolerated
    by the failure gate but must still read as unhealthy: the exit code is the
    verdict."""
    manager = _doctor_with_stubbed_run(
        monkeypatch, code=1, stdout="conflicting dependencies found", stderr=""
    )
    assert manager.doctor() == (False, "conflicting dependencies found")
    assert manager.cli_errors == []


def test_doctor_reclaims_failure_gate_entry(monkeypatch):
    """The unhealthy exit is the diagnosis, not a plumbing error: the gate's
    ``CLIError`` is reclaimed so the end-of-run summary is not inflated."""
    manager = _doctor_with_stubbed_run(
        monkeypatch, code=1, stdout="", stderr="Warning: broken linkage."
    )
    assert manager.doctor() == (False, "Warning: broken linkage.")
    assert manager.cli_errors == []


def test_doctor_incomplete_run_stays_an_error(monkeypatch):
    """A spawn that never completed (timeout, interrupt) is a genuine plumbing
    error: unhealthy, and its ``CLIError`` stays in the tally."""
    manager = _doctor_with_stubbed_run(
        monkeypatch, code=0, stdout="", stderr="", completed=False
    )
    assert manager.doctor() == (False, "")
    assert len(manager.cli_errors) == 1


def test_base_doctor_not_implemented():
    """A manager without a diagnostic verb propagates ``NotImplementedError``."""
    with pytest.raises(NotImplementedError):
        pool["uv"].doctor()


# CLI plumbing, driven through deterministic fakes.


class HealthyDoctorFakeManager(FakeManager):
    """Fake manager whose diagnosis succeeds with a report."""

    def doctor_cli(self) -> tuple[str, ...]:
        return ("doctor",)

    def doctor(self) -> tuple[bool, str]:
        return True, "Your system is ready."


class SickDoctorFakeManager(HealthyDoctorFakeManager):
    """Fake manager whose diagnosis reports problems."""

    def doctor(self) -> tuple[bool, str]:
        return False, "Broken linkage found."


class SilentDoctorFakeManager(HealthyDoctorFakeManager):
    """Fake manager whose diagnosis succeeds silently (the apt-get check shape)."""

    def doctor(self) -> tuple[bool, str]:
        return True, ""


def test_doctor_healthy_relays_report(invoke, monkeypatch):
    fake = _patch_pool_with(monkeypatch, HealthyDoctorFakeManager())
    result = invoke("doctor")
    assert result.exit_code == 0
    assert f"{fake.id}:" in result.stdout
    assert "Your system is ready." in result.stdout


def test_doctor_unhealthy_exits_nonzero(invoke, monkeypatch):
    fake = _patch_pool_with(monkeypatch, SickDoctorFakeManager())
    result = invoke("doctor")
    assert result.exit_code == 1
    assert "Broken linkage found." in result.stdout
    assert f"1 managers reported problems ({fake.id})." in result.stderr


@pytest.mark.parametrize("flag", ("--zero-exit", "-0"))
def test_doctor_zero_exit_opt_out(invoke, monkeypatch, flag):
    """-0/--zero-exit keeps the exit code at 0; the critical summary stays as the
    durable record."""
    fake = _patch_pool_with(monkeypatch, SickDoctorFakeManager())
    result = invoke(flag, "doctor")
    assert result.exit_code == 0
    assert f"1 managers reported problems ({fake.id})." in result.stderr


def test_doctor_silent_healthy_prints_no_section(invoke, monkeypatch):
    """A healthy manager with an empty report gets no stdout section: the trail
    already says everything."""
    fake = _patch_pool_with(monkeypatch, SilentDoctorFakeManager())
    result = invoke("doctor")
    assert result.exit_code == 0
    assert f"{fake.id}:" not in result.stdout
