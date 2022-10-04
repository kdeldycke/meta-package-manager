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

from __future__ import annotations

import pytest
from click_extra.tests.conftest import destructive

from ..pool import pool
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd(create_config):
    """Seed common subcommand tests with a dummy file and content to allow the CLI to
    not fail on required file input."""
    toml_path = create_config(
        "dummy.toml",
        """
        [dummy_manager]
        fancy_package = "0.0.1"
        """,
    )
    return "restore", str(toml_path)


class TestRestore(CLISubCommandTests):
    @destructive
    def test_default_all_managers(self, invoke, create_config):
        toml_path = create_config(
            "all-managers.toml",
            "".join(
                """
            [{}]
            blah = 123
            """.format(
                    m
                )
                for m in pool.all_manager_ids
            ),
        )

        result = invoke("restore", str(toml_path))
        assert result.exit_code == 0
        assert "all-managers.toml" in result.stderr
        self.check_manager_selection(result)

    @destructive
    @pytest.mark.parametrize("mid", pool.default_manager_ids)
    def test_single_manager(self, invoke, create_config, mid):
        toml_path = create_config(
            "all-managers.toml",
            "".join(
                """
            [{}]
            blah = 123
            """.format(
                    m
                )
                for m in pool.all_manager_ids
            ),
        )

        result = invoke(f"--{mid}", "restore", str(toml_path))
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

    @destructive
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

        result = invoke("--npm", "restore", str(toml_path))
        assert result.exit_code == 0
        assert "pip-npm-dummy.toml" in result.stderr
        assert "Restore \x1b[97mpip\x1b[0m packages..." not in result.stderr
        assert "Restore \x1b[97mnpm\x1b[0m packages..." in result.stderr

    @destructive
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
        assert "Restore \x1b[97mpip\x1b[0m packages..." in result.stderr
        assert "Restore \x1b[97mnpm\x1b[0m packages..." not in result.stderr

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
        assert "Restore \x1b[97mpip\x1b[0m packages..." in result.stderr
