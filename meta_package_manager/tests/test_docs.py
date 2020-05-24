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

import pytest
from boltons.iterutils import flatten

from ..platform import OS_DEFINITIONS
from .conftest import MANAGER_IDS

""" Test documentation. """


def test_changelog():
    changelog_path = Path(
        __file__).parent.parent.parent.joinpath('CHANGES.rst').resolve()
    with changelog_path.open() as doc:
        changelog = doc.read()

    assert changelog.startswith("Changelog\n=========\n")

    entry_pattern = re.compile(r"^\* \[(?P<category>[a-z,]+)\] (?P<entry>.+)")
    for line in changelog.splitlines():
        if line.startswith('*'):
            match = entry_pattern.match(line)
            assert match
            entry = match.groupdict()
            assert entry['category']
            assert set(entry['category'].split(',')).issubset(flatten([
                MANAGER_IDS, OS_DEFINITIONS.keys(), 'pip', 'mpm', 'bitbar']))
