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
import sys
from textwrap import dedent
from typing import Collection, Iterator

import pytest
from boltons.strutils import strip_ansi
from click_extra.tabulate import output_formats

from meta_package_manager import __version__
from meta_package_manager.pool import pool

from .conftest import default_manager_ids

""" Common tests for all CLI basic features and templates for subcommands. """


TEST_CONF_FILE = """\
# Comment

top_level_param = "to_ignore"

[mpm]
verbosity = "DEBUG"
blahblah = 234
manager = ["uv", "npm", "gem"]

[garbage]

[mpm.search]
exact = true
dummy_parameter = 3
"""


class InspectCLIOutput:
    @staticmethod
    def evaluate_signals(mid: str, stdout: str, stderr: str) -> Iterator[bool]:
        """Search in the CLI output for evidence that a manager has been retained.

        ..tip::

            In the implementation, signals should be roughly sorted from most specific
            to more forgiving.
        """
        raise NotImplementedError

    def check_manager_selection(
        self,
        result,
        selected: Iterator[str] | tuple[str, ...] = pool.default_manager_ids,
        reference_set: Collection[str] = pool.default_manager_ids,
        strict_selection_match: bool = True,
    ):
        """Check that user-selected managers are found in CLI's output.

        To establish that ``mpm`` CLI is properly selecting managers, we search for
        signals in CLI logs, by matching regular expressions against ``<stdout>`` and
        ``<stderr>``. This strategy close the gap of testing internal code testing and
        end user experience.

        Signals are expected to be implemented for each subcommand by the
        ``evaluate_signals()`` method.

        ``strict_selection_match`` check that all selected managers are properly
        reported in CLI output and none are missing.

        .. caution::

            At this stage of the CLI execution, the order in which the managers are
            reported doesn't matter because:

            - ``<stdout>`` and ``<stderr>`` gets mangled
            - `paging is async
                <https://github.com/kdeldycke/meta-package-manager/issues/528>`_
            - we may introduce `parallel execution of managers in the future
                <https://github.com/kdeldycke/meta-package-manager/issues/529>`_

            This explain the use of ``set()`` everywhere in this method.
        """
        found_managers = set()
        skipped_managers = set()

        # Strip colors to simplify checks.
        stdout = strip_ansi(result.stdout)
        stderr = strip_ansi(result.stderr)

        for mid in reference_set:
            signals_eval = self.evaluate_signals(mid, stdout, stderr)
            if True in signals_eval:
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


class TestCommonCLI:
    """Single tests for CLI behavior shared by all subcommands.

    If we have to, we only run the test on a single, non-destructive subcommand
    (like ``mpm installed`` or ``mpm managers``). Not all subcommands are tested.

    That way we prevent running similar tests which are operating on the same, shared
    code path. Thus improving overall execution of the test suite.
    """

    def test_executable_module(self):
        """Try running the CLI as a Python module.

        Use the current Python executable so we don't have to worry about missing
        dependencies.
        """
        process = subprocess.run(
            (sys.executable, "-m", "meta_package_manager", "--version"),
            capture_output=True,
            encoding="utf-8",
        )
        assert process.returncode == 0
        assert not process.stderr
        assert (
            process.stdout
            == f"\x1b[97mmpm\x1b[0m, version \x1b[32m{__version__}\x1b[0m\n"
        )

    def test_timeout(self, invoke):
        """Check that the CLI exits with an error when a timeout is reached."""
        result = invoke("--timeout", "1", "outdated")
        assert result.exit_code == 1
        assert isinstance(result.exception, subprocess.TimeoutExpired)

    @pytest.mark.parametrize(
        ("stats_arg", "active_stats"),
        (("--stats", True), ("--no-stats", False), (None, True)),
    )
    def test_stats(self, invoke, stats_arg, active_stats):
        """Test the result on all combinations of optional statistics options."""
        result = invoke(stats_arg, "installed")
        assert result.exit_code == 0
        stats_match = re.match(
            r"\d+ packages total \((\w+: \d+(, )?)+\)\.",
            # Last line of stderr.
            result.stderr.splitlines()[-1],
        )
        assert active_stats is bool(stats_match)


