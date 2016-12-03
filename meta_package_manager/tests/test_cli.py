# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Kevin Deldycke <kevin@deldycke.com>
#                    and contributors.
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

import unittest

from click.testing import CliRunner

from meta_package_manager.cli import cli


class CLITestCase(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()


class TestCLI(CLITestCase):

    def test_main_help(self):
        result = self.runner.invoke(cli, ['--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.runner.invoke(cli, ['--verbosity', 'DEBUG'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.runner.invoke(cli, ['--verbosity', 'INFO'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)


class TestCLIManagers(CLITestCase):

    def test_main_help(self):
        result = self.runner.invoke(cli, ['managers', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.runner.invoke(cli, ['--verbosity', 'DEBUG', 'managers'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.runner.invoke(cli, ['--verbosity', 'INFO', 'managers'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.runner.invoke(cli, ['managers'])
        self.assertEqual(result.exit_code, 0)


class TestCLISync(CLITestCase):

    def test_main_help(self):
        result = self.runner.invoke(cli, ['sync', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.runner.invoke(cli, ['--verbosity', 'DEBUG', 'sync'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.runner.invoke(cli, ['--verbosity', 'INFO', 'sync'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.runner.invoke(cli, ['sync'])
        self.assertEqual(result.exit_code, 0)


class TestCLIOutdated(CLITestCase):

    def test_main_help(self):
        result = self.runner.invoke(cli, ['outdated', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.runner.invoke(cli, ['--verbosity', 'DEBUG', 'outdated'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.runner.invoke(cli, ['--verbosity', 'INFO', 'outdated'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.runner.invoke(cli, ['outdated'])
        self.assertEqual(result.exit_code, 0)


class TestCLIUpgrade(CLITestCase):

    def test_main_help(self):
        result = self.runner.invoke(cli, ['upgrade', '--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--help", result.output)

    def test_verbosity(self):
        result = self.runner.invoke(cli, ['--verbosity', 'DEBUG', 'upgrade'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("debug:", result.output)

        result = self.runner.invoke(cli, ['--verbosity', 'INFO', 'upgrade'])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("debug:", result.output)

    def test_simple_call(self):
        result = self.runner.invoke(cli, ['upgrade'])
        self.assertEqual(result.exit_code, 0)
