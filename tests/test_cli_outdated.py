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

import pytest

from meta_package_manager.tables import OUTDATED_COLUMNS

from .test_cli import (
    CLIQueryTests,
    CLISubCommandTests,
    CLITableTests,
    check_packages_payload,
)


@pytest.fixture
def subcmd():
    return "outdated"


BAR_PLUGIN_KEYWORDS = frozenset({"shell"}.union({f"param{i}" for i in range(1, 10)}))


class TestOutdated(CLISubCommandTests, CLITableTests, CLIQueryTests):
    columns_registry = OUTDATED_COLUMNS

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--table-format", "json", subcmd)
        check_packages_payload(result, optional_keys=frozenset({"upgrade_all_cli"}))

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
        self.check_filtered_ids(result, expected_ids)
