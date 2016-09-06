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

from meta_package_manager.managers import pool


class TestDefinition(unittest.TestCase):

    """ Test the definition of all package managers. """

    def test_ascii_id(self):
        """ All package manager IDs should be short ASCII strings. """
        for manager_id in pool():
            self.assertRegexpMatches(manager_id, r'[a-z0-9]+')

    def test_number(self):
        """ Check all supported package managers are accounted for. """
        self.assertEqual(len(pool()), 8)
