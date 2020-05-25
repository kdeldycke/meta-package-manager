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

import re

from .. import bitbar
from .conftest import run_cmd, unless_macos


"""
Like BitBar, this plugin is supposed to run smoothly with Python 2.7.1 or
newer.
"""


@unless_macos
def test_simple_call():
    """ Check default rendering is flat: no submenu. """
    code, output, error = run_cmd(bitbar.__file__)
    assert code == 0
    assert error is None
    for regex in [
            r"^↑\d+ (⚠️\d+ )?\| dropdown=false$",
            r"^---$",
            r"^\d+ outdated .+ packages? \|  emojize=false$"]:
        assert re.search(regex, output, re.MULTILINE)


@unless_macos
def test_submenu_rendering(monkeypatch):
    monkeypatch.setenv("BITBAR_MPM_SUBMENU", "True")
    code, output, error = run_cmd(bitbar.__file__)
    assert code == 0
    assert error is None
    for regex in [
            r"^↑\d+ (⚠️\d+ )?\| dropdown=false$",
            r"^.+:\s+\d+ package(s| ) \| font=Menlo size=12 emojize=false$",
            r"^--\S+ \S+ → \S+ \| bash=.+$",
            r"^-----$",
            r"^--Upgrade all \| bash=.+$"]:
        assert re.search(regex, output, re.MULTILINE)
