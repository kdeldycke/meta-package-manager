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

from meta_package_manager.pool import pool
from meta_package_manager.tables import MANAGERS_COLUMNS

from .conftest import all_manager_ids, unsupported_manager_ids
from .test_cli import CLISubCommandTests, CLITableTests, managers_table_signals


@pytest.fixture
def subcmd():
    return "managers"


class TestManagers(CLISubCommandTests, CLITableTests):
    columns_registry = MANAGERS_COLUMNS
    columns_test_pair = ("manager_id", "version")

    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from managers_table_signals(mid, stdout, stderr)

    @all_manager_ids
    def test_all_managers(self, invoke, subcmd, manager_id):
        """Check only the selected manager is listed."""
        result = invoke(f"--{manager_id}", "--all-managers", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(
            result,
            {manager_id},
            reference_set=pool.all_manager_ids,
        )

    @unsupported_manager_ids
    def test_unsupported_managers(self, invoke, subcmd, manager_id):
        """A manager named by the user is reported whatever its state: the default
        view widens to `supported` on an explicit selection, so the row spelling out
        why `mpm` cannot use it is the answer the selector asked for."""
        result = invoke(f"--{manager_id}", subcmd, color=False)
        assert result.exit_code == 0
        self.check_manager_selection(result, set())
        assert manager_id in result.stdout

    @pytest.mark.parametrize(
        ("view_args", "expected_ids"),
        (
            pytest.param(
                (),
                lambda: {
                    mid for mid in pool.default_manager_ids if pool[mid].available
                },
                id="default-view-is-detected",
            ),
            pytest.param(
                ("--view", "detected"),
                lambda: {
                    mid for mid in pool.default_manager_ids if pool[mid].available
                },
                id="detected",
            ),
            pytest.param(
                ("--view", "supported"),
                lambda: set(pool.default_manager_ids),
                id="supported",
            ),
            pytest.param(
                ("--view", "all"),
                lambda: set(pool.all_manager_ids),
                id="all",
            ),
        ),
    )
    def test_view_widths(self, invoke, subcmd, view_args, expected_ids):
        """Each view reports its own nested slice of the pool."""
        result = invoke("--table-format", "json", subcmd, *view_args)
        assert result.exit_code == 0
        assert set(json.loads(result.stdout)) == expected_ids()

    def test_all_managers_flag_selects_widest_view(self, invoke, subcmd):
        """The global flag keeps naming the widest view, as `--view all` does."""
        result = invoke("--all-managers", "--table-format", "json", subcmd)
        assert result.exit_code == 0
        assert set(json.loads(result.stdout)) == set(pool.all_manager_ids)

    def test_default_view_drops_constant_columns(self, invoke, subcmd):
        """`Supported` and `Executable` are a ✓ on every detected row, so the
        default view leaves them out and the wider ones bring them back."""
        labels = {spec.id: spec.label for spec, _ in MANAGERS_COLUMNS}
        dropped = (labels["supported"], labels["executable"])

        detected = invoke(subcmd, color=False)
        assert detected.exit_code == 0
        assert not any(label in detected.stdout for label in dropped)

        for view in ("supported", "all"):
            wider = invoke(subcmd, "--view", view, color=False)
            assert wider.exit_code == 0
            assert all(label in wider.stdout for label in dropped)

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--table-format", "json", subcmd)
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert data
        assert isinstance(data, dict)
        assert set(data) <= set(pool.default_manager_ids)

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


def test_managers_stamps_global_timeout(invoke):
    """The version probes behind the table's detection columns fire in the pool's
    warm-up round, right after selection, so the `managers` subcommand must forward
    the global `--timeout` for the pool to bind it on each candidate beforehand.
    An unstamped instance falls back to the 120-second read-only default, letting a
    wedged binary hold the whole round for that long.
    """
    original = pool["pip"].timeout
    try:
        result = invoke("--timeout", "987", "managers")
        assert result.exit_code == 0
        assert pool["pip"].timeout == 987
    finally:
        pool["pip"].timeout = original
