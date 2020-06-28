# -*- coding: utf-8 -*-
#
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

import pytest
import simplejson as json

from .conftest import MANAGER_IDS, unless_macos
from .test_cli import CLISubCommandTests, CLITableTests


@pytest.fixture
def subcmd():
    return "search", "abc"


class TestSearch(CLISubCommandTests, CLITableTests):
    @pytest.mark.parametrize("mid", MANAGER_IDS)
    def test_single_manager(self, invoke, subcmd, mid):
        result = invoke("--manager", mid, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd)
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert data
        assert isinstance(data, dict)
        assert set(data).issubset(MANAGER_IDS)

        for manager_id, info in data.items():
            assert isinstance(manager_id, str)
            assert isinstance(info, dict)

            assert isinstance(info["id"], str)
            assert isinstance(info["name"], str)

            assert set(info) == {"errors", "id", "name", "packages"}

            assert isinstance(info["errors"], list)
            if info["errors"]:
                assert set(map(type, info["errors"])) == {str}

            assert info["id"] == manager_id

            assert isinstance(info["packages"], list)
            for pkg in info["packages"]:
                assert isinstance(pkg, dict)

                assert set(pkg) == {"id", "latest_version", "name"}

                assert isinstance(pkg["id"], str)
                if pkg["latest_version"] is not None:
                    assert isinstance(pkg["latest_version"], str)
                assert isinstance(pkg["name"], str)

    @unless_macos
    def test_unicode_search(self, invoke):
        """ See #16. """
        result = invoke("--manager", "cask", "search", "ubersicht")
        assert result.exit_code == 0
        assert "ubersicht" in result.stdout
        # XXX search command is not fetching yet detailed package infos like
        # names.
        assert "Übersicht" not in result.stdout

        result = invoke("--manager", "cask", "search", "Übersicht")
        assert result.exit_code == 0
        assert "ubersicht" in result.stdout
        assert "Übersicht" not in result.stdout

    def test_exact_search_tokenizer(self, invoke):
        result = invoke("--manager", "pip", "search", "--exact", "sed", color=False)
        assert result.exit_code == 0
        assert "1 package total" in result.stdout
        assert " sed " in result.stdout

        for query in ["SED", "SeD", "sEd*", "*sED*", "_seD-@", "", "_"]:
            result = invoke("--manager", "pip", "search", "--exact", query)
            assert result.exit_code == 0
            assert "0 package total" in result.stdout
            assert "sed" not in result.stdout

    def test_fuzzy_search_tokenizer(self, invoke):
        for query in ["", "_", "_seD-@"]:
            result = invoke("--manager", "pip", "search", query)
            assert result.exit_code == 0
            assert "0 package total" in result.stdout
            assert "sed" not in result.stdout

        for query in ["sed", "SED", "SeD", "sEd*", "*sED*"]:
            result = invoke("--manager", "pip", "search", query, color=False)
            assert result.exit_code == 0
            assert "2 packages total" in result.stdout
            assert " sed " in result.stdout
            assert " SED-cli " in result.stdout

    def test_extended_search_tokenizer(self, invoke):
        for query in ["", "_", "_seD-@"]:
            result = invoke("--manager", "pip", "search", "--extended", query)
            assert result.exit_code == 0
            assert "0 package total" in result.stdout
            assert "sed" not in result.stdout

        for query in ["sed", "SED", "SeD", "sEd*", "*sED*"]:
            result = invoke("--manager", "pip", "search", "--extended", query)
            assert result.exit_code == 0
            assert "23 packages total" in result.stdout
