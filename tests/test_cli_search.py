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
from extra_platforms.pytest import skip_github_ci, unless_macos

from meta_package_manager.capabilities import Operations
from meta_package_manager.tables import SEARCH_COLUMNS

from .test_cli import CLISubCommandTests, CLITableTests, check_packages_payload


@pytest.fixture
def subcmd():
    # "excel" deterministically surfaces an upstream `mas` record whose
    # `description` carries an unescaped U+0010 byte and two U+2028 line
    # separators (`PDF to Excel OCR Converter`, adamID 1316315027). Searching
    # for it gives real-world coverage of the parser workaround in
    # `meta_package_manager.managers.mas._parse_json_stream`. Upstream bug:
    # https://github.com/mas-cli/mas/issues/1248
    return "search", "excel"


class TestSearch(CLISubCommandTests, CLITableTests):
    columns_registry = SEARCH_COLUMNS

    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # The glued `:<mid>:` label form matches whatever level the
            # message lands at: demoted to DEBUG for implicit selection
            # (`mpm search`), INFO for explicit ones.
            f":{mid}: Does not implement {Operations.search}." in stderr,
            f":{mid}: Skipped:" in stderr,
            # Stats line at the end of output.
            f"{mid}: " in stderr.splitlines()[-1] if stderr else "",
        )

    def test_description_column_selection(self, invoke, fake_pool):
        """The description column hides by default, appears with `--description`,
        and an explicit `--columns` selection is authoritative either way."""
        # Hidden by default.
        result = invoke("search", "match-me", color=False)
        assert result.exit_code == 0
        assert "Description" not in result.stdout

        # The --description shorthand adds the column.
        result = invoke("--description", "search", "match-me", color=False)
        assert result.exit_code == 0
        assert "Description" in result.stdout

        # An explicit --columns selection surfaces it without the shorthand...
        result = invoke(
            "search", "match-me", "--columns", "package_id,description", color=False
        )
        assert result.exit_code == 0
        header = next(line for line in result.stdout.splitlines() if "│" in line)
        assert "Description" in header
        assert "Manager" not in header

        # ...and wins over the shorthand when it leaves the column out.
        result = invoke(
            "--description",
            "search",
            "match-me",
            "--columns",
            "package_id",
            color=False,
        )
        assert result.exit_code == 0
        assert "Description" not in result.stdout

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--table-format", "json", subcmd)
        check_packages_payload(result)

    @unless_macos
    @skip_github_ci
    def test_unicode_search(self, invoke):
        """Check `mpm` is accepting unicode as search query.

        `mas` is the only manager we have that is accepting unicode characters for
        its package names. We perform a search with it so we can prove `mpm` is
        supporting it too:

        ```{code-block} shell-session

        $ mpm --mas search 钉
        ╭────────────┬───────────────────┬─────────┬────────────────╮
        │ Package ID │ Name              │ Manager │ Latest version │
        ├────────────┼───────────────────┼─────────┼────────────────┤
        │ 1435447041 │ 钉钉 - 让进步发生 │ mas     │ 7.6.57         │
        ╰────────────┴───────────────────┴─────────┴────────────────╯
        ```

        Test originates from #16.

        ```{caution}
        Test is skipped on GitHub Actions as `mas` does not have access there
        to a registered account on the App Store. So the search returns no results.
        ```
        """
        result = invoke("--color", "--mas", "search", "钉")
        assert result.exit_code == 0
        assert "钉钉" in result.stdout
        # The match is emphasized with the theme's search style (green since
        # click-extra 8.4.0, which dropped the bold).
        assert " \x1b[32m钉钉\x1b[0m " in result.stdout

    def test_search_highlight(self, invoke):
        """We search on cargo as it is available on all platforms.

        The search on the small `co` string is producing all variations of multiple
        `co` substring matches and highlights.
        """
        result = invoke("--color", "--cargo", "search", "co")
        assert result.exit_code == 0
        # crates.io intermittently throttles CI runners into empty search
        # results: an empty table means there is nothing to highlight, not a
        # highlighting bug.
        data_rows = [
            line for line in result.stdout.splitlines() if line.startswith("│")
        ]
        if len(data_rows) <= 1:  # Header row only: the search came back empty.
            pytest.skip("cargo search returned no results (registry throttling)")
        # Check that the highlight ANSI sequence for "co" appears in the output.
        # Cargo search results change over time, so we only verify that
        # highlighting is applied, not which specific packages are returned.
        # click-extra 7.19 dropped the bold code from theme().search, leaving
        # the green color as the only highlight style.
        highlight_pattern = "\x1b[32mco\x1b[0m"
        assert highlight_pattern in result.stdout
