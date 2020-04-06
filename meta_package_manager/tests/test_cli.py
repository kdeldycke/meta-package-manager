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

import re
import unittest

import pytest
import simplejson as json
from boltons.tbutils import ExceptionInfo
from click.testing import CliRunner

from .. import __version__
from ..bitbar import run as bitbar_run
from ..cli import cli
from .case import MANAGER_IDS, print_cli_output


@pytest.fixture(scope="function")
def runner(request):
    return CliRunner()


@pytest.fixture(scope="function")
def invoke(runner, *args):
    """ Executes Click's CLI, print output and return results. """

    def run_run(*args):

        result = runner.invoke(cli, args)

        print_cli_output(['mpm'] + list(args), result.output)

        # Print some more debug info.
        print(result)
        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result

    return run_run


class CLITestCase(unittest.TestCase):

    """ Utilities to automate tests and checks for Click-based CLIs. """

    def __init__(self, *args, **kwargs):
        """ Force running all unittests within an isolated filesystem.

        Intercepts `__init__()` to have an oportunity to decorate manually the
        whole `run()` method itself, so each test method and calls to `setUp()`
        are wrap by the isolated filesystem decorator. See: https://github.com
        /python/cpython/blob/v3.6.0/Lib/unittest/case.py#L648-L649
        """
        super(CLITestCase, self).__init__(*args, **kwargs)

        self.runner = CliRunner()

        run_method = self.run
        decorated_run = self.runner.isolated_filesystem()(run_method)
        self.run = decorated_run

    def invoke(self, *args):
        """ Executes Click's CLI, print output and return results. """
        result = self.runner.invoke(cli, args)

        print_cli_output(['mpm'] + list(args), result.output)

        # Print some more debug info.
        print(result)
        if result.exception:
            print(ExceptionInfo.from_exc_info(*result.exc_info).get_formatted())

        return result


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


@pytest.fixture(scope="function", params=commands)
def commands_arg(request):
    return request.param


class TestCLISubcommand(CLITestCase):

    """ Base class to define tests common to each subcommands. """

    subcommand_args = []

    def setUp(self):
        if not self.subcommand_args:
            raise unittest.SkipTest('Skip generic test class.')

    def test_main_help(self):
        result = self.invoke(*(self.subcommand_args + ['--help']))
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke(*self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        return result

    def check_manager_selection(self, output, included):
        """ Check inclusion and exclusion of a set of managers. """
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
                # Log message for backup command.
                "Dumping packages from {}...".format(mid) in output,
                # Warning message for restore command.
                "warning: Skip {} packages: no section found in TOML file."
                "".format(mid) in output]

            if True in signals:
                found_managers.add(mid)
            else:
                skipped_managers.add(mid)

        # Compare managers reported by the CLI and those expected.
        included = set(included)
        self.assertSetEqual(found_managers, included)
        self.assertSetEqual(skipped_managers, MANAGER_IDS - included)

    def test_manager_selection(self):
        result = self.invoke('--manager', 'apm', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(result.output, ['apm'])

    def test_manager_duplicate_selection(self):
        result = self.invoke(
            '--manager', 'apm', '--manager', 'apm', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(result.output, ['apm'])

    def test_manager_multiple_selection(self):
        result = self.invoke(
            '--manager', 'apm', '--manager', 'gem', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(result.output, ['apm', 'gem'])

    def test_manager_exclusion(self):
        result = self.invoke('--exclude', 'apm', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(
            result.output, MANAGER_IDS - set(['apm']))

    def test_manager_duplicate_exclusion(self):
        result = self.invoke(
            '--exclude', 'apm', '--exclude', 'apm', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(
            result.output, MANAGER_IDS - set(['apm']))

    def test_manager_multiple_exclusion(self):
        result = self.invoke(
            '--exclude', 'apm', '--exclude', 'gem', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(
            result.output, MANAGER_IDS - set(['apm', 'gem']))

    def test_manager_selection_priority(self):
        result = self.invoke(
            '--manager', 'apm', '--exclude', 'gem', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(result.output, ['apm'])

    def test_manager_selection_exclusion_override(self):
        result = self.invoke(
            '--manager', 'apm', '--exclude', 'apm', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.check_manager_selection(result.output, [])


class TestCLITableRendering(TestCLISubcommand):

    """ Test subcommands whose output is a configurable table.

    A table output is also allowed to be rendered as JSON.
    """

    def test_simple_call(self):
        result = super(TestCLITableRendering, self).test_simple_call()
        self.assertIn("═════", result.output)

    def test_simple_table_rendering(self):
        result = self.invoke(
            '--output-format', 'simple', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("-----", result.output)

    def test_plain_table_rendering(self):
        result = self.invoke('--output-format', 'plain', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("═════", result.output)
        self.assertNotIn("-----", result.output)

    def test_json_output(self):
        result = self.invoke('--output-format', 'json', *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        return json.loads(result.output)

    def test_json_debug_output(self):
        """ Debug output is expected to be unparseable.

        Because of interleaved debug messages and JSON output.
        """
        result = self.invoke(
            '--output-format', 'json', '--verbosity', 'DEBUG',
            *self.subcommand_args)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)
        with self.assertRaises(json.decoder.JSONDecodeError):
            json.loads(result.output)
