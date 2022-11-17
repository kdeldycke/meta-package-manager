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

from __future__ import annotations

import pytest

from ..cli import mpm
from ..pool import pool

""" Test the pool and its content. """


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(pool) == 28
    assert len(pool) == len(pool.all_manager_ids)
    assert pool.all_manager_ids == tuple(sorted(set(pool)))


def test_cached_pool():
    assert pool == pool
    assert pool is pool


@pytest.mark.parametrize("manager_id", pool.maintained_manager_ids)
def test_maintained_managers(manager_id):
    assert pool[manager_id].deprecated is False


@pytest.mark.parametrize("manager_id", pool.default_manager_ids)
def test_supported_managers(manager_id):
    assert pool[manager_id].supported is True


@pytest.mark.parametrize("manager_id", pool.unsupported_manager_ids)
def test_unsupported_managers(manager_id):
    assert pool[manager_id].supported is False


def test_manager_groups():
    """Test relationships between manager groups."""
    assert set(pool.maintained_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.default_manager_ids).issubset(pool.all_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.all_manager_ids)

    assert set(pool.default_manager_ids).issubset(pool.maintained_manager_ids)
    assert set(pool.unsupported_manager_ids).issubset(pool.maintained_manager_ids)

    assert len(pool.default_manager_ids) + len(pool.unsupported_manager_ids) == len(
        pool.maintained_manager_ids
    )
    assert (
        tuple(sorted(set(pool.default_manager_ids).union(pool.unsupported_manager_ids)))
        == pool.maintained_manager_ids
    )


def test_extra_option_allowlist():
    assert pool.ALLOWED_EXTRA_OPTION.issubset(opt.name for opt in mpm.params)


selection_cases = {
    "single_selector": (
        {"keep": ("pip",)},
        ("pip",),
    ),
    "list_input": (
        {"keep": ["pip"]},
        ("pip",),
    ),
    "set_input": (
        {"keep": {"pip"}},
        ("pip",),
    ),
    "empty_selector": (
        {"keep": ()},
        (),
    ),
    "duplicate_selectors": (
        {"keep": ("pip", "pip")},
        ("pip",),
    ),
    "multiple_selectors": (
        {"keep": ("pip", "gem")},
        ("pip", "gem"),
    ),
    "ordered_selectors": (
        {"keep": ("gem", "pip")},
        ("gem", "pip"),
    ),
    "single_exclusion": (
        {"drop": {"pip"}},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "pip"
        ),
    ),
    "duplicate_exclusions": (
        {"drop": ("pip", "pip")},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid != "pip"
        ),
    ),
    "multiple_exclusions": (
        {"drop": ("pip", "gem")},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available and mid not in ("pip", "gem")
        ),
    ),
    "selector_priority": (
        {"keep": {"pip"}, "drop": {"gem"}},
        ("pip",),
    ),
    "exclusion_override": (
        {"keep": {"pip"}, "drop": {"pip"}},
        (),
    ),
    "default_selection": (
        {},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "explicit_default_selection": (
        {"keep": None, "drop": None},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_deprecated": (
        {"keep_deprecated": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_deprecated": (
        {"keep_deprecated": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_unsupported": (
        {"keep_unsupported": True},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].available),
    ),
    "drop_unsupported": (
        {"keep_unsupported": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "drop_inactive": (
        {"drop_inactive": True},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_inactive": (
        {"drop_inactive": False},
        tuple(
            mid
            for mid in pool.all_manager_ids
            if not pool[mid].deprecated and pool[mid].supported
        ),
    ),
}


@pytest.mark.parametrize(
    "kwargs,expected",
    (
        pytest.param(kwargs, expected, id=test_id)
        for test_id, (kwargs, expected) in selection_cases.items()
    ),
)
def test_select_managers(kwargs, expected):
    """We use tuple everywhere so we can check that select_managers() conserve the
    original order."""
    selection = pool.select_managers(**kwargs)
    assert tuple(m.id for m in selection) == expected