class TestManagerSelection(InspectCLIOutput):
    """Test selection of package managers to use.

    Tests are performed here on the ``mpm managers`` subcommand, as it is a safe
    read-only operation that is supposed to work on all platforms, whatever the
    environment.

    There is not need to test all subcommands, as the selection logic and code path is
    shared by all of them. See the implementation in
    ``meta_package_manager.pool.ManagerPool.select_managers()``.
    """

    @staticmethod
    def evaluate_signals(mid: str, stdout: str, stderr: str) -> Iterator[bool]:
        """Borrow the signals from the ``--manager`` test suite.

        Module is imported inplace to avoid circular import.
        """
        from .test_cli_managers import TestManagers

        return TestManagers.evaluate_signals(  # type: ignore[no-any-return]
            mid,
            stdout,
            stderr,
        )

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
        self.check_manager_selection(result)

    @default_manager_ids
    def test_manager_shortcuts(self, invoke, manager_id):
        """Test each manager selection shortcut."""
        result = invoke(f"--{manager_id}", "managers")
        assert result.exit_code == 0
        self.check_manager_selection(result, {manager_id})

    @pytest.mark.parametrize(
        ("args", "expected"),
        (
            pytest.param(("--manager", "uv"), {"uv"}, id="single_selector"),
            pytest.param(("--uv",), {"uv"}, id="single_flag_selector"),
            pytest.param(("--manager", "uv") * 2, {"uv"}, id="duplicate_selectors"),
            pytest.param(("--uv",) * 2, {"uv"}, id="duplicate_flag_selectors"),
            pytest.param(
                ("--manager", "uv", "--uv"),
                {"uv"},
                id="duplicate_mixed_selectors",
            ),
            pytest.param(
                ("--manager", "uv", "--manager", "gem"),
                {"uv", "gem"},
                id="multiple_selectors",
            ),
            pytest.param(
                ("--manager", "uv", "--gem"),
                {"uv", "gem"},
                id="multiple_mixed_selectors",
            ),
            pytest.param(
                ("--gem", "--uv"),
                {"uv", "gem"},
                id="ordered_selectors",
            ),
            pytest.param(
                ("--gem", "--manager", "uv"),
                {"uv", "gem"},
                id="ordered_mixed_selectors",
            ),
            pytest.param(
                ("--no-uv",),
                set(pool.default_manager_ids) - {"uv"},
                id="single_exclusion",
            ),
            pytest.param(
                ("--no-uv",) * 2,
                set(pool.default_manager_ids) - {"uv"},
                id="duplicate_exclusions",
            ),
            pytest.param(
                ("--no-uv", "--no-gem"),
                set(pool.default_manager_ids) - {"uv", "gem"},
                id="multiple_exclusions",
            ),
            pytest.param(
                ("--uv", "--no-gem"),
                {"uv"},
                id="selector_priority_ordered",
            ),
            pytest.param(
                ("--no-gem", "--uv"),
                {"uv"},
                id="selector_priority_reversed",
            ),
            pytest.param(
                ("--uv", "--no-uv"),
                None,
                id="exclusion_precedence_ordered",
            ),
            pytest.param(
                ("--no-uv", "--uv"),
                None,
                id="exclusion_precedence_reversed",
            ),
        ),
    )
    def test_manager_selection(self, invoke, args, expected):
        result = invoke(*args, "managers")
        if expected is None:
            assert result.exit_code == 2
            assert not result.stdout
            assert result.stderr.endswith(
                "\x1b[31m\x1b[1mcritical\x1b[0m: No manager selected.\n"
            )
        else:
            assert result.exit_code == 0
            self.check_manager_selection(result, expected)

    @pytest.mark.skip(reason="Generated config file is not isolated from other tests.")
    def test_conf_file_overrides_defaults(self, invoke, create_config):
        conf_path = create_config("conf.toml", TEST_CONF_FILE)
        result = invoke("--config", str(conf_path), "managers", color=False)
        assert result.exit_code == 0
        self.check_manager_selection(result, ("uv", "npm", "gem"))
        assert "debug: " in result.stderr

    @pytest.mark.skip(reason="Generated config file is not isolated from other tests.")
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
        self.check_manager_selection(result, ("uv", "npm", "gem"))
        assert "error: " not in result.stderr
        assert "warning: " not in result.stderr
        assert "info: " not in result.stderr
        assert "debug: " not in result.stderr

    @pytest.mark.skip(reason="Generated config file is not isolated from other tests.")
    def test_conf_and_parameter_mix_keep_order(self, invoke, create_config):
        """"""
        conf_path = create_config(
            "conf.toml",
            dedent("""\
                [mpm]
                npm = true
                flatpak = false
                manager = ["gem"]
                cargo = false
                pipx = true
                """),
        )
        result = invoke(
            "--uv", "--no-pip", "--config", str(conf_path), "managers", color=False
        )
        assert result.exit_code == 0
        self.check_manager_selection(result, ("uv", "npm", "gem", "pipx"))


class CLISubCommandTests(InspectCLIOutput):
    """All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a template,
    inherited by sub-command specific test cases.
    """


class CLITableTests:
    """Test subcommands whose output is a configurable table.

    Any table output is also allowed to be rendered as JSON.
    """

    @pytest.mark.parametrize("mode", output_formats)
    def test_all_table_rendering(self, invoke, mode):
        result = invoke("--output-format", mode, "installed")
        assert result.exit_code == 0

    def test_json_output(self, invoke, subcmd):
        """JSON output is expected to be parseable if read from ``<stdout>``.

        Debug level messages are redirected to <stderr> and are not supposed to interfere
        with this behavior.
        """
        result = invoke("--output-format", "json", "--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "debug" in result.stderr
        json.loads(result.stdout)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)
