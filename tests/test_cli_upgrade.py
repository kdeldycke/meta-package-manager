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
import re

import pytest

from meta_package_manager.capabilities import Operations
from meta_package_manager.execution import CLIError

from .conftest import default_manager_ids
from .fake_manager import FakeManager
from .test_cli import CLISubCommandTests


@pytest.fixture
def failing_installed_query(monkeypatch):
    """Break `FakeManager.installed`, like a misconfigured `pnpm` breaks its own."""

    def raise_cli_error(manager):
        raise CLIError(1, "", "Global bin directory is not in PATH.")

    monkeypatch.setattr(FakeManager, "installed", property(raise_cli_error))


@pytest.fixture
def subcmd():
    return "upgrade", "--all"


class TestUpgrade(CLISubCommandTests):
    """Test the system-wide upgrade sub-command.

    ```{danger}
    All tests here should me marked as destructive unless --dry-run parameter is
    passed.
    ```
    """

    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # The glued `:<mid>:` label form matches whatever level the
            # message lands at: demoted to DEBUG for implicit selection,
            # WARNING/INFO for explicit ones (`mpm --<mid> upgrade`).
            f":{mid}: Does not implement upgrade_all_cli." in stderr,
            f":{mid}: Does not implement {Operations.upgrade_all}." in stderr,
            f":{mid}: Upgrade all outdated packages..." in stderr,
            bool(re.search(rf"Upgrade \S+ with {mid}\.\.\.", stderr)),
            f":{mid}: Skipped:" in stderr,
        )

    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_all_managers_dry_run_upgrade_all(self, invoke, all_option):
        # `--verbosity DEBUG` makes the per-manager skip/does-not-implement
        # messages reach stderr: at default verbosity they stay quiet because
        # this invocation makes no explicit `--<id>` selection.
        result = invoke("--verbosity", "DEBUG", "--dry-run", "upgrade", all_option)
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result)

    @pytest.mark.destructive()
    def test_all_managers_upgrade_all(self, invoke):
        # Only the explicit `--all` spelling runs destructively: the bare
        # `upgrade` alias is already asserted by both dry-run variants above,
        # and the non-convergent managers (cpan rebuilds, gem re-walks every
        # installed gem even when current) repeat their full upgrade on a
        # second pass, doubling the destructive wall-clock for the sake of an
        # argument-parsing message.
        result = invoke("--verbosity", "DEBUG", "upgrade", "--all")
        # Accept exit code 1: end-to-end destructive upgrades depend on the
        # health of every installed third-party manager, and CI runners
        # regularly surface transient backend failures (missing project files,
        # toolchain gaps, network blips). The contract we test here is that
        # mpm dispatched to every selected manager and surfaced their output.
        assert result.exit_code in (0, 1)
        self.check_manager_selection(result)

    @default_manager_ids
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_single_manager_dry_run_upgrade_all(self, invoke, manager_id, all_option):
        result = invoke(
            f"--{manager_id}", "--dry-run", "--verbosity", "INFO", "upgrade", all_option
        )
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        if result.exit_code == 2:
            self.assert_no_manager_selected(result)
        else:
            # Accept exit code 1: some managers (like pip on Windows) may
            # report errors during the upgrade dry-run simulation, causing
            # exit code 1 rather than 0. This is an environmental issue and
            # not a test-logic failure.
            assert result.exit_code in (0, 1)
            self.check_manager_selection(result, {manager_id})

    @pytest.mark.destructive()
    @default_manager_ids
    def test_single_manager_upgrade_all(self, invoke, manager_id):
        # Only the explicit `--all` spelling runs destructively: see
        # test_all_managers_upgrade_all.
        result = invoke(f"--{manager_id}", "--verbosity", "INFO", "upgrade", "--all")
        if result.exit_code == 2:
            self.assert_no_manager_selected(result)
        else:
            # Accept exit code 1: see test_all_managers_upgrade_all.
            assert result.exit_code in (0, 1)
            self.check_manager_selection(result, {manager_id})


def test_installed_ids_tolerates_a_failing_cli(
    fake_pool, failing_installed_query, caplog
):
    """A manager whose `installed` CLI fails reports no IDs instead of raising."""
    with caplog.at_level(logging.WARNING):
        assert fake_pool.installed_ids == frozenset()
    assert "Could not list installed packages." in caplog.text


# `upgrade <packages>` and `remove` share the `_dispatch_sourced_operation` engine,
# which reads `installed_ids` on every selected manager to find which ones carry an
# untied package. A manager whose query CLI is broken used to abort the whole command
# with a traceback before the managers that do have the package were ever tried.
@pytest.mark.parametrize("subcommand", ("upgrade", "remove"))
def test_sourcing_survives_a_failing_manager(
    invoke, fake_pool, failing_installed_query, subcommand
):
    result = invoke("--dry-run", subcommand, "fake-pkg-alpha")
    assert result.exit_code == 0
    assert "Traceback" not in result.stderr
    assert f":{fake_pool.id}: Could not list installed packages." in result.stderr
    # No manager could source the package, so it is skipped rather than fatal.
    assert "fake-pkg-alpha is not recognized" in result.stderr
