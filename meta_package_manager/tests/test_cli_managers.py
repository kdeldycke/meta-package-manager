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

import json

import pytest
from boltons.iterutils import same

from ..pool import pool
from .conftest import all_manager_ids, default_manager_ids, unsupported_manager_ids
from .test_cli import CLISubCommandTests, CLITableTests


@pytest.fixture
def subcmd():
    return "managers"


class TestManagers(CLISubCommandTests, CLITableTests):
    @default_manager_ids
    def test_default_managers(self, invoke, subcmd, manager_id):
        result = invoke(f"--{manager_id}", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {manager_id})

    @all_manager_ids
    def test_all_managers(self, invoke, subcmd, manager_id):
        result = invoke(f"--{manager_id}", "--all-managers", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(
            result, {manager_id}, reference_set=pool.all_manager_ids
        )

    @unsupported_manager_ids
    def test_unsupported_managers(self, invoke, subcmd, manager_id):
        result = invoke(f"--{manager_id}", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, set())

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd)
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert data
        assert isinstance(data, dict)
        assert set(data) == set(pool.default_manager_ids)

        for manager_id, info in data.items():
            assert isinstance(manager_id, str)
            assert isinstance(info, dict)

            assert set(info) == {
                "available",
                "cli_path",
                "errors",
                "executable",
                "fresh",
                "id",
                "name",
                "supported",
                "version",
            }

            assert isinstance(info["available"], bool)
            if info["cli_path"] is not None:
                assert isinstance(info["cli_path"], str)

            assert isinstance(info["errors"], list)
            if info["errors"]:
                assert same(map(type, info["errors"]), str)

            assert isinstance(info["executable"], bool)
            assert isinstance(info["fresh"], bool)
            assert isinstance(info["id"], str)
            assert isinstance(info["name"], str)
            assert isinstance(info["supported"], bool)

            if info["version"] is not None:
                assert isinstance(info["version"], str)

            assert info["id"] == manager_id
