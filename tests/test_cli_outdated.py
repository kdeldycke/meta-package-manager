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

import dataclasses
import json

import pytest
from boltons.iterutils import same

from meta_package_manager.capabilities import Operations
from meta_package_manager.package import Package
from meta_package_manager.pool import pool

from .test_cli import CLISubCommandTests, CLITableTests


@pytest.fixture
def subcmd():
    return "outdated"


BAR_PLUGIN_KEYWORDS = frozenset({"shell"}.union({f"param{i}" for i in range(1, 10)}))


class TestOutdated(CLISubCommandTests, CLITableTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # Log-level prefix is omitted because the message is demoted to
            # DEBUG for implicit selection (``mpm outdated``) but stays at
            # WARNING/INFO for explicit ones (``mpm --<mid> outdated``).
            f"{mid} does not implement {Operations.outdated}" in stderr,
            f"Skip {mid} manager:" in stderr,
            # Stats line at the end of output.
            f"{mid}: " in stderr.splitlines()[-1] if stderr else "",
        )

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--table-format", "json", subcmd)
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert data
        assert isinstance(data, dict)
        assert set(data).issubset(pool.default_manager_ids)

        for manager_id, info in data.items():
            assert isinstance(manager_id, str)
            assert isinstance(info, dict)

            assert isinstance(info["id"], str)
            assert isinstance(info["name"], str)

            keys = {"errors", "id", "name", "packages"}
            if "upgrade_all_cli" in info:
                assert isinstance(info["upgrade_all_cli"], str)
                keys.add("upgrade_all_cli")
            assert set(info) == keys

            assert isinstance(info["errors"], list)
            if info["errors"]:
                assert same(map(type, info["errors"]), str)

            assert info["id"] == manager_id

            assert isinstance(info["packages"], list)
            for pkg in info["packages"]:
                assert isinstance(pkg, dict)

                fields = {f.name for f in dataclasses.fields(Package)}
                assert set(pkg).issubset(fields)

                for f in pkg:
                    assert isinstance(pkg[f], str) or pkg[f] is None

    @pytest.mark.parametrize(
        ("args", "expected_ids"),
        (
            # No query: every outdated package is listed.
            ((), {"fake-pkg-alpha"}),
            # Fuzzy query narrows the listing to matching IDs.
            (("alpha",), {"fake-pkg-alpha"}),
            # fake-pkg-beta is installed but not outdated, so it never surfaces.
            (("beta",), set()),
            (("absent",), set()),
            # Exact query requires a verbatim ID or name match.
            (("--exact", "fake-pkg-alpha"), {"fake-pkg-alpha"}),
            (("--exact", "alpha"), set()),
        ),
    )
    def test_query_filter(self, invoke, fake_pool, args, expected_ids):
        result = invoke("--table-format", "json", "outdated", *args)
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        package_ids = {pkg["id"] for info in data.values() for pkg in info["packages"]}
        assert package_ids == expected_ids

    def test_query_highlight(self, invoke, fake_pool):
        """The matched substring is wrapped in the theme's green search style."""
        result = invoke("--color", "outdated", "alpha")
        assert result.exit_code == 0
        assert "\x1b[32malpha\x1b[0m" in result.stdout
