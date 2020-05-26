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

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import os
import re
import sys
import unittest

from .. import bitbar


"""
Like BitBar, this plugin is supposed to run smoothly with Python 2.7.1 or
newer.
"""


@unittest.skipUnless(sys.platform == 'darwin', 'macOS required')
class TestBibarPlugin(unittest.TestCase):
    """ This is the only test suite that is still using unittest module instead
    of pytest.
    """

    def bitbar_output_checks(self, checklist):
        code, output, error = bitbar.run(bitbar.__file__)
        self.assertEqual(code, 0)
        self.assertIsNone(error)
        for regex in checklist:
            self.assertRegexpMatches(output, re.compile(regex, re.MULTILINE))

    def test_simple_call(self):
        """ Check default rendering is flat: no submenu. """
        self.bitbar_output_checks([
            r"^↑\d+ (⚠️\d+ )?\| dropdown=false$",
            r"^---$",
            r"^\d+ outdated .+ packages? \|  emojize=false$"])

    def test_submenu_rendering(self):
        os.environ['BITBAR_MPM_SUBMENU'] = 'True'
        self.bitbar_output_checks([
            r"^↑\d+ (⚠️\d+ )?\| dropdown=false$",
            r"^.+:\s+\d+ package(s| ) \| font=Menlo size=12 emojize=false$",
            r"^--\S+ \S+ → \S+ \| bash=.+$",
            r"^-----$",
            r"^--Upgrade all \| bash=.+$"])
