# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

from __future__ import annotations

from itertools import combinations

from click_extra.platforms import ALL_PLATFORMS, Group

from ..platforms import PLATFORM_GROUPS
from .conftest import all_managers


def test_unique_ids():
    """IDs must be unique."""
    all_group_ids = {g.id for g in PLATFORM_GROUPS}
    assert len(all_group_ids) == len(PLATFORM_GROUPS)


def test_groups_content():
    for group in PLATFORM_GROUPS:
        assert isinstance(group, Group)
        assert len(group) > 0
        assert len(group.platforms) == len(group.platform_ids)
        assert group.issubset(ALL_PLATFORMS)


def test_platform_groups_no_overlap():
    """Check our platform groups are mutually exclusive."""
    for combination in combinations(PLATFORM_GROUPS, 2):
        assert combination[0].isdisjoint(combination[1])


@all_managers
def test_all_platforms_covered_by_groups(manager):
    """Check all platforms supported by managers are covered by a local group."""
    leftover_platforms = manager.platforms.copy()

    for group in PLATFORM_GROUPS:

        # Check the group fully overlap the manager platforms.
        if not group.isdisjoint(manager.platforms):
            assert group.issubset(manager.platforms)

            # Remove the group platforms from the uncovered list.
            leftover_platforms -= set(group.platforms)

    assert len(leftover_platforms) == 0
    # At this stage we know all platforms of the manager can be partitioned by a
    # combination of PLATFORM_GROUPS elements, without any overlap or leftover.
