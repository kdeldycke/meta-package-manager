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

import re
from collections import Counter
from pathlib import Path

import simplejson as json
import tomli
from boltons.iterutils import flatten
from click_extra.platform import OS_DEFINITIONS, os_label
from click_extra.tests.conftest import unless_linux
from yaml import Loader, load

from ..labels import MANAGER_LABELS, MANAGER_PREFIX, PLATFORM_LABELS, PLATFORM_PREFIX
from ..pool import ALL_MANAGER_IDS, pool

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
    toml_path = Path(__file__).parent.joinpath("../../pyproject.toml").resolve()
    toml_config = tomli.loads(toml_path.read_text())
    # Check all managers are referenced in Python package keywords.
    assert set(ALL_MANAGER_IDS).issubset(toml_config["tool"]["poetry"]["keywords"])


def test_changelog():
    content = PROJECT_ROOT.joinpath("changelog.md").read_text()

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
                    (ALL_MANAGER_IDS, OS_DEFINITIONS.keys(), "mpm", "bitbar", "xbar")
                )
            )


@unless_linux
def test_labeller_rules():
    """This covers the dynamic production of labels by GitHub action. As such it
    only targets Linux. See: https://github.com/kdeldycke/meta-package-manager/blob
    /bd666e291c783fe480015c9aae3beab19b12774c/.github/workflows/labels.yaml#L14
    """

    # Extract list of extra labels.
    content = PROJECT_ROOT.joinpath(".github/labels-extra.json").read_text()
    extra_labels = [lbl["name"] for lbl in json.loads(content)]

    # Canonical labels are uniques.
    assert len(extra_labels) == len(set(extra_labels))
    canonical_labels = set(extra_labels)

    # Extract and categorize labels.
    canonical_managers = {
        lbl
        for lbl in canonical_labels
        if lbl.startswith(MANAGER_PREFIX) and "mpm" not in lbl
    }
    canonical_platforms = {
        lbl for lbl in canonical_labels if lbl.startswith(PLATFORM_PREFIX)
    }
    assert canonical_managers
    assert canonical_platforms

    # Extract rules from json blurb serialized into YAML.
    content = PROJECT_ROOT.joinpath(
        ".github/workflows/labeller-content-based.yaml"
    ).read_text()
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
    assert (canonical_labels - {"🔌 BitBar plugin", "📦 manager: mpm"}).issubset(
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
    assert len(rules_platforms) == len(OS_DEFINITIONS)
    # Each platforms has at least a rule.
    assert min(rules_platforms.values()) >= 1

    # Check that all canonical labels are referenced in rules.
    assert canonical_labels.issuperset(rules_platforms)

    # Check each rule definition.
    for rule in rules:

        # No duplicate labels.
        assert len(set(rule["labels"])) == len(rule["labels"])

        # Special checks for rules targetting manager labels.
        manager_label = canonical_managers.intersection(rule["labels"])
        if manager_label:

            # Extract manager label
            assert len(manager_label) == 1
            manager_label = manager_label.pop()

            # Only platforms are expected alongside manager labels.
            platforms = set(rule["labels"]) - canonical_managers
            assert platforms.issubset(canonical_platforms)

            # Check managers sharing the same label shares the same platforms.
            supported_platforms = [
                pool()[mid].platforms
                for mid, lbl in MANAGER_LABELS.items()
                # Relying on pool() restrict our checks, as the pool exclude
                # non-locally supported managers.
                if lbl == manager_label and mid in pool()
            ]
            assert len(set(supported_platforms)) == 1

            # Check the right platforms is associated with the manager.
            supported_platform_labels = {
                PLATFORM_LABELS[os_label(p)] for p in supported_platforms[0]
            }
            assert platforms == supported_platform_labels
