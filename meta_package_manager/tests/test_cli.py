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

import json
import re
import subprocess

import pytest
from boltons.strutils import strip_ansi
from click_extra.tabulate import output_formats

from .. import __version__
from ..bar_plugin import MPMPlugin  # type: ignore
from ..base import Operations
from ..pool import pool

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


class TestBaseCLI:

    """This collection is testing basic CLI behavior without involving any subcommands.

    Also includes a bunch of tests performed once on an arbitrary sub-command, for
    situation when the tested behavior is shared by all subcommands. The arbitrary sub-
    command is `managers`, as it is a safe read-only operation supposed to work on all
    platforms, whatever the environment.
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

    def test_conf_file_overrides_defaults(self, invoke, create_config):
        conf_path = create_config("conf.toml", TEST_CONF_FILE)
        result = invoke("--config", str(conf_path), "managers", color=False)
        assert result.exit_code == 0
        for mid in ("pip", "npm", "gem"):
            assert re.search(rf"│ {mid}\s+│ ", result.stdout)
        assert " brew " not in result.stdout
        assert " brew cask " not in result.stdout
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
        for mid in ("pip", "npm", "gem"):
            assert re.search(rf"│ {mid}\s+│ ", result.stdout)
        assert " brew " not in result.stdout
        assert " cask " not in result.stdout
        assert "error: " not in result.stderr
        assert "warning: " not in result.stderr
        assert "info: " not in result.stderr
        assert "debug: " not in result.stderr


class CLISubCommandTests:

    """All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a template,
    inherited by sub-command specific test cases.
    """

    @pytest.mark.parametrize("opt_stats", ("--stats", "--no-stats", None))
    def test_stats(self, invoke, subcmd, opt_stats):
        """Test the result on all combinations of optional options."""
        result = invoke(opt_stats, subcmd)
        assert result.exit_code == 0

    strict_selection_match = True
    """All user-selected managers are expected to be reported in CLI output."""

    @classmethod
    def check_manager_selection(
        cls,
        result,
        selected=pool.default_manager_ids,
        reference_set=pool.default_manager_ids,
    ):
        """Check that user-selected managers are found in CLI's output.

        At this stage of the CLI, the order in which the managers are reported doesn't
        matter because:
        * ``<stdout>`` and ``<stderr>`` gets mangled
        * paging is async
        * we may introduce parallel execution of manager in the future

        This explain the use of ``set()`` everywhere.

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
        if cls.strict_selection_match:
            assert found_managers == set(selected)
        # Partial reporting of found manager is allowed in certain cases like install
        # command, which is only picking one manager among the user's selection.
        else:
            assert set(found_managers).issubset(selected)

    @pytest.mark.parametrize("selector", ("--manager", "--exclude"))
    def test_invalid_manager_selector(self, invoke, subcmd, selector):
        result = invoke(selector, "unknown", subcmd)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for " in result.stderr
        assert selector in result.stderr

    def test_default_all_managers(self, invoke, subcmd):
        """Test all available managers are selected by default."""
        result = invoke(subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result)

    @pytest.mark.parametrize("mid", pool.default_manager_ids)
    def test_manager_shortcuts(self, invoke, subcmd, mid):
        """Test each manager selection shortcut."""
        result = invoke(f"--{mid}", subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})

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
    def test_manager_selection(self, invoke, subcmd, args, expected):
        result = invoke(*args, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, expected)


class CLITableTests:

    """Test subcommands whose output is a configurable table.

    A table output is also allowed to be rendered as JSON.
    """

    @pytest.mark.parametrize("mode", output_formats)
    def test_all_table_rendering(self, invoke, subcmd, mode):
        result = invoke("--output-format", mode, subcmd)
        assert result.exit_code == 0

    def test_json_output(self, invoke, subcmd):
        """JSON output is expected to be parseable if read from <stdout>.

        Debug level messages are redirected to <stderr> and are not supposed to
        interfer with this behavior.

        Also checks that JSON output format is not supported by all commands.
        """
        result = invoke("--output-format", "json", "--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "debug:" in result.stderr
        json.loads(result.stdout)
        json.loads(result.output)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)
