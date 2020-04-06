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

import simplejson as json

from .case import MANAGER_IDS, run_cmd, skip_destructive
from .test_cli import TestCLITableRendering


class TestCLIOutdated(TestCLITableRendering):

    subcommand_args = ['outdated']

    def test_json_output(self):
        result = super(TestCLIOutdated, self).test_json_output()

        self.assertTrue(set(result).issubset(MANAGER_IDS))

        for manager_id, info in result.items():
            self.assertIsInstance(manager_id, str)
            self.assertIsInstance(info, dict)

            self.assertIsInstance(info['errors'], list)
            self.assertIsInstance(info['id'], str)
            self.assertIsInstance(info['name'], str)
            self.assertIsInstance(info['packages'], list)

            keys = set(['errors', 'id', 'name', 'packages'])
            if 'upgrade_all_cli' in info:
                self.assertIsInstance(info['upgrade_all_cli'], str)
                self.assertGreater(len(info['packages']), 0)
                keys.add('upgrade_all_cli')
            else:
                self.assertEqual(len(info['packages']), 0)

            self.assertSetEqual(set(info), keys)

            self.assertEqual(info['id'], manager_id)

            for pkg in info['packages']:
                self.assertIsInstance(pkg, dict)

                self.assertSetEqual(set(pkg), set([
                    'id', 'installed_version', 'latest_version', 'name',
                    'upgrade_cli']))

                self.assertIsInstance(pkg['id'], str)
                self.assertIsInstance(pkg['installed_version'], str)
                self.assertIsInstance(pkg['latest_version'], str)
                self.assertIsInstance(pkg['name'], str)
                self.assertIsInstance(pkg['upgrade_cli'], str)

    def test_cli_format_plain(self):
        result = self.invoke(
            '--output-format', 'json', 'outdated', '--cli-format', 'plain')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                self.assertIsInstance(infos['upgrade_cli'], str)

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
                self.assertIsInstance(infos['upgrade_cli'], str)
                self.assertIn('param1=', infos['upgrade_cli'])

    @skip_destructive()
    def test_unicode_name(self):
        """ See #16. """
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.0.44.
        formula_url = (
            "https://raw.githubusercontent.com/caskroom/homebrew-cask"
            "/51add049f53225ac2c98f59bbeee5e19c29e6557/Casks/ubersicht.rb")
        code, output, error = run_cmd(
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
        code, output, error = run_cmd(
            'brew', 'cask', 'install', formula_url)
        self.assertEqual(code, 0)
        self.assertIn('xld-20160920.dmg', output)
        self.assertFalse(error)

        # Look for reported available upgrade.
        result = self.invoke('--manager', 'cask', 'outdated')
        self.assertEqual(result.exit_code, 0)
        self.assertIn("xld", result.output)
        self.assertIn("X Lossless Decoder", result.output)
