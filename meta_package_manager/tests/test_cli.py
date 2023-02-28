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
import re
import subprocess

import pytest
from boltons.strutils import strip_ansi
from click_extra.tabulate import output_formats

from .. import __version__
from ..bar_plugin import MPMPlugin
from ..base import Operations
from ..pool import pool
from .conftest import default_manager_ids

""" Common tests for all CLI basic features and templates for subcommands. """


TEST_CONF_FILE = """
    # Comment

    top_level_param = "to_ignore"

    [mpm]
    verbosity = "DEBUG"
    blahblah = 234
    manager = ["pip", "npm", "gem"]

    [garbage]

    [mpm.search]
    exact = true
    dummy_parameter = 3
    """


def check_manager_selection(
        result,
        selected=pool.default_manager_ids,
        reference_set=pool.default_manager_ids,
        strict_selection_match=True,
    ):
        """Check that user-selected managers are found in CLI's output.

        At this stage of the CLI, the order in which the managers are reported doesn't
        matter because:

          - ``<stdout>`` and ``<stderr>`` gets mangled
          - paging is async
          - we may introduce parallel execution of manager in the future

        This explain the use of ``set()`` everywhere.

        ``strict_selection_match`` check that all selected managers are properly
        reported in CLI output.

        .. todo::

            Parametrize/fixturize signals to pin point output depending on
            subcommand.
        """
        assert isinstance(selected, (list, tuple, frozenset, set))
        assert isinstance(reference_set, (list, tuple, frozenset, set))

        found_managers = set()
        skipped_managers = set()

        # Strip colors to simplify checks.
        stdout = strip_ansi(result.stdout)
        stderr = strip_ansi(result.stderr)

        for mid in reference_set:
            # List of signals indicating a package manager has been retained by
            # the CLI. Roughly sorted from most specific to more forgiving.
            signals = (
                # Common "not found" warning message.
                f"warning: Skip unavailable {mid} manager." in stderr,
                # Common "not implemented" optional command warning message.
                bool(
                    re.search(
                        rf"warning: {mid} does not implement "
                        rf"Operations\.({'|'.join(Operations.__members__.keys())}).",
                        stderr,
                    )
                ),
                # Stats line at the end of output.
                f"{mid}: " in stderr.splitlines()[-1] if stderr else "",
                # Match output of managers command.
                bool(
                    re.search(
                        rf"│\s+{mid}\s+│.+│\s+(✓|✘).+│\s+(✓|✘)",
                        stdout,
                    )
                ),
                # Install messages.
                bool(
                    re.search(
                        rf"Install \S+ package with {mid}\.\.\.",
                        stderr,
                    )
                ),
                bool(
                    re.search(
                        rf"warning: No \S+ package found on {mid}\.",
                        stderr,
                    )
                ),
                # Upgrade command.
                f"warning: {mid} does not implement upgrade_all_cli." in stderr,
                f"Upgrade all outdated packages from {mid}..." in stderr,
                bool(
                    re.search(
                        rf"Upgrade \S+ with {mid}\.\.\.",
                        stderr,
                    )
                ),
                # Remove messages.
                bool(
                    re.search(
                        rf"Remove \S+ package with {mid}\.\.\.",
                        stderr,
                    )
                ),
                # Sync command.
                f"Sync {mid} package info..." in stderr,
                # Cleanup command.
                f"Cleanup {mid}..." in stderr,
                # Log message for backup command.
                f"Dumping packages from {mid}..." in stderr,
                # Warning message for restore command.
                f"warning: No [{mid}] section found." in stderr,
                # Restoring message.
                f"Restore {mid} packages..." in stderr,
            )

            if True in signals:
                found_managers.add(mid)
            else:
                skipped_managers.add(mid)

        # Check consistency of reported findings.
        assert len(found_managers) + len(skipped_managers) == len(reference_set)
        assert found_managers.union(skipped_managers) == set(reference_set)

        # Compare managers reported by the CLI and those expected.
        if strict_selection_match:
            assert found_managers == set(selected)
        # Partial reporting of found manager is allowed in certain cases like install
        # command, which is only picking one manager among the user's selection.
        else:
            assert set(found_managers).issubset(selected)


