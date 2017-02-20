# -*- coding: utf-8 -*-
#
# Copyright (c) 2016-2017 Kevin Deldycke <kevin@deldycke.com>
#                         and contributors.
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

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import json

from .. import __version__
from ..platform import PY3, PY_VERSION
from .case import CLITestCase, skip_destructive, unless_macos

if PY3:
    basestring = (str, bytes)


class TestCLI(CLITestCase):

    def test_bare_call(self):
        result = self.invoke()
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_main_help(self):
        result = self.invoke('--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_version(self):
        result = self.invoke('--version')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)


class TestCLIManagers(CLITestCase):

    def test_main_help(self):
        result = self.invoke('managers', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('managers')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("═════", result.output)

    def test_simple_table_rendering(self):
        result = self.invoke('--output-format', 'simple', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("-----", result.output)

    def test_plain_table_rendering(self):
        result = self.invoke('--output-format', 'plain', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("═════", result.output)
        self.assertNotIn("-----", result.output)

    def test_json_output(self):
        result = self.invoke('--output-format', 'json', 'managers')
        self.assertEqual(result.exit_code, 0)
        json.loads(result.output)

    def test_json_debug_output(self):
        result = self.invoke(
            '--output-format', 'json', '--verbosity', 'DEBUG', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)
        if PY_VERSION >= (3, 5):
            with self.assertRaises(json.decoder.JSONDecodeError):
                json.loads(result.output)
        else:
            with self.assertRaises(ValueError) as expt:
                json.loads(result.output)
            message = expt.exception.args[0]
            if PY_VERSION >= (3, 4):
                self.assertIn('Expecting value: line ', message)
            else:
                self.assertEqual(message, 'No JSON object could be decoded')

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'managers')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(" npm ", result.output)
        self.assertNotIn(" apm ", result.output)
        self.assertNotIn(" brew ", result.output)
        self.assertNotIn(" pip2 ", result.output)
        self.assertNotIn(" pip3 ", result.output)
        self.assertNotIn(" gem ", result.output)


class TestCLISync(CLITestCase):

    def test_main_help(self):
        result = self.invoke('sync', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'sync')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'sync')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('sync')
        self.assertEqual(result.exit_code, 0)

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'sync')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("npm", result.output)
        self.assertNotIn("apm", result.output)
        self.assertNotIn("brew", result.output)
        self.assertNotIn("pip2", result.output)
        self.assertNotIn("pip3", result.output)
        self.assertNotIn("gem", result.output)


class TestCLIList(CLITestCase):

    def test_main_help(self):
        result = self.invoke('list', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'list')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'list')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('list')
        self.assertEqual(result.exit_code, 0)

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'list')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(" npm ", result.output)
        self.assertNotIn(" apm ", result.output)
        self.assertNotIn(" brew ", result.output)
        self.assertNotIn(" pip2 ", result.output)
        self.assertNotIn(" pip3 ", result.output)
        self.assertNotIn(" gem ", result.output)


class TestCLISearch(CLITestCase):

    def test_main_help(self):
        result = self.invoke('search', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'search', 'abc')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'search', 'abc')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('search', 'abc')
        self.assertEqual(result.exit_code, 0)

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'search', 'abc')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(" npm ", result.output)
        self.assertNotIn(" apm ", result.output)
        self.assertNotIn(" brew ", result.output)
        self.assertNotIn(" pip2 ", result.output)
        self.assertNotIn(" pip3 ", result.output)
        self.assertNotIn(" gem ", result.output)

    @unless_macos()
    def test_unicode_search(self):
        """ See #16. """
        result = self.invoke('search', 'ubersicht')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ubersicht", result.output)
        # XXX search command is not fetching details package infos like names
        # for now.
        # self.assertIn("Übersicht", result.output)

        result = self.invoke('search', 'Übersicht')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ubersicht", result.output)
        # self.assertIn("Übersicht", result.output)


