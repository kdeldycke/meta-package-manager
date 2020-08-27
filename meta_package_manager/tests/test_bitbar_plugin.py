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

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import re
import sys
import unittest
from collections import Counter

from .. import bitbar


"""
Like BitBar, this plugin is supposed to run smoothly with Python 2.7.1 or
newer.
"""


@unittest.skipUnless(sys.platform == "darwin", "macOS required")
class TestBibarPlugin(unittest.TestCase):
    """This is the only test suite that is still using unittest module instead
    of pytest.
    """

    common_checklist = [
        # Menubar line. Required.
        (r"↑\d+ (⚠️\d+ )?\| dropdown=false$", True),
        # Package upgrade line. Optional: there might be no package to
        # upgrade.
        (r"(--)?\S+ \S+ → \S+ \| bash=.+$", False),
        # Submenu marker line. Required.
        (r"-{3,5}$", True),
        # Upgrade all line. Required.
        (r"(--)?Upgrade all \| bash=.+$", False),
        # Error line. Optional.
        (r"(--)?.+ \| color=red font=Menlo size=12 trim=false emojize=false$", False),
    ]

    def bitbar_output_checks(self, checklist, env=None):
        if env:
            for var, value in env.items():
                os.environ[var] = value
        code, output, error = bitbar.run(bitbar.__file__)
        if env:
            for var in env:
                del os.environ[var]
        self.assertEqual(code, 0)
        self.assertIsNone(error)

        checks = checklist + self.common_checklist

        match_counter = Counter()

        for line in output.splitlines():
            # The line is expected to match at least one regexp.
            matches = False
            for index, (regex, _) in enumerate(checks):
                if re.match(regex, line):
                    matches = True
                    match_counter[index] += 1
                    break
            if not matches:
                self.fail(
                    "BitBar output line {!r} did not match any regexp.".format(line)
                )

        # Check all required regexp did match at least once.
        for index, (regex, required) in enumerate(checks):
            if required and not match_counter[index]:
                self.fail(
                    "{!r} regex did not match any BitBar plugin output line."
                    "".format(regex)
                )

    def test_simple_call(self):
        """ Check default rendering is flat: no submenu. """
        self.bitbar_output_checks(
            [
                # Summary package statistics. Required.
                (r"\d+ outdated .+ packages? \|  emojize=false$", True),
            ]
        )

    def test_submenu_rendering(self):
        self.bitbar_output_checks(
            [
                # Submenu entry line with summary. Required.
                (r".+:\s+\d+ package(s| ) \| font=Menlo size=12 emojize=false$", True),
            ],
            env={"BITBAR_MPM_SUBMENU": "True"},
        )
