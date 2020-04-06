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


from .test_cli import TestCLISubcommand


class TestCLIBackup(TestCLISubcommand):

    # Wait for https://github.com/pallets/click/pull/1497 before removing the
    # mpm-packages.toml argument below.
    subcommand_args = ['backup', 'mpm-packages.toml']

    def test_export_all_packages_to_file(self):
        result = self.invoke('backup', 'mpm-packages.toml')
        self.assertEqual(result.exit_code, 0)
        self.assertIn('mpm-packages.toml', result.output)

    def test_backup_single_manager(self):
        result = self.invoke('--manager', 'npm', 'backup', 'npm-packages.toml')
        self.assertEqual(result.exit_code, 0)
        with open('npm-packages.toml', 'r') as doc:
            # Check only [npm] section appears in TOML file.
            self.assertSetEqual(
                {l for l in doc.read().split() if l.startswith('[')},
                set(['[npm]']))
