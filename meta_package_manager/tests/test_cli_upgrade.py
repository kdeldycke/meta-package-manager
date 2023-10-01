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

from meta_package_manager.base import Operations

from .conftest import default_manager_ids
from .test_cli import CLISubCommandTests


@pytest.fixture()
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
            f"warning: {mid} does not implement upgrade_all_cli." in stderr,
            f"warning: {mid} does not implement {Operations.upgrade_all}." in stderr,
            f"Upgrade all outdated packages from {mid}..." in stderr,
            bool(re.search(rf"Upgrade \S+ with {mid}\.\.\.", stderr)),
            # Common "not found" warning message.
            f"warning: Skip unavailable {mid} manager." in stderr,
        )

    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_all_managers_dry_run_upgrade_all(self, invoke, all_option):
        result = invoke("--dry-run", "upgrade", all_option)
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result)

    @pytest.mark.destructive()
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_all_managers_upgrade_all(self, invoke, all_option):
        result = invoke("upgrade", all_option)
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result)

    @default_manager_ids
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_single_manager_dry_run_upgrade_all(self, invoke, manager_id, all_option):
        result = invoke(
            f"--{manager_id}", "--dry-run", "--verbosity", "INFO", "upgrade", all_option
        )
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result, {manager_id})

    @pytest.mark.destructive()
    @default_manager_ids
    @pytest.mark.parametrize("all_option", ("--all", None))
    def test_single_manager_upgrade_all(self, invoke, manager_id, all_option):
        result = invoke(f"--{manager_id}", "upgrade", all_option)
        assert result.exit_code == 0
        if not all_option:
            assert "assume -A/--all option" in result.stderr
        self.check_manager_selection(result, {manager_id})
