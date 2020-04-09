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

from .conftest import MANAGER_IDS, unless_macos
from .test_cli import TestCLITableRendering


class TestCLISearch(TestCLITableRendering):

    subcommand_args = ['search', 'abc']

    def test_json_output(self):
        result = super(TestCLISearch, self).test_json_output()

        self.assertTrue(set(result).issubset(MANAGER_IDS))

        for manager_id, info in result.items():
            self.assertIsInstance(manager_id, str)
            self.assertIsInstance(info, dict)

            self.assertSetEqual(set(info), set([
                'errors', 'id', 'name', 'packages']))

            self.assertIsInstance(info['errors'], list)
            self.assertIsInstance(info['id'], str)
            self.assertIsInstance(info['name'], str)
            self.assertIsInstance(info['packages'], list)

            self.assertEqual(info['id'], manager_id)

            for pkg in info['packages']:
                self.assertIsInstance(pkg, dict)

                self.assertSetEqual(set(pkg), set([
                    'id', 'latest_version', 'name']))

                self.assertIsInstance(pkg['id'], str)
                if pkg['latest_version'] is not None:
                    self.assertIsInstance(pkg['latest_version'], str)
                self.assertIsInstance(pkg['name'], str)

    @unless_macos()
    def test_unicode_search(self):
        """ See #16. """
        result = self.invoke('--manager', 'cask', 'search', 'ubersicht')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ubersicht", result.output)
        # XXX search command is not fetching details package infos like names
        # for now.
        # self.assertIn("Übersicht", result.output)

        result = self.invoke('--manager', 'cask', 'search', 'Übersicht')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("ubersicht", result.output)
        # self.assertIn("Übersicht", result.output)

    def test_exact_search_tokenizer(self):
        result = self.invoke('--manager', 'pip3', 'search', '--exact', 'sed')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("1 package found", result.output)
        self.assertIn(" sed ", result.output)

        for query in ['SED', 'SeD', 'sEd*', '*sED*', '_seD-@', '', '_']:
            result = self.invoke(
                '--manager', 'pip3', 'search', '--exact', query)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("0 package found", result.output)
            self.assertNotIn("sed", result.output)

    def test_fuzzy_search_tokenizer(self):
        for query in ['', '_', '_seD-@']:
            result = self.invoke('--manager', 'pip3', 'search', query)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("0 package found", result.output)
            self.assertNotIn("sed", result.output)

        for query in ['sed', 'SED', 'SeD', 'sEd*', '*sED*']:
            result = self.invoke('--manager', 'pip3', 'search', query)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("2 packages found", result.output)
            self.assertIn(" sed ", result.output)
            self.assertIn(" SED-cli ", result.output)

    def test_extended_search_tokenizer(self):
        for query in ['', '_', '_seD-@']:
            result = self.invoke(
                '--manager', 'pip3', 'search', '--extended', query)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("0 package found", result.output)
            self.assertNotIn("sed", result.output)

        for query in ['sed', 'SED', 'SeD', 'sEd*', '*sED*']:
            result = self.invoke(
                '--manager', 'pip3', 'search', '--extended', query)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("22 packages found", result.output)
