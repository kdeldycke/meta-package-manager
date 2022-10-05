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

from dataclasses import asdict

import pytest
from boltons.iterutils import flatten

from ..pool import pool
from ..specifier import PURL_MAP, EmptyReduction, Solver, Specifier


def test_purl_map():
    # Check all our supported managers are registered.
    assert set(pool.all_manager_ids).issubset(PURL_MAP)
    # Check our hard-coded purl mapping points to implemented managers.
    assert (
        set(pool.all_manager_ids)
        .union({None})
        .issuperset(set(flatten(PURL_MAP.values())))
    )


def props(spec: Specifier):
    """Utility to help compares specifiers between themselves.

    I.e. all properties of specifiers are the same but the ``raw_specs`` property.
    """
    return sorted((k, v) for k, v in asdict(spec).items() if k != "raw_spec")


@pytest.mark.parametrize(
    "spec_string, expected",
    (
        pytest.param(
            "leftpad",
            ({"package_id": "leftpad", "manager_id": None, "version": None},),
            id="ascii",
        ),
        pytest.param(
            "left_pad",
            ({"package_id": "left_pad", "manager_id": None, "version": None},),
            id="underscore",
        ),
        pytest.param(
            "left.pad",
            ({"package_id": "left.pad", "manager_id": None, "version": None},),
            id="dot",
        ),
        pytest.param(
            "left-pad",
            ({"package_id": "left-pad", "manager_id": None, "version": None},),
            id="dash",
        ),
        pytest.param(
            "left-pad@8.a7",
            ({"package_id": "left-pad", "manager_id": None, "version": "8.a7"},),
            id="version_spec",
        ),
        pytest.param(
            "pkg:npm/leftpad",
            (
                {
                    "package_id": "leftpad",
                    "manager_id": "npm",
                    "version": None,
                },
            ),
            id="purl_with_manager",
        ),
        pytest.param(
            "pkg:npm/leftpad@1.2.3",
            ({"package_id": "leftpad", "manager_id": "npm", "version": "1.2.3"},),
            id="purl_with_version",
        ),
        pytest.param(
            "pkg:rubygems/dummy@21.0-b",
            ({"package_id": "dummy", "manager_id": "gem", "version": "21.0-b"},),
            id="purl_single_alias",
        ),
        pytest.param(
            "pkg:rpm/ping@2011-04.gamma",
            (
                {
                    "package_id": "ping",
                    "manager_id": "dnf",
                    "version": "2011-04.gamma",
                },
                {
                    "package_id": "ping",
                    "manager_id": "yum",
                    "version": "2011-04.gamma",
                },
                {
                    "package_id": "ping",
                    "manager_id": "zypper",
                    "version": "2011-04.gamma",
                },
            ),
            id="purl_multiple_aliases",
        ),
    ),
)
def test_parse_specs(spec_string, expected):
    specs = tuple(Specifier.from_string(spec_string))

    spec_props = []
    for spec in specs:
        assert spec.raw_spec == spec_string
        # Serialize each specifier into an hashable set without the 'raw_spec'
        # field (which we checked above).
        spec_props.append(props(spec))

    assert sorted(spec_props) == sorted(sorted(s.items()) for s in expected)


@pytest.mark.parametrize(
    "spec_strings,target_managers,expected",
    (
        pytest.param(
            ("leftpad",),
            None,
            Specifier.from_string("leftpad"),
            id="tuple_specs",
        ),
        pytest.param(
            ["leftpad"],
            None,
            Specifier.from_string("leftpad"),
            id="list_specs",
        ),
        pytest.param(
            {"leftpad"},
            None,
            Specifier.from_string("leftpad"),
            id="set_specs",
        ),
        pytest.param(
            ("leftpad", "leftpad"),
            None,
            Specifier.from_string("leftpad"),
            id="duplicates",
        ),
        pytest.param(
            {"left-pad@8.a7"},
            None,
            Specifier.from_string("left-pad@8.a7"),
            id="version_spec",
        ),
        pytest.param(
            {"left-pad", "left-pad@8.23.a7"},
            None,
            Specifier.from_string("left-pad@8.23.a7"),
            id="version_and_unversionned_mix",
        ),
        pytest.param(
            {"pkg:npm/leftpad"},
            None,
            Specifier.from_string("pkg:npm/leftpad"),
            id="purl_with_manager",
        ),
        pytest.param(
            {"pkg:npm/leftpad@1.2.3"},
            None,
            Specifier.from_string("pkg:npm/leftpad@1.2.3"),
            id="purl_with_version",
        ),
        pytest.param(
            {"pkg:rubygems/dummy@21.0-b"},
            None,
            Specifier.from_string("pkg:gem/dummy@21.0-b"),
            id="purl_single_alias",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["dnf", "yum", "zypper"],
            Specifier.from_string("pkg:dnf/ping@2011-04.gamma"),
            id="purl_multiple_aliases_priority1",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["zypper", "yum"],
            Specifier.from_string("pkg:zypper/ping@2011-04.gamma"),
            id="purl_multiple_aliases_priority2",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            ["pypi"],
            EmptyReduction,
            id="purl_multiple_aliases_unmatching_manager_skip_package",
        ),
        pytest.param(
            {"pkg:rpm/ping@2011-04.gamma"},
            None,
            ValueError,
            id="unresolveable_multiple_aliases",
        ),
        pytest.param(
            {"pkg:npm/leftpad", "leftpad@77.10.0"},
            None,
            Specifier.from_string("pkg:npm/leftpad"),
            id="purl_takes_precedence",
        ),
        pytest.param(
            {"leftpad", "leftpad@1.7.3", "pkg:npm/leftpad@1.7.3"},
            None,
            Specifier.from_string("pkg:npm/leftpad@1.7.3"),
            id="mixed_package_specs",
        ),
        pytest.param(
            {"left-pad@33.1.a", "left-pad@0100"},
            None,
            Specifier.from_string("left-pad@0100"),
            id="multiple_versions",
        ),
        pytest.param(
            {"left-pad@99.00", "left-pad@99.00"},
            None,
            Specifier.from_string("left-pad@99.00"),
            id="duplicate_version_spec",
        ),
        pytest.param(
            {"left-pad@99.00", "left-pad@99"},
            None,
            Specifier.from_string("left-pad@99.00"),
            id="similar_version_spec",
        ),
        pytest.param(
            {"left-pad@99.00", "left-pad@0099.00"},
            None,
            ValueError,
            id="equivalent_version_spec",
        ),
    ),
)
def test_reduce_specs(spec_strings, target_managers, expected):
    solver = Solver(spec_strings, manager_priority=target_managers)

    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            solver.reduce_specs(solver.spec_pool)

    else:
        reduced_spec = solver.reduce_specs(solver.spec_pool)
        expected = tuple(expected)
        assert len(expected) == 1
        assert props(reduced_spec) == props(expected[0])
