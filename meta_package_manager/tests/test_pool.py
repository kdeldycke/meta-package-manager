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

from ..cli import mpm
from ..pool import pool

""" Test the pool and its content. """


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(pool) == 25
    assert len(pool) == len(pool.all_manager_ids)
    assert pool.all_manager_ids == tuple(sorted(set(pool)))


def test_cached_pool():
    assert pool == pool
    assert pool is pool


@pytest.mark.parametrize("manager_id", pool.default_manager_ids)
def test_supported_managers(manager_id):
    assert pool[manager_id].supported is True


@pytest.mark.parametrize("manager_id", pool.unsupported_manager_ids)
def test_unsupported_managers(manager_id):
    assert pool[manager_id].supported is False


def test_manager_groups():
    assert len(pool.default_manager_ids) + len(pool.unsupported_manager_ids) == len(
        pool.all_manager_ids
    )
    assert (
        tuple(sorted(set(pool.default_manager_ids).union(pool.unsupported_manager_ids)))
        == pool.all_manager_ids
    )


def test_extra_option_allowlist():
    assert pool.ALLOWED_EXTRA_OPTION.issubset(opt.name for opt in mpm.params)


selection_cases = {
    "single_selector": (
        {"keep": ("apm",)},
        ("apm",),
    ),
    "list_input": (
        {"keep": ["apm"]},
        ("apm",),
    ),
    "set_input": (
        {"keep": {"apm"}},
        ("apm",),
    ),
    "duplicate_selectors": (
        {"keep": ("apm", "apm")},
        ("apm",),
    ),
    "multiple_selectors": (
        {"keep": ("apm", "gem")},
        ("apm", "gem"),
    ),
    "ordered_selectors": (
        {"keep": ("gem", "apm")},
        ("gem", "apm"),
    ),
    "single_exclusion": (
        {"drop": ("apm")},
        tuple(mid for mid in pool.default_manager_ids if mid != "apm"),
    ),
    "duplicate_exclusions": (
        {"drop": ("apm", "apm")},
        tuple(mid for mid in pool.default_manager_ids if mid != "apm"),
    ),
    "multiple_exclusions": (
        {"drop": ("apm", "gem")},
        tuple(mid for mid in pool.default_manager_ids if mid not in ("apm", "gem")),
    ),
    "selector_priority": (
        {"keep": ("apm"), "drop": ("gem")},
        ("apm",),
    ),
    "exclusion_override": (
        {"keep": ("apm"), "drop": ("apm")},
        (),
    ),
    "default_selection": (
        {},
        pool.default_manager_ids,
    ),
    "drop_unsupported": (
        {"drop_unsupported": True},
        pool.default_manager_ids,
    ),
    "keep_unsupported": (
        {"drop_unsupported": False},
        pool.all_manager_ids,
    ),
    "drop_inactive": (
        {"drop_inactive": True},
        tuple(mid for mid in pool.default_manager_ids if pool[mid].available),
    ),
    "keep_inactive": (
        {"drop_inactive": False},
        pool.default_manager_ids,
    ),
}


@pytest.mark.parametrize(
    "kwargs,expected",
    (
        pytest.param(kwargs, expected, id=test_id)
        for test_id, (kwargs, expected) in selection_cases.items()
    ),
)
def select_managers(kwargs, expected):
    """We use tuple everywhere so we can check that select_managers() conserve the
    original order."""
    selection = pool.select_managers(**kwargs)
    assert tuple(selection) == expected
