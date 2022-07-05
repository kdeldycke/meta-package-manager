# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

# pylint: disable=redefined-outer-name

from __future__ import annotations

import dataclasses
import json
import re
from time import sleep

import pytest
from boltons.iterutils import same
from click_extra.tests.conftest import unless_macos

from ..base import Package
from ..pool import pool
from .test_cli import CLISubCommandTests, CLITableTests


@pytest.fixture
def subcmd():
    return "search", "abc"


class TestSearch(CLISubCommandTests, CLITableTests):
    @pytest.mark.parametrize("mid", pool.default_manager_ids)
    def test_single_manager(self, invoke, subcmd, mid):
        result = invoke(f"--{mid}", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd)
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

            assert set(info) == {"errors", "id", "name", "packages"}

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

    @unless_macos
    def test_unicode_search(self, invoke):
        """See #16."""
        result = invoke("--mas", "search", "钉钉")
        assert result.exit_code == 0
        assert "钉钉" in result.stdout

    # PyPi's online search API was at first rate-limited. So we added an artificial
    # 2-seconds delay to prevent the following error:
    #   xmlrpc.client.Fault: <Fault -32500: 'HTTPTooManyRequests: The action could not
    #   be performed because there were too many requests by the client. Limit may
    #   reset in 1 seconds.'>
    # Then the search API was shutdown altogether as it was hammered (see
    # https://github.com/pypa/pip/issues/5216#issuecomment-744605466) which produced
    # this error:
    #   xmlrpc.client.Fault: <Fault -32500: "RuntimeError: PyPI's XMLRPC API has been
    #   temporarily disabled due to unmanageable load and will be deprecated in the
    #   near future. See https://status.python.org/ for more information.">

    skip_pip_search = pytest.mark.skip(reason="pip search is deprecated")

    @skip_pip_search
    def test_exact_search_one_result(self, invoke):
        sleep(2)
        result = invoke("--pip", "search", "--exact", "sed", color=False)
        assert result.exit_code == 0
        assert "1 package total" in result.stdout
        assert " sed " in result.stdout

    @skip_pip_search
    @pytest.mark.parametrize(
        "query", ("SED", "SeD", "sEd*", "*sED*", "_seD-@", "", "_")
    )
    def test_exact_search_no_result(self, invoke, query):
        sleep(2)
        result = invoke("--pip", "search", "--exact", query)
        assert result.exit_code == 0
        assert "0 package total" in result.stdout
        assert "sed" not in result.stdout

    @skip_pip_search
    @pytest.mark.parametrize("query", ("", "_", "_seD-@"))
    def test_fuzzy_search_no_results(self, invoke, query):
        sleep(2)
        result = invoke("--pip", "search", query)
        assert result.exit_code == 0
        assert "0 package total" in result.stdout
        assert "sed" not in result.stdout

    @skip_pip_search
    @pytest.mark.parametrize("query", ("sed", "SED", "SeD", "sEd*", "*sED*"))
    def test_fuzzy_search_multiple_results(self, invoke, query):
        sleep(2)
        result = invoke("--pip", "search", query, color=False)
        assert result.exit_code == 0
        assert "2 packages total" in result.stdout
        assert " sed " in result.stdout
        assert " SED-cli " in result.stdout

    @skip_pip_search
    @pytest.mark.parametrize("query", ("", "_", "_seD-@"))
    def test_extended_search_no_results(self, invoke, query):
        sleep(2)
        result = invoke("--pip", "search", "--extended", query)
        assert result.exit_code == 0
        assert "0 package total" in result.stdout
        assert "sed" not in result.stdout

    @skip_pip_search
    @pytest.mark.parametrize("query", ("sed", "SED", "SeD", "sEd*", "*sED*"))
    def test_extended_search_multiple_results(self, invoke, query):
        sleep(2)
        result = invoke("--pip", "search", "--extended", query)
        assert result.exit_code == 0
        last_line = result.stdout.splitlines()[-1]
        assert last_line
        msg_match = re.match(
            r"^([0-9]+) packages? total \(pip: ([0-9]+)\).$", last_line
        )
        assert msg_match
        assert same(msg_match.groups())
        # We should find lots of results for this package search.
        assert int(msg_match.groups()[0]) >= 20

    def test_search_highlight(self, invoke):
        """We search on cargo as it is available on all platforms.

        The search on the small ``co`` string is producing all variations of multiple
        ``co`` substring matches and highlights.
        """
        result = invoke("--cargo", "search", "co")
        assert result.exit_code == 0
        # co
        assert "│ \x1b[32m\x1b[1mco\x1b[0m " in result.stdout
        # acco
        assert "│ ac\x1b[32m\x1b[1mco\x1b[0m " in result.stdout
        # bicoro
        assert "│ bi\x1b[32m\x1b[1mco\x1b[0mro " in result.stdout
        # cocomo-core
        assert (
            "│ \x1b[32m\x1b[1mcoco\x1b[0mmo-\x1b[32m\x1b[1mco\x1b[0mre "
            in result.stdout
        )
        # cocomo-tui
        assert "│ \x1b[32m\x1b[1mcoco\x1b[0mmo-tui " in result.stdout
