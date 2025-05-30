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

from dataclasses import asdict
from itertools import chain
from string import ascii_lowercase, digits

import pytest

from meta_package_manager.pool import pool
from meta_package_manager.specifier import PURL_MAP, EmptyReduction, Solver, Specifier


def test_purl_map():
    # Check pURL type IDs. See:
    # https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst#rules-for-each-purl-component
    for purl_type in PURL_MAP:
        assert purl_type.isascii()
        assert purl_type[0] in ascii_lowercase
        assert set(purl_type).issubset(ascii_lowercase + digits + ".+-")

    # Check that keys are sorted.
    assert list(PURL_MAP.keys()) == sorted(PURL_MAP.keys())

    # Check that all registered managers are known to the pool.
    referenced_manager_ids = set(
        chain.from_iterable(ids for ids in PURL_MAP.values() if ids is not None)
    )
    assert set(pool.all_manager_ids).issuperset(referenced_manager_ids), (
        "Unknown manager IDs found in PURL_MAP: "
        + ", ".join(referenced_manager_ids.difference(pool.all_manager_ids))
    )

    # Check that each manager whose ID is also a pURL type is registered with itself.
    for manager_id in pool.all_manager_ids:
        if manager_id in PURL_MAP:
            assert manager_id in PURL_MAP[manager_id], (
                f"Manager ID '{manager_id}' is not registered with itself in PURL_MAP."
            )


def props(spec: Specifier):
    """Utility to help compares specifiers between themselves.

    I.e. all properties of specifiers are the same but the ``raw_specs`` property.
    """
    return sorted((k, v) for k, v in asdict(spec).items() if k != "raw_spec")


@pytest.mark.parametrize(
    ("spec_string", "expected"),
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
            "left/pad",
            ({"package_id": "left/pad", "manager_id": None, "version": None},),
            id="slash",
        ),
        pytest.param(
            "left-pad@",
            ({"package_id": "left-pad@", "manager_id": None, "version": None},),
            id="version_separator",
        ),
        pytest.param(
            "left-pad@8.a7",
            ({"package_id": "left-pad", "manager_id": None, "version": "8.a7"},),
            id="version_spec",
        ),
        pytest.param(
            "left-pad@8.a7@1.2.3",
            ({"package_id": "left-pad@8.a7", "manager_id": None, "version": "1.2.3"},),
            id="double_version_separator",
        ),
        pytest.param(
            "@eslint/json",
            ({"package_id": "@eslint/json", "manager_id": None, "version": None},),
            id="starting_with_at_sign",
        ),
        pytest.param(
            "@eslint/json@0.9.0",
            ({"package_id": "@eslint/json", "manager_id": None, "version": "0.9.0"},),
            id="at_sign_and_version",
        ),
        pytest.param(
            "pkg:gem/dummy",
            ({"package_id": "dummy", "manager_id": "gem", "version": None},),
            id="purl_with_identical_manager",
        ),
        pytest.param(
            "pkg:gem/dummy@1.2.3",
            ({"package_id": "dummy", "manager_id": "gem", "version": "1.2.3"},),
            id="purl_with_version",
        ),
        pytest.param(
            "pkg:rubygems/dummy@21.0-b",
            ({"package_id": "dummy", "manager_id": "gem", "version": "21.0-b"},),
            id="purl_single_alias",
        ),
        pytest.param(
            "pkg:steamcmd/half-life@3",
            ({"package_id": "half-life", "manager_id": "steamcmd", "version": "3"},),
            id="purl_unregistered_manager",
        ),
        pytest.param(
            "pkg:npm/left-pad@2011-04.gamma",
            (
                {
                    "package_id": "left-pad",
                    "manager_id": "npm",
                    "version": "2011-04.gamma",
                },
                {
                    "package_id": "left-pad",
                    "manager_id": "yarn",
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
    ("spec_strings", "target_managers", "expected"),
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
            id="version_and_unversioned_mix",
        ),
        pytest.param(
            {"pkg:gem/leftpad"},
            None,
            Specifier.from_string("pkg:gem/leftpad"),
            id="purl_with_manager",
        ),
        pytest.param(
            {"pkg:gem/leftpad@1.2.3"},
            None,
            Specifier.from_string("pkg:gem/leftpad@1.2.3"),
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
            id="unresolvable_multiple_aliases",
        ),
        pytest.param(
            {"pkg:gem/leftpad", "leftpad@77.10.0"},
            None,
            Specifier.from_string("pkg:gem/leftpad"),
            id="purl_takes_precedence",
        ),
        pytest.param(
            {"leftpad", "leftpad@1.7.3", "pkg:gem/leftpad@1.7.3"},
            None,
            Specifier.from_string("pkg:gem/leftpad@1.7.3"),
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
