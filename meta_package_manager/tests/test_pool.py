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
from boltons.iterutils import flatten

from ..cli import mpm
from ..pool import PURL_MAP, SkipPackage, pool, resolve_specs

""" Test the pool and its content. """


def test_manager_count():
    """Check all implemented package managers are accounted for, and unique."""
    assert len(pool) == 27
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
            if pool[mid].supported and pool[mid].available
        ),
    ),
    "keep_inactive": (
        {"drop_inactive": False},
        tuple(mid for mid in pool.all_manager_ids if pool[mid].supported),
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


def test_purl_map():
    # Check all our supported managers are registered.
    assert set(pool.all_manager_ids).issubset(PURL_MAP)
    # Check our hard-coded purl mapping points to implemented managers.
    assert (
        set(pool.all_manager_ids)
        .union({None})
        .issuperset(set(flatten(PURL_MAP.values())))
    )


@pytest.mark.parametrize(
    "specs,target_manager,expected",
    (
        pytest.param(
            ("leftpad", "left-pad", "left.pad", "left_pad"),
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": None,
                    "version_str": None,
                },
                {
                    "package_id": "left-pad",
                    "manager_id": None,
                    "version_str": None,
                },
                {
                    "package_id": "left.pad",
                    "manager_id": None,
                    "version_str": None,
                },
                {
                    "package_id": "left_pad",
                    "manager_id": None,
                    "version_str": None,
                },
            ),
            id="package_id_strings",
        ),
        pytest.param(
            ("leftpad",),
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": None,
                    "version_str": None,
                },
            ),
            id="tuple_specs",
        ),
        pytest.param(
            ["leftpad"],
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": None,
                    "version_str": None,
                },
            ),
            id="list_specs",
        ),
        pytest.param(
            {"leftpad"},
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": None,
                    "version_str": None,
                },
            ),
            id="set_specs",
        ),
        pytest.param(
            ("leftpad", "leftpad"),
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": None,
                    "version_str": None,
                },
            ),
            id="duplicates",
        ),
        pytest.param(
            {"left-pad@8.a7"},
            None,
            ({"package_id": "left-pad", "manager_id": None, "version_str": "8.a7"},),
            id="version_spec",
        ),
        pytest.param(
            {"left-pad", "left-pad@8.23.a7"},
            None,
            ({"package_id": "left-pad", "manager_id": None, "version_str": "8.23.a7"},),
            id="version_and_unversionned_mix",
        ),
        pytest.param(
            {"pkg:npm/leftpad"},
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": "npm",
                    "version_str": None,
                },
            ),
            id="purl_with_manager",
        ),
        pytest.param(
            {"pkg:npm/leftpad@1.2.3"},
            None,
            ({"package_id": "leftpad", "manager_id": "npm", "version_str": "1.2.3"},),
            id="purl_with_version",
        ),
        pytest.param(
            {"pkg:rubygems/dummy@21.0-b"},
            None,
            ({"package_id": "dummy", "manager_id": "gem", "version_str": "21.0-b"},),
            id="purl_single_alias",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["dnf", "yum", "zypper"],
            (
                {
                    "package_id": "ping",
                    "manager_id": "dnf",
                    "version_str": "2011-04.gamma",
                },
            ),
            id="purl_multiple_aliases_priority1",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["zypper", "yum"],
            (
                {
                    "package_id": "ping",
                    "manager_id": "zypper",
                    "version_str": "2011-04.gamma",
                },
            ),
            id="purl_multiple_aliases_priority2",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["pypi"],
            (),
            id="purl_multiple_aliases_unmatching_manager_skip_package",
        ),
        pytest.param(
            {"pkg:npm/leftpad", "leftpad@77.10.0"},
            None,
            (
                {
                    "package_id": "leftpad",
                    "manager_id": "npm",
                    "version_str": None,
                },
            ),
            id="purl_takes_precedence",
        ),
        pytest.param(
            {"leftpad", "leftpad@1.7.3", "pkg:npm/leftpad@1.7.3"},
            None,
            ({"package_id": "leftpad", "manager_id": "npm", "version_str": "1.7.3"},),
            id="mixed_package_specs",
        ),
        pytest.param(
            {"left-pad@33.1.a", "left-pad@0100"},
            None,
            ({"package_id": "left-pad", "manager_id": None, "version_str": "0100"},),
            id="multiple_versions",
        ),
        pytest.param(
            {"left-pad@99.00", "left-pad@99.00"},
            None,
            ({"package_id": "left-pad", "manager_id": None, "version_str": "99.00"},),
            id="duplicate_version_spec",
        ),
        pytest.param(
            {"left-pad@99.00", "left-pad@99"},
            None,
            ({"package_id": "left-pad", "manager_id": None, "version_str": "99.00"},),
            id="similar_version_spec",
        ),
    ),
)
def test_resolveable_specs(specs, target_manager, expected):
    # Transform dicts into sets to eliminate the effects of out of order.
    expected = sorted(sorted(d.items()) for d in expected)
    reduced_specs = sorted(
        sorted(d.items()) for d in resolve_specs(specs, target_manager)
    )
    assert reduced_specs == expected
