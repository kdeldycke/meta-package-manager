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

import re

import pytest

from meta_package_manager.capabilities import Operations

from .conftest import default_manager_ids
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "upgrade", "--all"


class TestUpgrade(CLISubCommandTests):
    """Test the system-wide upgrade sub-command.

    .. danger::
        All tests here should me marked as destructive unless --dry-run parameter is
        passed.
    """

    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # Log-level prefix is omitted because Skip/does-not-implement are
            # demoted to DEBUG for implicit selection and stay at WARNING/INFO
            # for explicit ones (``mpm --<mid> upgrade``).
            f"{mid} does not implement upgrade_all_cli." in stderr,
            f"{mid} does not implement {Operations.upgrade_all}." in stderr,
            f"Upgrade all outdated packages from {mid}..." in stderr,
            bool(re.search(rf"Upgrade \S+ with {mid}\.\.\.", stderr)),
            f"Skip {mid} manager:" in stderr,
        )

    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_all_managers_dry_run_upgrade_all(self, invoke, all_option):
        # ``--verbosity DEBUG`` makes the per-manager skip/does-not-implement
        # messages reach stderr: at default verbosity they stay quiet because
        # this invocation makes no explicit ``--<id>`` selection.
        result = invoke("--verbosity", "DEBUG", "--dry-run", "upgrade", all_option)
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result)

    @pytest.mark.destructive()
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_all_managers_upgrade_all(self, invoke, all_option):
        result = invoke("--verbosity", "DEBUG", "upgrade", all_option)
        # Accept exit code 1: end-to-end destructive upgrades depend on the
        # health of every installed third-party manager, and CI runners
        # regularly surface transient backend failures (missing project files,
        # toolchain gaps, network blips). The contract we test here is that
        # mpm dispatched to every selected manager and surfaced their output.
        assert result.exit_code in (0, 1)
        if not all_option:
            assert "assume -A/--all option" in result.stderr
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
            assert not result.stdout
            assert (
                "\x1b[31m\x1b[1mcritical\x1b[0m: No manager selected.\n"
                in result.stderr
            )
        else:
            assert result.exit_code == 0
            self.check_manager_selection(result, {manager_id})

    @pytest.mark.destructive()
    @default_manager_ids
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_single_manager_upgrade_all(self, invoke, manager_id, all_option):
        result = invoke(f"--{manager_id}", "upgrade", all_option)
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        if result.exit_code == 2:
            assert not result.stdout
            assert (
                "\x1b[31m\x1b[1mcritical\x1b[0m: No manager selected.\n"
                in result.stderr
            )
        else:
            # Accept exit code 1: see test_all_managers_upgrade_all.
            assert result.exit_code in (0, 1)
            self.check_manager_selection(result, {manager_id})