class TestCLIOutdated(CLITestCase):

    def test_main_help(self):
        result = self.invoke('outdated', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("═════", result.output)

    def test_simple_table_rendering(self):
        result = self.invoke('--output-format', 'simple', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("-----", result.output)

    def test_plain_table_rendering(self):
        result = self.invoke('--output-format', 'plain', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("═════", result.output)
        self.assertNotIn("-----", result.output)

    def test_json_output(self):
        result = self.invoke('--output-format', 'json', 'outdated')
        self.assertEqual(result.exit_code, 0)
        json.loads(result.output)

    def test_json_debug_output(self):
        result = self.invoke(
            '--output-format', 'json', '--verbosity', 'DEBUG', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)
        if PY_VERSION >= (3, 5):
            with self.assertRaises(json.decoder.JSONDecodeError):
                json.loads(result.output)
        else:
            with self.assertRaises(ValueError) as expt:
                json.loads(result.output)
            message = expt.exception.args[0]
            if PY_VERSION >= (3, 4):
                self.assertIn('Expecting value: line ', message)
            else:
                self.assertEqual(message, 'No JSON object could be decoded')

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(" npm ", result.output)
        self.assertNotIn(" apm ", result.output)
        self.assertNotIn(" brew ", result.output)
        self.assertNotIn(" pip2 ", result.output)
        self.assertNotIn(" pip3 ", result.output)
        self.assertNotIn(" gem ", result.output)

    def test_cli_format_plain(self):
        result = self.invoke(
            '--output-format', 'json', 'outdated', '--cli-format', 'plain')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                self.assertIsInstance(infos['upgrade_cli'], basestring)

    def test_cli_format_fragments(self):
        result = self.invoke(
            '--output-format', 'json', 'outdated', '--cli-format', 'fragments')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                self.assertIsInstance(infos['upgrade_cli'], list)

    def test_cli_format_bitbar(self):
        result = self.invoke(
            '--output-format', 'json', 'outdated', '--cli-format', 'bitbar')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                self.assertIsInstance(infos['upgrade_cli'], basestring)
                self.assertIn('param1=', infos['upgrade_cli'])

    @skip_destructive()
    def test_unicode_name(self):
        """ See #16. """
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.0.44.
        formula_url = (
            "https://raw.githubusercontent.com/caskroom/homebrew-cask"
            "/51add049f53225ac2c98f59bbeee5e19c29e6557/Casks/ubersicht.rb")
        code, output, error = self.run_cmd(
            'brew', 'cask', 'install', formula_url)
        self.assertEqual(code, 0)
        self.assertIn('Uebersicht-1.0.44.app', output)
        self.assertFalse(error)

        # Look for reported available upgrade.
        result = self.invoke('--manager', 'cask', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ubersicht", result.output)
        self.assertIn("Übersicht", result.output)

    @skip_destructive()
    def test_multiple_names(self):
        """ See #26. """
        # Install an old version of a package with multiple names.
        # Old Cask formula for xld 2016.09.20.
        formula_url = (
            "https://raw.githubusercontent.com/caskroom/homebrew-cask"
            "/9e6ca52ab7846c82471df586a930fb60231d63ee/Casks/xld.rb")
        code, output, error = self.run_cmd(
            'brew', 'cask', 'install', formula_url)
        self.assertEqual(code, 0)
        self.assertIn('xld-20160920.dmg', output)
        self.assertFalse(error)

        # Look for reported available upgrade.
        result = self.invoke('--manager', 'cask', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("xld", result.output)
        self.assertIn("X Lossless Decoder", result.output)


class TestCLIUpgrade(CLITestCase):

    def test_main_help(self):
        result = self.invoke('upgrade', '--help')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.invoke('--verbosity', 'DEBUG', 'upgrade', '--dry-run')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.invoke('--verbosity', 'INFO', 'upgrade', '--dry-run')
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.invoke('upgrade', '--dry-run')
        self.assertEqual(result.exit_code, 0)

    def test_sub_manager_scope(self):
        result = self.invoke('--manager', 'npm', 'upgrade', '--dry-run')
        self.assertEqual(result.exit_code, 0)
        self.assertIn(" npm", result.output)
        self.assertNotIn(" apm ", result.output)
        self.assertNotIn(" brew ", result.output)
        self.assertNotIn(" pip2 ", result.output)
        self.assertNotIn(" pip3 ", result.output)
        self.assertNotIn(" gem ", result.output)

    @skip_destructive()
    def test_full_upgrade(self):
        result = self.invoke('upgrade')
        self.assertEqual(result.exit_code, 0)
