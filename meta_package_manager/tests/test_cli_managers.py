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

from .. import __version__
from .case import MANAGER_IDS
from .test_cli import TestCLITableRendering


class TestCLIManagers(TestCLITableRendering):

    subcommand_args = ['managers']

    def test_json_output(self):
        result = super(TestCLIManagers, self).test_json_output()

        self.assertSetEqual(set(result), MANAGER_IDS)

        for manager_id, info in result.items():
            self.assertIsInstance(manager_id, str)
            self.assertIsInstance(info, dict)

            self.assertSetEqual(set(info), set([
                'available', 'cli_path', 'errors', 'executable', 'fresh', 'id',
                'name', 'supported', 'version']))

            self.assertIsInstance(info['available'], bool)
            if info['cli_path'] is not None:
                self.assertIsInstance(info['cli_path'], str)
            self.assertIsInstance(info['errors'], list)
            self.assertIsInstance(info['executable'], bool)
            self.assertIsInstance(info['fresh'], bool)
            self.assertIsInstance(info['id'], str)
            self.assertIsInstance(info['name'], str)
            self.assertIsInstance(info['supported'], bool)
            if info['version'] is not None:
                self.assertIsInstance(info['version'], str)

            self.assertEqual(info['id'], manager_id)
