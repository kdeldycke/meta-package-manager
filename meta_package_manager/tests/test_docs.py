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

from pathlib import Path

import pytest

""" Test documentation. """


def test_real_fs():
    """ Check the test in not caught into the CLI runner fixture which is
    encapsulating all filesystem access into temporary directory structure. """
    assert str(Path(__file__)).startswith(str(Path.cwd()))


def test_temporary_fs(runner):
    """ Check the CLI runner fixture properly encapsulated the filesystem in
    temporary directory. """
    assert not str(Path(__file__)).startswith(str(Path.cwd()))


def test_changelog():

    changelog_path = Path(
        __file__).parent.parent.parent.joinpath('CHANGES.rst').resolve()

    with changelog_path.open() as doc:
        changelog = doc.read()

    assert changelog.startswith("Changelog\n=========\n")
