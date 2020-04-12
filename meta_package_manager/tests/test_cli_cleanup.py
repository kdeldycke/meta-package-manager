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

import pytest

from .conftest import MANAGER_IDS
from .test_cli import \
    test_manager_selection  # Run manager selection tests for this subcommand.
from .test_cli import check_manager_selection


@pytest.fixture
def subcommand():
    return 'cleanup'


def test_default_all_manager(invoke, subcommand):
    result = invoke(subcommand)
    assert result.exit_code == 0
    check_manager_selection(result.output)


@pytest.mark.parametrize('mid', MANAGER_IDS)
def test_single_manager(invoke, subcommand, mid):
    result = invoke('--manager', mid, subcommand)
    assert result.exit_code == 0
    check_manager_selection(result.output, {mid})
