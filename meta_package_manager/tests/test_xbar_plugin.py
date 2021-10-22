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

import os
import re
from collections import Counter

from click_extra.run import run_cmd
from click_extra.tests.conftest import unless_macos

from .. import xbar


@unless_macos
class TestXbarPlugin:

    common_checklist = [
        # Menubar line. Required.
        (r"↑\d+ (⚠️\d+ )?\| dropdown=false$", True),
        # Package upgrade line. Optional: there might be no package to
        # upgrade.
        (r"(--)?.+ \S+ → \S+ \| shell=.+$", False),
        # Submenu marker line. Required.
        (r"-{3,5}$", True),
        # Upgrade all line. Required.
        (r"(--)?Upgrade all \| shell=.+$", False),
        # Error line. Optional.
        (
            r"(--)?.+ \| color=red \| font=Menlo \| size=12 \| trim=false \| emojize=false$",
            False,
        ),
    ]

    def xbar_output_checks(self, checklist, env=None):
        if env:
            for var, value in env.items():
                os.environ[var] = value
        code, output, error = run_cmd(xbar.__file__)
        if env:
            for var in env:
                del os.environ[var]
        assert code == 0
        assert error is None

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
                print(repr(output))
                raise Exception(f"xbar output line {line!r} did not match any regexp.")

        # Check all required regexp did match at least once.
        for index, (regex, required) in enumerate(checks):
            if required and not match_counter[index]:
                raise Exception(
                    f"{regex!r} regex did not match any xbar plugin output line."
                )

    def test_simple_call(self):
        """Check default rendering is flat: no submenu."""
        self.xbar_output_checks(
            [
                # Summary package statistics. Required.
                (r"\d+ outdated .+ packages? \| emojize=false$", True),
            ]
        )

    def test_submenu_rendering(self):
        self.xbar_output_checks(
            [
                # Submenu entry line with summary. Required.
                (
                    r".+:\s+\d+ package(s| ) \| font=Menlo \| size=12 \| emojize=false$",
                    True,
                ),
            ],
            env={"VAR_SUBMENU_LAYOUT": "True"},
        )
