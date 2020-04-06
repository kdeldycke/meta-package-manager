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

import textwrap

from .test_cli import TestCLISubcommand


class TestCLIRestore(TestCLISubcommand):

    subcommand_args = ['restore', 'dummy.toml']

    def setUp(self, *args, **kwargs):
        """ Create a custom TOML file to feed the CLI with.

        Our dummy file should result in no action as whole sections of
        unrecognized managers are simply ignored.
        """
        toml_content = textwrap.dedent("""\
            [dummy_manager]
            fancy_package = "0.0.1"
            """)

        with open('dummy.toml', 'w') as doc:
            doc.write(toml_content)

        super(TestCLIRestore, self).setUp(*args, **kwargs)

    def test_ignore_dummy_manager(self):
        result = self.invoke('restore', 'dummy.toml')
        self.assertEqual(result.exit_code, 0)
        self.assertIn('dummy.toml', result.output)
        self.assertNotIn('dummy_manager', result.output)

    # @skip_destructive()
    def test_restore_single_manager(self):
        toml_content = textwrap.dedent("""\
            [pip3]
            fancy_package = "0.0.1"

            [npm]
            dummy_package = "2.2.2"
            """)

        with open('packages.toml', 'w') as doc:
            doc.write(toml_content)

        result = self.invoke('--manager', 'npm', 'restore', 'packages.toml')
        self.assertEqual(result.exit_code, 0)
        self.assertIn('packages.toml', result.output)
        self.assertNotIn('Restore pip3', result.output)
        self.assertIn('Restore npm', result.output)

    # @skip_destructive()
    def test_restore_excluded_manager(self):
        toml_content = textwrap.dedent("""\
            [pip3]
            fancy_package = "0.0.1"

            [npm]
            dummy_package = "2.2.2"
            """)

        with open('packages.toml', 'w') as doc:
            doc.write(toml_content)

        result = self.invoke('--exclude', 'npm', 'restore', 'packages.toml')
        self.assertEqual(result.exit_code, 0)
        self.assertIn('packages.toml', result.output)
        self.assertIn('Restore pip3', result.output)
        self.assertNotIn('Restore npm', result.output)
