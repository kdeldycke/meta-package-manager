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

import json
import re
import tomllib
from collections import Counter
from itertools import permutations
from pathlib import Path

from boltons.iterutils import flatten
from extra_platforms import Group
from yaml import Loader, load

from meta_package_manager.inventory import MAIN_PLATFORMS
from meta_package_manager.labels import LABELS, MANAGER_PREFIX, PLATFORM_PREFIX
from meta_package_manager.pool import pool

from .conftest import all_managers

""" Test all non-code artifacts depending on manager definitions.

Covers:
    * Documentation (sphinx, readme, etc.)
    * CI/CD scripts
    * GitHub project config

These tests are mainly there to remind us keep extra stuff in sync on new
platform or manager addition.
"""

PROJECT_ROOT = Path(__file__).parent.parent


def test_unique_local_group_ids():
    """Check our platform groups have unique identifiers."""
    group_ids = [p.id for p in MAIN_PLATFORMS]
    assert len(group_ids) == len(set(group_ids))


def test_local_groups_no_overlap():
    """Check our platform groups are mutually exclusive."""
    for a, b in permutations(MAIN_PLATFORMS, 2):
        if isinstance(a, Group):
            assert a.isdisjoint(b)


@all_managers
def test_all_platforms_covered_by_local_groups(manager):
    """Check all platforms supported by managers are covered by a local group."""
    leftover_platforms = set(manager.platforms.copy())

    for main_platform in (set(Group._extract_platforms(i)) for i in MAIN_PLATFORMS):
        # Check the group fully overlap the manager platforms.
        if main_platform.issubset(manager.platforms):
            # Remove the group platforms from the uncovered list.
            leftover_platforms -= main_platform

    assert len(leftover_platforms) == 0
    # At this stage we know all platforms of the manager can be partitioned by a
    # combination of MAIN_PLATFORMS elements, without any overlap or leftover.


def test_project_metadata():
    # Fetch general information about the project from pyproject.toml.
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    # Check all managers are referenced in Python package keywords.
    assert set(pool.all_manager_ids).issubset(toml_config["project"]["keywords"])


def test_changelog():
    content = PROJECT_ROOT.joinpath("changelog.md").read_text(encoding="utf-8")
    assert content.startswith("# Changelog\n")

    entry_pattern = re.compile(r"^- \[(?P<category>[a-z0-9,\-]+)\] (?P<entry>.+)")

    allowed_categories = set((
        *pool.all_manager_ids,
        *(p.id for p in MAIN_PLATFORMS),
        "mpm",
        "bar-plugin",
    ))

    for line in content.splitlines():
        if line.startswith("-"):
            match = entry_pattern.match(line)
            assert match
            entry = match.groupdict()
            assert entry["category"]
            categories = entry["category"].split(",")
            assert len(categories)
            assert len(categories) == len(set(categories))
            assert categories == sorted(categories)
            assert set(categories).issubset(allowed_categories)


def test_labels():
    for name, color, description in LABELS:
        assert name
        assert color
        assert color.startswith("#")
        assert len(description) <= 100


def test_new_package_manager_issue_template():
    """Check all platforms groups are referenced in the issue template."""
    content = PROJECT_ROOT.joinpath(
        ".github/ISSUE_TEMPLATE/new-package-manager.yaml",
    ).read_text(encoding="utf-8")
    assert content

    template_platforms = load(content, Loader=Loader)["body"][3]["attributes"][
        "options"
    ]

    reference_labels = []
    for p_obj in MAIN_PLATFORMS:
        label = f"{p_obj.icon} {p_obj.name}"
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            label += f" ({', '.join(p.name for p in p_obj.platforms)})"
        reference_labels.append({"label": label})

    assert template_platforms == reference_labels


def test_labeller_rules():
    # Extract list of extra labels.
    content = PROJECT_ROOT.joinpath(".github/labels-extra.json").read_text(
        encoding="utf-8"
    )
    assert content

    extra_labels = [lbl["name"] for lbl in json.loads(content)]
    assert extra_labels

    # Canonical labels are uniques.
    assert len(extra_labels) == len(set(extra_labels))
    canonical_labels = set(extra_labels)
    assert canonical_labels

    # Extract and categorize labels.
    canonical_managers = {
        lbl
        for lbl in canonical_labels
        if lbl.startswith(MANAGER_PREFIX) and "mpm" not in lbl
    }
    assert canonical_managers
    canonical_platforms = {
        lbl for lbl in canonical_labels if lbl.startswith(PLATFORM_PREFIX)
    }
    assert canonical_platforms

    # Extract rules from json blurb serialized into YAML.
    content = PROJECT_ROOT.joinpath(
        ".github/workflows/labeller-content-based.yaml",
    ).read_text(encoding="utf-8")
    assert "kdeldycke/workflows/.github/workflows/labeller-file-based.yaml" in content
    extra_rules = load(content, Loader=Loader)["jobs"]["labeller"]["with"][
        "extra-rules"
    ]
    rules = load(extra_rules, Loader=Loader)
    assert rules

    # Each keyword match one rule only.
    rules_keywords = Counter(flatten(rules.values()))
    assert rules_keywords
    assert max(rules_keywords.values()) == 1

    # Check that all canonical labels are referenced in rules.
    assert (canonical_labels - {"📦 manager: mpm"}).issubset(rules.keys())
