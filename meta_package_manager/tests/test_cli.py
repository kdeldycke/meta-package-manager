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

import pytest
import simplejson as json
from boltons.iterutils import flatten

from .. import __version__, logger
from .conftest import MANAGER_IDS, run_cmd

""" Common tests for all CLI basic features and templates for subcommands. """


class TestBaseCLI:

    """ This collection test based CLI behavior shared by all subcommands.

    Regroups tests not involving subcommands.

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
        result = invoke('--help')
        assert result.exit_code == 0
        assert "Usage: " in result.stdout
        assert not result.stderr

    def test_version(self, invoke):
        result = invoke('--version')
        assert result.exit_code == 0
        assert __version__ in result.stdout
        assert not result.stderr

    def test_unknown_option(self, invoke):
        result = invoke('--blah')
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: no such option: --blah" in result.stderr

    def test_unknown_command(self, invoke):
        result = invoke('blah')
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: No such command 'blah'." in result.stderr

    def test_required_command(self, invoke):
        result = invoke('--verbosity', 'DEBUG')
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing command." in result.stderr

    def test_unrecognized_verbosity(self, invoke):
        result = invoke('--verbosity', 'random', 'managers')
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for '--verbosity' / '-v'" in result.stderr

    @pytest.mark.parametrize(
        'level', ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'])
    def test_verbosity(self, invoke, level):
        result = invoke('--verbosity', level, 'managers')
        assert result.exit_code == 0
        assert logger.level == getattr(logging, level)
        assert "══════" in result.stdout
        if level == 'DEBUG':
            assert "debug: " in result.stderr
        else:
            assert "debug: " not in result.stderr

    def test_console_output(self, invoke):
        """ Check the table is rendering in console's standard output
        (<stdout>) instead of error output (<stderr>), so the result can be
        grep-ed. """
        result = invoke('managers')
        assert result.exit_code == 0
        assert "═════" in result.stdout
        assert "═════" not in result.stderr


class CLISubCommandTests:

    """ All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a
    template, inherited sub-command specific files.
    """

    @staticmethod
    def check_manager_selection(result, included=MANAGER_IDS):
        """ Check inclusion and exclusion of a set of managers.

        Check all manager are there by default.

        .. todo:

            Parametrize/fixturize signals to pin point output depending on
            subcommand.
        """
        assert isinstance(included, (frozenset, set))

        found_managers = set()
        skipped_managers = set()

        for mid in MANAGER_IDS:

            # List of signals indicating a package manager has been retained by
            # the CLI. Roughly sorted from most specific to more forgiving.
            signals = [
                # Common "not found" warning message.
                "warning: Skip unavailable {} manager.".format(
                    mid) in result.stderr,
                # Stats line at the end of output.
                "{}: ".format(mid) in result.stdout.splitlines(
                    )[-1] if result.stdout else '',
                # Match output of managers command.
                bool(re.search(
                    r"\s+│\s+{}\s+│\s+(✓|✘).+│\s+(✓|✘)\s+".format(mid),
                    result.stdout)),
                # Sync command.
                "Sync {} package info...".format(mid) in result.stderr,
                # Upgrade command.
                "Updating all outdated packages from {}...".format(
                    mid) in result.stderr,
                # Cleanup command.
                "Cleanup {}...".format(mid) in result.stderr,
                # Log message for backup command.
                "Dumping packages from {}...".format(mid) in result.stderr,
                # Restoring message.
                "Restore {} packages...".format(mid) in result.stderr,
                # Warning message for restore command.
                "warning: No [{}] section found.".format(mid) in result.stderr]

            if True in signals:
                found_managers.add(mid)
            else:
                skipped_managers.add(mid)

        # Compare managers reported by the CLI and those expected.
        assert found_managers == included
        assert skipped_managers == MANAGER_IDS - included

    def test_help(self, invoke, subcmd):
        result = invoke(subcmd, '--help')
        assert result.exit_code == 0
        assert "Usage: " in result.stdout
        assert flatten([subcmd])[0] in result.stdout
        assert not result.stderr

    @pytest.mark.parametrize('selector', ['--manager', '--exclude'])
    def test_invalid_manager_selector(self, invoke, subcmd, selector):
        result = invoke(selector, 'unknown', subcmd)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Invalid value for " in result.stderr
        assert selector in result.stderr

    @pytest.mark.parametrize('args,expected', [
        pytest.param(
            ('--manager', 'apm'), {'apm'},
            id="single_selector"),
        pytest.param(
            ('--manager', 'apm') * 2, {'apm'},
            id="duplicate_selectors"),
        pytest.param(
            ('--manager', 'apm', '--manager', 'gem'), {'apm', 'gem'},
            id="multiple_selectors"),
        pytest.param(
            ('--exclude', 'apm'), MANAGER_IDS - {'apm'},
            id="single_exclusion"),
        pytest.param(
            ('--exclude', 'apm') * 2, MANAGER_IDS - {'apm'},
            id="duplicate_exclusions"),
        pytest.param(
            ('--exclude', 'apm', '--exclude', 'gem'),
            MANAGER_IDS - {'apm', 'gem'},
            id="multiple_exclusions"),
        pytest.param(
            ('--manager', 'apm', '--exclude', 'gem'), {'apm'},
            id="priority_ordered"),
        pytest.param(
            ('--exclude', 'gem', '--manager', 'apm'), {'apm'},
            id="priority_reversed"),
        pytest.param(
            ('--manager', 'apm', '--exclude', 'apm'), set(),
            id="exclusion_override_ordered"),
        pytest.param(
            ('--exclude', 'apm', '--manager', 'apm'), set(),
            id="exclusion_override_reversed"),
    ])
    def test_manager_selection(self, invoke, subcmd, args, expected):
        result = invoke(*args, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, expected)


class CLITableTests:

    """ Test subcommands whose output is a configurable table.

    A table output is also allowed to be rendered as JSON.
    """

    def test_default_table_rendering(self, invoke, subcmd):
        result = invoke(subcmd)
        assert result.exit_code == 0
        assert "═════" in result.stdout
        assert "═════" not in result.stderr

    @pytest.mark.parametrize('mode', ['simple', 'plain'])
    def test_table_rendering(self, invoke, subcmd, mode):
        result = invoke('--output-format', mode, subcmd)
        assert result.exit_code == 0
        assert "═════" not in result.stdout
        assert "═════" not in result.stderr

    def test_json_debug_output(self, invoke, subcmd):
        """ Output is expected to be parseable if read from <stdout> even in
        debug level as these messages are redirected to <stderr>.

        Also checks that JSON output format is not supported by all commands.
        """
        result = invoke(
            '--output-format', 'json', '--verbosity', 'DEBUG', subcmd)
        assert result.exit_code == 0
        assert "debug:" in result.stderr
        json.loads(result.stdout)
        json.loads(result.output)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)