class TestBaseCLI:
    """Tests of basic CLI invokations that does not involve subcommands.

    Still includes tests performed only once on an arbitrary, non-destructive
    subcommand, to cover code path shared by all other subcommands. That way we prevent
    duplicating similar tests for each subcommand and improve overall execution of the
    test suite.

    The arbitrary subcommand of our choice is ``mpm managers``, as it is a safe
    read-only operation supposed to work on all platforms, whatever the environment.
    """

    def test_executable_module(self):
        # Locate Python executable.
        py_path = MPMPlugin.locate_bin("python", "python3")
        assert py_path

        process = subprocess.run(
            (py_path, "-m", "meta_package_manager", "--version"),
            capture_output=True,
            encoding="utf-8",
        )

        assert process.returncode == 0
        assert process.stdout.startswith(f"mpm, version {__version__}\n")
        assert not process.stderr

    @pytest.mark.parametrize("selector", ("--manager", "--exclude"))
    def test_invalid_manager_selector(self, invoke, selector):
        result = invoke(selector, "unknown", "managers")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for " in result.stderr
        assert selector in result.stderr

    def test_default_all_managers(self, invoke):
        """Test all available managers are selected by default."""
        result = invoke("managers")
        assert result.exit_code == 0
        check_manager_selection(result)

    @default_manager_ids
    def test_manager_shortcuts(self, invoke, manager_id):
        """Test each manager selection shortcut."""
        result = invoke(f"--{manager_id}", "managers")
        assert result.exit_code == 0
        check_manager_selection(result, {manager_id})

    @pytest.mark.parametrize(
        "args,expected",
        (
            pytest.param(("--manager", "pip"), {"pip"}, id="single_selector"),
            pytest.param(("--pip",), {"pip"}, id="single_flag_selector"),
            pytest.param(("--manager", "pip") * 2, {"pip"}, id="duplicate_selectors"),
            pytest.param(("--pip",) * 2, {"pip"}, id="duplicate_flag_selectors"),
            pytest.param(
                ("--manager", "pip", "--pip"),
                {"pip"},
                id="duplicate_mixed_selectors",
            ),
            pytest.param(
                ("--manager", "pip", "--manager", "gem"),
                {"pip", "gem"},
                id="multiple_selectors",
            ),
            pytest.param(
                ("--manager", "pip", "--gem"),
                {"pip", "gem"},
                id="multiple_mixed_selectors",
            ),
            pytest.param(
                ("--manager", "gem", "--manager", "pip"),
                {"pip", "gem"},
                id="ordered_selectors",
            ),
            pytest.param(
                ("--gem", "--manager", "pip"),
                {"pip", "gem"},
                id="ordered_mixed_selectors",
            ),
            pytest.param(
                ("--exclude", "pip"),
                set(pool.default_manager_ids) - {"pip"},
                id="single_exclusion",
            ),
            pytest.param(
                ("--exclude", "pip") * 2,
                set(pool.default_manager_ids) - {"pip"},
                id="duplicate_exclusions",
            ),
            pytest.param(
                ("--exclude", "pip", "--exclude", "gem"),
                set(pool.default_manager_ids) - {"pip", "gem"},
                id="multiple_exclusions",
            ),
            pytest.param(
                ("--manager", "pip", "--exclude", "gem"),
                {"pip"},
                id="selector_priority_ordered",
            ),
            pytest.param(
                ("--exclude", "gem", "--manager", "pip"),
                {"pip"},
                id="selector_priority_reversed",
            ),
            pytest.param(
                ("--manager", "pip", "--exclude", "pip"),
                set(),
                id="exclusion_override_ordered",
            ),
            pytest.param(
                ("--exclude", "pip", "--manager", "pip"),
                set(),
                id="exclusion_override_reversed",
            ),
        ),
    )
    def test_manager_selection(self, invoke, args, expected):
        result = invoke(*args, "managers")
        assert result.exit_code == 0
        check_manager_selection(result, expected)

    def test_conf_file_overrides_defaults(self, invoke, create_config):
        conf_path = create_config("conf.toml", TEST_CONF_FILE)
        result = invoke("--config", str(conf_path), "managers", color=False)
        assert result.exit_code == 0
        check_manager_selection(result, ("pip", "npm", "gem"))
        assert "debug: " in result.stderr

    def test_conf_file_cli_override(self, invoke, create_config):
        conf_path = create_config("conf.toml", TEST_CONF_FILE)
        result = invoke(
            "--config",
            str(conf_path),
            "--verbosity",
            "CRITICAL",
            "managers",
            color=False,
        )
        assert result.exit_code == 0
        check_manager_selection(result, ("pip", "npm", "gem"))
        assert "error: " not in result.stderr
        assert "warning: " not in result.stderr
        assert "info: " not in result.stderr
        assert "debug: " not in result.stderr


class CLISubCommandTests:
    """All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a template,
    inherited by subcommand specific test cases.
    """

    @pytest.mark.parametrize("opt_stats", ("--stats", "--no-stats", None))
    def test_stats(self, invoke, subcmd, opt_stats):
        """Test the result on all combinations of optional options."""
        result = invoke(opt_stats, subcmd)
        assert result.exit_code == 0


class CLITableTests:
    """Test subcommands whose output is a configurable table.

    A table output is also allowed to be rendered as JSON.
    """

    @pytest.mark.parametrize("mode", output_formats)
    def test_all_table_rendering(self, invoke, subcmd, mode):
        result = invoke("--output-format", mode, subcmd)
        assert result.exit_code == 0

    def test_json_output(self, invoke, subcmd):
        """JSON output is expected to be parseable if read from ``<stdout>``.

        Debug level messages are redirected to <stderr> and are not supposed to interfer
        with this behavior.

        Also checks that JSON output format is not supported by all commands.
        """
        result = invoke("--output-format", "json", "--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "debug:" in result.stderr
        json.loads(result.stdout)
        json.loads(result.output)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)
