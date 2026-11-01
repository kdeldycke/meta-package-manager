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
"""Run the test suite of purl-spec against the pURL parser and renderer of `mpm`.

`tests/purl-spec/` copies the `LICENSE`, the type definitions of `types/` and the
test suite of `tests/` from the
[purl-spec `v1.1.0` release](https://github.com/package-url/purl-spec/releases/tag/v1.1.0).
To move to a newer release:

1. Replace the three with those of the release.
2. Format the JSON files with `repomatic run biome -- format --write tests/purl-spec`.
3. Fix the rows of `PURL_TYPES` that `test_purl_types_match_their_definitions` names.

typos skips the copy, per `[tool.typos]` in `pyproject.toml`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meta_package_manager.package import PURL_TYPES, PurlType, parse_purl, render_purl

PURL_SPEC = Path(__file__).parent / "purl-spec"

_UPPERCASE_KEY = (
    "Clause 5.6.6 of ECMA-427 allows lowercase qualifier keys only, and the required"
    " gem and rpm parse cases refuse an uppercase one, but this case accepts it:"
    " package-url/purl-spec#942 and package-url/purl-spec#1027."
)

SPEC_CONTRADICTIONS = {
    "git-test-0": (
        "The git definition keeps the case of the namespace and the name, but this"
        " case lowercases them."
    ),
    "maven-test-8": _UPPERCASE_KEY,
    "maven-test-9": _UPPERCASE_KEY,
    "maven-test-12": _UPPERCASE_KEY,
    "maven-test-13": _UPPERCASE_KEY,
    "gem-test-0": _UPPERCASE_KEY,
    "rpm-test-0": _UPPERCASE_KEY,
}
"""Cases of the suite that contradict the standard or another case, by ID."""


def _definitions() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="UTF-8"))
        for path in sorted((PURL_SPEC / "types").glob("*-definition.json"))
    ]


def _cases(test_type: str) -> list:
    """The cases of `test_type` in the suite, one parameter each."""
    params = []
    for path in sorted((PURL_SPEC / "tests").rglob("*-test.json")):
        cases = json.loads(path.read_text(encoding="UTF-8"))["tests"]
        for index, case in enumerate(cases):
            if case["test_type"] != test_type:
                continue
            case_id = f"{path.stem}-{index}"
            marks = ()
            if case_id in SPEC_CONTRADICTIONS:
                reason = SPEC_CONTRADICTIONS[case_id]
                marks = (pytest.mark.xfail(reason=reason, strict=True),)
            params.append(pytest.param(case, id=case_id, marks=marks))
    return params


def _parts(components: dict) -> tuple:
    """The parts `parse_purl()` returns, from the components of a test case."""
    return tuple(
        components.get(key) or None for key in ("type", "namespace", "name", "version")
    )


def test_purl_types_match_their_definitions():
    """Each registered type has a row stating the rules of its definition."""
    expected = {}
    for definition in _definitions():
        lowercase = tuple(
            component
            for component in ("namespace", "name", "version")
            if definition.get(f"{component}_definition", {}).get("case_sensitive")
            is False
        )
        qualifiers = tuple(
            qualifier["key"]
            for qualifier in definition.get("qualifiers_definition", [])
            if qualifier.get("requirement") == "required"
        )
        namespace = definition.get("namespace_definition", {})
        expected[definition["type"]] = PurlType(
            namespace.get("requirement", "optional"), lowercase, qualifiers
        )
    assert PURL_TYPES == expected


@pytest.mark.parametrize("case", _cases("parse"))
def test_parse_case(case):
    """`parse_purl()` splits each valid pURL of the suite, and refuses the others."""
    if case["expected_failure"]:
        with pytest.raises(ValueError):
            parse_purl(case["input"])
    else:
        assert parse_purl(case["input"]) == _parts(case["expected_output"])


@pytest.mark.parametrize("case", _cases("validate"))
def test_validate_case(case):
    """A pURL reads like its canonical form, and an invalid one is refused."""
    if case["expected_failure"]:
        with pytest.raises(ValueError):
            parse_purl(case["input"])
    else:
        assert parse_purl(case["input"]) == parse_purl(case["expected_output"])


@pytest.mark.parametrize("case", _cases("build"))
def test_build_case(case):
    """`render_purl()` renders each valid set of parts, and refuses the others."""
    parts = case["input"]

    def build() -> str:
        return render_purl(
            parts.get("type") or "",
            parts.get("namespace"),
            parts.get("name") or "",
            parts.get("version"),
            parts.get("qualifiers"),
            parts.get("subpath"),
        )

    if case["expected_failure"]:
        with pytest.raises(ValueError):
            build()
    else:
        assert build() == case["expected_output"]
