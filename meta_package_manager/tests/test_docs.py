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
import sys
from collections import Counter
from pathlib import Path

from boltons.iterutils import flatten
from yaml import Loader, load

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import]

from ..labels import MANAGER_LABELS, MANAGER_PREFIX, PLATFORM_PREFIX
from ..platforms import PLATFORM_GROUPS, encoding_args
from ..pool import pool

""" Test all non-code artifacts depending on manager definitions.

Covers:
    * Documentation (sphinx, readme, etc.)
    * CI/CD scripts
    * GitHub project config

These tests are mainly there to remind us keep extra stuff in sync on new
platform or manager addition.
"""

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_project_metadata():
    # Fetch general information about the project from pyproject.toml.
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    toml_config = tomllib.loads(toml_path.read_text(**encoding_args))
    # Check all managers are referenced in Python package keywords.
    assert set(pool.all_manager_ids).issubset(toml_config["tool"]["poetry"]["keywords"])


def test_changelog():
    content = PROJECT_ROOT.joinpath("changelog.md").read_text(**encoding_args)

    assert content.startswith("# Changelog\n")

    entry_pattern = re.compile(r"^\* \[(?P<category>[a-z,]+)\] (?P<entry>.+)")
    for line in content.splitlines():
        if line.startswith("*"):
            match = entry_pattern.match(line)
            assert match
            entry = match.groupdict()
            assert entry["category"]
            assert set(entry["category"].split(",")).issubset(
                flatten(
                    (
                        pool.all_manager_ids,
                        PLATFORM_GROUPS.platform_ids,
                        "mpm",
                        "bar-plugin",
                    )
                )
            )


def test_new_package_manager_issue_template():
    """Check all platforms groups are referenced in the issue template."""
    content = PROJECT_ROOT.joinpath(
        ".github/ISSUE_TEMPLATE/new-package-manager.yaml"
    ).read_text(**encoding_args)
    assert content

    template_platforms = load(content, Loader=Loader)["body"][3]["attributes"][
        "options"
    ]

    reference_labels = []
    for group in PLATFORM_GROUPS:
        label = f"{group.icon} {group.name}"
        if len(group) > 1:
            label += f" ({', '.join(p.name for p in group.platforms)})"
        reference_labels.append({"label": label})

    assert template_platforms == reference_labels


def test_labeller_rules():
    # Extract list of extra labels.
    content = PROJECT_ROOT.joinpath(".github/labels-extra.json").read_text(
        **encoding_args
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
        ".github/workflows/labeller-content-based.yaml"
    ).read_text(**encoding_args)
    assert "Naturalclar/issue-action" in content
    json_rules = load(content, Loader=Loader)["jobs"]["labeller"]["steps"][0]["with"][
        "parameters"
    ]
    rules = json.loads(json_rules)
    assert rules

    # Each keyword match one rule only.
    rules_keywords = Counter(flatten([r["keywords"] for r in rules]))
    assert rules_keywords
    assert max(rules_keywords.values()) == 1

    # Extract and categorize labels.
    rules_labels = Counter(flatten([r["labels"] for r in rules]))

    assert rules_labels
    # Check that all canonical labels are referenced in rules.
    assert (canonical_labels - {"🔌 bar-plugin", "📦 manager: mpm"}).issubset(
        rules_labels
    )

    rules_managers = Counter(
        {
            label: count
            for label, count in rules_labels.items()
            if label.startswith(MANAGER_PREFIX)
        }
    )
    rules_platforms = Counter(
        {
            label: count
            for label, count in rules_labels.items()
            if label.startswith(PLATFORM_PREFIX)
        }
    )

    assert rules_managers
    # Each canonical manager labels is defined.
    assert len(canonical_managers.symmetric_difference(rules_managers)) == 0
    # Each manager has a rule and one only.
    assert max(rules_managers.values()) == 1

    assert rules_platforms
    # Each canonical platform labels is defined.
    assert len(canonical_platforms.symmetric_difference(rules_platforms)) == 0
    # Each registered OS has a rule.
    assert len(rules_platforms) == len(PLATFORM_GROUPS)
    # Each platforms has at least a rule.
    assert min(rules_platforms.values()) >= 1

    # Check that all canonical labels are referenced in rules.
    assert canonical_labels.issuperset(rules_platforms)

    # Check each rule definition.
    for rule in rules:
        # No duplicate labels.
        assert len(set(rule["labels"])) == len(rule["labels"])

        # Special checks for rules targeting manager labels.
        manager_label = canonical_managers.intersection(rule["labels"])
        if manager_label:
            # Extract manager label
            assert len(manager_label) == 1
            manager_label = manager_label.pop()

            # Only platforms are expected alongside manager labels.
            platforms_labels = set(rule["labels"]) - canonical_managers
            assert platforms_labels.issubset(canonical_platforms)

            # Check managers sharing the same label shares the same platforms specs.
            supported_platforms = [
                pool.get(mid).platforms
                for mid, lbl in MANAGER_LABELS.items()
                # Relying on pool restrict our checks, as the pool exclude
                # non-locally supported managers.
                if lbl == manager_label and mid in pool
            ]
            assert len(set(supported_platforms)) == 1

            # Regenerate the platforms specs from the label and check it matches.
            common_platforms = supported_platforms.pop()
            target_platforms = set()
            for platform_label in platforms_labels:
                group_name = platform_label.split(PLATFORM_PREFIX, 1)[1]
                assert group_name
                matching_groups = []
                for group in PLATFORM_GROUPS:
                    if group.name == group_name:
                        matching_groups.append(group)
                assert len(matching_groups) == 1
                target_platforms.update(matching_groups[0].platforms)
            assert target_platforms == common_platforms
