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

import logging
import re
from pathlib import Path

import click
import pytest
import simplejson as json
from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from cli_helpers.tabular_output import TabularOutputFormatter

from .. import __version__, logger
from ..cli import RENDERING_MODES, WINDOWS_MODE_BLACKLIST
from .conftest import MANAGER_IDS, unless_windows

""" Common tests for all CLI basic features and templates for subcommands. """


def test_real_fs():
    """Check a simple test is not caught into the CLI runner fixture which is
    encapsulating all filesystem access into temporary directory structure."""
    assert str(Path(__file__)).startswith(str(Path.cwd()))


def test_temporary_fs(runner):
    """Check the CLI runner fixture properly encapsulated the filesystem in
    temporary directory."""
    assert not str(Path(__file__)).startswith(str(Path.cwd()))


class TestBaseCLI:

    """This collection is testing basic CLI behavior shared by all
    subcommands.

    Also regroups tests not involving subcommands.

    Also includes a bunch of tests performed once on an arbitrary sub-command,
    for situation when the tested behavior is shared by all subcommands. In
    that case we choosed `managers` as it is a safe read-only operation
    supposed to work on all platforms whatever the environment.
    """

    def test_bare_call(self, invoke):
        result = invoke()
        assert result.exit_code == 0
        assert "Usage: " in result.stdout
        assert not result.stderr

    def test_main_help(self, invoke):
        result = invoke("--help")
        assert result.exit_code == 0
        assert "Usage: " in result.stdout
        assert not result.stderr

    def test_version(self, invoke):
        result = invoke("--version")
        assert result.exit_code == 0
        assert __version__ in result.stdout
        assert not result.stderr

    def test_unknown_option(self, invoke):
        result = invoke("--blah")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: no such option: --blah" in result.stderr

    def test_unknown_command(self, invoke):
        result = invoke("blah")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: No such command 'blah'." in result.stderr

    def test_required_command(self, invoke):
        result = invoke("--verbosity", "DEBUG")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing command." in result.stderr

    def test_unrecognized_verbosity(self, invoke):
        result = invoke("--verbosity", "random", "managers")
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for '--verbosity' / '-v'" in result.stderr

    @pytest.mark.parametrize("level", ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
    def test_verbosity(self, invoke, level):
        result = invoke("--verbosity", level, "managers")
        assert result.exit_code == 0
        assert logger.level == getattr(logging, level)
        assert "══════" in result.stdout
        if level == "DEBUG":
            assert "debug: " in result.stderr
        else:
            assert "debug: " not in result.stderr

    @unless_windows
    @pytest.mark.parametrize("mode", WINDOWS_MODE_BLACKLIST)
    def test_check_failing_unicode_rendering(self, mode):
        """Check internal assumption that some rendering unicode table
        rendering modes fails in Windows console."""
        table_formatter = TabularOutputFormatter(mode)
        with pytest.raises(UnicodeEncodeError):
            click.echo(
                table_formatter.format_output(
                    ((1, 87), (2, 80), (3, 79)), ("day", "temperature")
                )
            )


class CLISubCommandTests:

    """All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a
    template, inherited sub-command specific files.
    """

    def test_help(self, invoke, subcmd):
        result = invoke(subcmd, "--help")
        assert result.exit_code == 0
        assert "Usage: " in result.stdout
        assert flatten([subcmd])[0] in result.stdout
        assert not result.stderr

    @pytest.mark.parametrize("opt_stats", ["--stats", "--no-stats", None])
    @pytest.mark.parametrize("opt_timer", ["--time", "--no-time", None])
    def test_options(self, invoke, subcmd, opt_stats, opt_timer):
        """ Test the result on all combinations of optional options. """
        result = invoke(opt_stats, opt_timer, subcmd)
        assert result.exit_code == 0

    @staticmethod
    def check_manager_selection(result, selected=MANAGER_IDS):
        """Check inclusion and exclusion of a set of managers.

        Check all manager are there by default.

        .. todo:

            Parametrize/fixturize signals to pin point output depending on
            subcommand.
        """
        assert isinstance(selected, (frozenset, set))

        found_managers = set()
        skipped_managers = set()

        for mid in MANAGER_IDS:

            # List of signals indicating a package manager has been retained by
            # the CLI. Roughly sorted from most specific to more forgiving.
            signals = [
                # Common "not found" warning message.
                "warning: Skip unavailable {} manager.".format(mid) in result.stderr,
                # Common "not implemented" optional command warning message.
                bool(
                    re.search(
                        r"warning: (Sync|Cleanup) not implemented for {}.".format(mid),
                        result.stderr,
                    )
                ),
                # Stats line at the end of output.
                "{}: ".format(mid) in result.stdout.splitlines()[-1]
                if result.stdout
                else "",
                # Match output of managers command.
                bool(
                    re.search(
                        r"\s+│\s+{}\s+│\s+(✓|✘).+│\s+(✓|✘)".format(mid),
                        strip_ansi(result.stdout),
                    )
                ),
                # Sync command.
                "Sync {} package info...".format(mid) in result.stderr,
                # Upgrade command.
                "Updating all outdated packages from {}...".format(mid)
                in result.stderr,
                # Cleanup command.
                "Cleanup {}...".format(mid) in result.stderr,
                # Log message for backup command.
                "Dumping packages from {}...".format(mid) in result.stderr,
                # Restoring message.
                "Restore {} packages...".format(mid) in result.stderr,
                # Warning message for restore command.
                "warning: No [{}] section found.".format(mid) in result.stderr,
            ]

            if True in signals:
                found_managers.add(mid)
            else:
                skipped_managers.add(mid)

        # Compare managers reported by the CLI and those expected.
        assert found_managers == selected
        assert skipped_managers == MANAGER_IDS - selected

    @pytest.mark.parametrize("selector", ["--manager", "--exclude"])
    def test_invalid_manager_selector(self, invoke, subcmd, selector):
        result = invoke(selector, "unknown", subcmd)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for " in result.stderr
        assert selector in result.stderr

    def test_default_all_managers(self, invoke, subcmd):
        """ Test all available managers are selected by default. """
        result = invoke(subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result)

    @pytest.mark.parametrize(
        "args,expected",
        [
            pytest.param(("--manager", "apm"), {"apm"}, id="single_selector"),
            pytest.param(("--manager", "apm") * 2, {"apm"}, id="duplicate_selectors"),
            pytest.param(
                ("--manager", "apm", "--manager", "gem"),
                {"apm", "gem"},
                id="multiple_selectors",
            ),
            pytest.param(
                ("--exclude", "apm"), MANAGER_IDS - {"apm"}, id="single_exclusion"
            ),
            pytest.param(
                ("--exclude", "apm") * 2,
                MANAGER_IDS - {"apm"},
                id="duplicate_exclusions",
            ),
            pytest.param(
                ("--exclude", "apm", "--exclude", "gem"),
                MANAGER_IDS - {"apm", "gem"},
                id="multiple_exclusions",
            ),
            pytest.param(
                ("--manager", "apm", "--exclude", "gem"), {"apm"}, id="priority_ordered"
            ),
            pytest.param(
                ("--exclude", "gem", "--manager", "apm"),
                {"apm"},
                id="priority_reversed",
            ),
            pytest.param(
                ("--manager", "apm", "--exclude", "apm"),
                set(),
                id="exclusion_override_ordered",
            ),
            pytest.param(
                ("--exclude", "apm", "--manager", "apm"),
                set(),
                id="exclusion_override_reversed",
            ),
        ],
    )
    def test_manager_selection(self, invoke, subcmd, args, expected):
        result = invoke(*args, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, expected)


class CLITableTests:

    """Test subcommands whose output is a configurable table.

    A table output is also allowed to be rendered as JSON.
    """

    # List of all supported rendering modes IDs, and their expected output.
    expected_renderings = {
        "ascii": ("---+---", None),
        "csv": (",", None),
        "csv-tab": ("\t", None),
        "double": ("═══╬═══", None),
        "fancy_grid": ("═══╪═══", None),
        "github": ("---|---", None),
        "grid": ("===+===", "ascii"),
        "html": ("<table>", None),
        "jira": (" || ", None),
        "json": ('": {', None),
        "latex": ("\\hline", None),
        "latex_booktabs": ("\\toprule", None),
        "mediawiki": ('{| class="wikitable" ', "jira"),
        "moinmoin": (" ''' || ''' ", "jira"),
        "orgtbl": ("---+---", None),
        "pipe": ("---|:---", None),
        "plain": ("  ", None),
        "psql": ("---+---", None),
        "rst": ("===  ===", None),
        "simple": ("---  ---", None),
        "textile": (" |_. ", None),
        "tsv": ("\t", None),
        "vertical": ("***[ 1. row ]***", None),
    }

    def test_recognized_modes(self):
        """Check all rendering modes proposed by the table module are
        accounted for."""
        assert RENDERING_MODES == set(self.expected_renderings.keys())

    def test_default_table_rendering(self, invoke, subcmd):
        """ Check default rendering is fancy_grid. """
        result = invoke(subcmd)
        assert result.exit_code == 0

        expected = self.expected_renderings["fancy_grid"][0]

        # If no package found, check that no table gets rendered. Else, check
        # the selected mode is indeed rendered in <stdout>, so the CLI result
        # can be grep-ed.
        if result.stdout.startswith("0 package total ("):
            assert expected not in result.stdout
        else:
            assert expected in result.stdout

        assert expected not in result.stderr

    @pytest.mark.parametrize(
        "mode,expected,conflict",
        [(k, v[0], v[1]) for k, v in expected_renderings.items()],
    )
    def test_all_table_rendering(self, invoke, subcmd, mode, expected, conflict):
        """Check that from all rendering modes, only the selected one appears
        in <stdout> and only there. Any other mode are not expected neither in
        <stdout> or <stderr>.
        """
        result = invoke("--output-format", mode, subcmd)
        assert result.exit_code == 0

        # If no package found, check that no table gets rendered. Else, check
        # the selected mode is indeed rendered in <stdout>, so the CLI result
        # can be grep-ed.
        if result.stdout.startswith("0 package total ("):
            # CSV mode will match on comma.
            if mode != "csv":
                assert expected not in result.stdout
        else:
            assert expected in result.stdout

        # Collect all possible unique traces from all possible rendering modes.
        blacklist = {
            v[0]
            for v in self.expected_renderings.values()
            # Exclude obvious character sequences shorter than 3 characters to
            # eliminate false negative.
            if len(v[0]) > 2
        }
        # Remove overlapping edge-cases.
        if conflict:
            blacklist.remove(self.expected_renderings[conflict][0])

        for unexpected in blacklist:
            if unexpected != expected:
                # The unexpected trace is not the selected one, it should not
                # appears at all in stdout.
                assert unexpected not in result.stdout
            # Any expected output from all rendering modes must not appears in
            # <stderr>, including the selected one.
            assert unexpected not in result.stderr

    def test_json_debug_output(self, invoke, subcmd):
        """Output is expected to be parseable if read from <stdout> even in
        debug level as these messages are redirected to <stderr>.

        Also checks that JSON output format is not supported by all commands.
        """
        result = invoke("--output-format", "json", "--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "debug:" in result.stderr
        json.loads(result.stdout)
        json.loads(result.output)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)
