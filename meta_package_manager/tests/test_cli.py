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
from .conftest import MANAGER_IDS, destructive

""" Common tests for all CLI basic features and subcommands. """


def test_bare_call(invoke):
    result = invoke()
    assert result.exit_code == 0
    assert "--help" in result.output


def test_main_help(invoke):
    result = invoke('--help')
    assert result.exit_code == 0
    assert "--help" in result.output


def test_version(invoke):
    result = invoke('--version')
    assert result.exit_code == 0
    assert __version__ in result.output


def test_unknown_option(invoke):
    result = invoke('--blah')
    assert result.exit_code == 2
    assert "Error: no such option: --blah" in result.output


def test_unknown_command(invoke):
    result = invoke('blah')
    assert result.exit_code == 2
    assert "Error: No such command 'blah'." in result.output


def test_required_command(invoke):
    result = invoke('--verbosity', 'DEBUG')
    assert result.exit_code == 2
    assert "Error: Missing command." in result.output


def test_unrecognized_verbosity(invoke):
    result = invoke('--verbosity', 'random', 'managers')
    assert result.exit_code == 2
    assert "Error: Invalid value for '--verbosity' / '-v'" in result.output


@pytest.mark.parametrize(
    'level', ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'])
def test_verbosity(invoke, level):
    result = invoke('--verbosity', level, 'managers')
    assert result.exit_code == 0
    assert logger.level == getattr(logging, level)
    if level == 'DEBUG':
        assert "debug: " in result.output
    else:
        assert "debug: " not in result.output


class CLISubCommandTests:

    """ All these tests runs on each subcommand.

    This class doesn't starts with `Test` as it is meant to be used as a
    template, inherited sub-command specific files.
    """

    @staticmethod
    def check_manager_selection(output, included=MANAGER_IDS):
        """ Check inclusion and exclusion of a set of managers.

        Check all manager are there by default.

        .. todo:

            Parametrize/fixturize signals to pin point output depending on
            subcommand.
        """
        assert isinstance(output, str)
        assert isinstance(included, (frozenset, set))

        found_managers = set()
        skipped_managers = set()

        for mid in MANAGER_IDS:

            # List of signals indicating a package manager has been retained by
            # the CLI. Roughly sorted from most specific to more forgiving.
            signals = [
                # Common "not found" warning message.
                "warning: Skip unavailable {} manager.".format(mid) in output,
                # Stats line at the end of output.
                "{}: ".format(
                    mid) in output.splitlines()[-1] if output else '',
                # Match output of managers command.
                bool(re.search(
                    r"\s+│\s+{}\s+│\s+(✓|✘).+│\s+(✓|✘)\s+".format(mid),
                    output)),
                # Sync command.
                "Sync {} package info...".format(mid) in output,
                # Upgrade command.
                "Updating all outdated packages from {}..."
                "".format(mid) in output,
                # Cleanup command.
                "Cleanup {}...".format(mid) in output,
                # Log message for backup command.
                "Dumping packages from {}...".format(mid) in output,
                # Restoring message.
                "Restore {} packages...".format(mid) in output,
                # Warning message for restore command.
                "warning: No [{}] section found.".format(mid) in output]

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
        assert flatten([subcmd])[0] in result.output
        assert "--help" in result.output

    @pytest.mark.parametrize('selector', ['--manager', '--exclude'])
    def test_invalid_manager_selector(self, invoke, subcmd, selector):
        result = invoke(selector, 'unknown', subcmd)
        assert result.exit_code == 2
        assert "Error: Invalid value for " in result.output
        assert selector in result.output

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
        self.check_manager_selection(result.output, expected)


class CLITableTests:

    def test_default_table_rendering(self, invoke, subcmd):
        result = invoke(subcmd)
        assert result.exit_code == 0
        assert "═════" in result.output

    @pytest.mark.parametrize('mode', ['simple', 'plain'])
    def test_table_rendering(self, invoke, subcmd, mode):
        result = invoke('--output-format', mode, subcmd)
        assert result.exit_code == 0
        assert "═════" not in result.output

    def test_json_debug_output(self, invoke, subcmd):
        """ Debug output is expected to be unparseable because of interleaved
        debug messages and JSON output.

        Also checks that JSON output format is not supported by all commands.
        """
        result = invoke(
            '--output-format', 'json', '--verbosity', 'DEBUG', subcmd)
        assert result.exit_code == 0
        assert "debug:" in result.output
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.output)
