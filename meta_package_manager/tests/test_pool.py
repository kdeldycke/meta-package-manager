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

from ..managers import (
    ALL_MANAGER_IDS,
    DEFAULT_MANAGER_IDS,
    UNSUPPORTED_MANAGER_IDS,
    pool,
)

""" Test the pool and its content. """


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(pool()) == 16
    assert len(pool()) == len(ALL_MANAGER_IDS)
    assert ALL_MANAGER_IDS == tuple(sorted(set(pool())))


def test_cached_pool():
    assert pool() == pool()
    assert pool() is pool()


@pytest.mark.parametrize("manager_id", DEFAULT_MANAGER_IDS)
def test_supported_managers(manager_id):
    assert pool()[manager_id].supported is True


@pytest.mark.parametrize("manager_id", UNSUPPORTED_MANAGER_IDS)
def test_unsupported_managers(manager_id):
    assert pool()[manager_id].supported is False


def test_manager_groups():
    assert len(DEFAULT_MANAGER_IDS) + len(UNSUPPORTED_MANAGER_IDS) == len(
        ALL_MANAGER_IDS
    )
    assert (
        tuple(sorted(set(DEFAULT_MANAGER_IDS).union(UNSUPPORTED_MANAGER_IDS)))
        == ALL_MANAGER_IDS
    )
