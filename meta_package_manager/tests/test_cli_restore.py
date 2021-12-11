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

import pytest

from ..pool import ALL_MANAGER_IDS, DEFAULT_MANAGER_IDS
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd(create_config):
    """Seed common subcommand tests with a dummy file and content to allow the
    CLI to not fail on required file input."""
    toml_path = create_config(
        "dummy.toml",
        """
        [dummy_manager]
        fancy_package = "0.0.1"
        """,
    )
    return "restore", str(toml_path)


class TestRestore(CLISubCommandTests):
    def test_default_all_managers(self, invoke, create_config):
        toml_path = create_config(
            "all-managers.toml",
            "".join(
                (
                    """
            [{}]
            blah = 123
            """.format(
                        m
                    )
                    for m in ALL_MANAGER_IDS
                )
            ),
        )

        result = invoke("restore", str(toml_path))
        assert result.exit_code == 0
        assert "all-managers.toml" in result.stderr
        self.check_manager_selection(result)

    @pytest.mark.parametrize("mid", DEFAULT_MANAGER_IDS)
    def test_single_manager(self, invoke, create_config, mid):
        toml_path = create_config(
            "all-managers.toml",
            "".join(
                (
                    """
            [{}]
            blah = 123
            """.format(
                        m
                    )
                    for m in ALL_MANAGER_IDS
                )
            ),
        )

        result = invoke("--manager", mid, "restore", str(toml_path))
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})

    def test_ignore_unrecognized_manager(self, invoke, create_config):
        toml_path = create_config(
            "unrecognized.toml",
            """
            [random_section]
            blah = 123
            """,
        )

        result = invoke("--verbosity", "INFO", "restore", str(toml_path))
        assert result.exit_code == 0
        assert "unrecognized.toml" in result.stderr
        assert "Ignore [random_section] section" in result.stderr

    def test_restore_single_manager(self, invoke, create_config):
        toml_path = create_config(
            "pip-npm-dummy.toml",
            """
            [pip]
            fancy_package = "0.0.1"

            [npm]
            dummy_package = "2.2.2"
            """,
        )

        result = invoke("--manager", "npm", "restore", str(toml_path))
        assert result.exit_code == 0
        assert "pip-npm-dummy.toml" in result.stderr
        assert "Restore pip" not in result.stderr
        assert "Restore npm" in result.stderr

    def test_restore_excluded_manager(self, invoke, create_config):
        toml_path = create_config(
            "pip-npm-dummy.toml",
            """
            [pip]
            fancy_package = "0.0.1"

            [npm]
            dummy_package = "2.2.2"
            """,
        )

        result = invoke("--exclude", "npm", "restore", str(toml_path))
        assert result.exit_code == 0
        assert "pip-npm-dummy.toml" in result.stderr
        assert "Restore pip" in result.stderr
        assert "Restore npm" not in result.stderr

    def test_empty_manager(self, invoke, create_config):
        toml_path = create_config(
            "pip-empty.toml",
            """
            [pip]
            """,
        )

        result = invoke("restore", str(toml_path))
        assert result.exit_code == 0
        assert "pip-empty.toml" in result.stderr
        assert "Restore pip" in result.stderr
