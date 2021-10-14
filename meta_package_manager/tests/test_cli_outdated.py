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

from string import ascii_lowercase, digits

import pytest
import simplejson as json
from boltons.iterutils import same

from ..pool import DEFAULT_MANAGER_IDS
from .test_cli import CLISubCommandTests, CLITableTests


@pytest.fixture
def subcmd():
    return "outdated"


XBAR_KEYWORDS = frozenset({"shell"}.union({f"param{i}" for i in range(1, 10)}))


class TestOutdated(CLISubCommandTests, CLITableTests):
    @pytest.mark.parametrize("mid", DEFAULT_MANAGER_IDS)
    def test_single_manager(self, invoke, mid, subcmd):
        result = invoke("--manager", mid, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})

    def test_json_parsing(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd)
        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert data
        assert isinstance(data, dict)
        assert set(data).issubset(DEFAULT_MANAGER_IDS)

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

                assert set(pkg) == {
                    "id",
                    "installed_version",
                    "latest_version",
                    "name",
                    "upgrade_cli",
                }

                assert isinstance(pkg["id"], str)
                assert isinstance(pkg["installed_version"], str)
                assert isinstance(pkg["latest_version"], str)
                assert isinstance(pkg["name"], str)
                assert isinstance(pkg["upgrade_cli"], str)

    def test_cli_format_plain(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd, "--cli-format", "plain")
        for outdated in json.loads(result.stdout).values():
            for infos in outdated["packages"]:
                assert isinstance(infos["upgrade_cli"], str)

    def test_cli_format_fragments(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd, "--cli-format", "fragments")
        for outdated in json.loads(result.stdout).values():
            for infos in outdated["packages"]:
                assert isinstance(infos["upgrade_cli"], list)
                assert same(map(type, infos["upgrade_cli"]), str)

    def test_cli_format_xbar(self, invoke, subcmd):
        result = invoke("--output-format", "json", subcmd, "--cli-format", "xbar")
        for outdated in json.loads(result.stdout).values():
            for infos in outdated["packages"]:
                assert isinstance(infos["upgrade_cli"], str)
                assert "param1=" in infos["upgrade_cli"]
                for param in infos["upgrade_cli"].split(" | "):
                    k, v = param.split("=", 1)
                    assert k in XBAR_KEYWORDS
                    assert set(v.lower()).issubset(
                        digits + ascii_lowercase + './-_+="\\@:'
                    )
