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

"""Utilities to generate extra labels to use for GitHub issues and PRs."""

from __future__ import annotations

from typing import Dict, FrozenSet, Set, Union

from boltons.iterutils import flatten
from click_extra.platforms import ALL_PLATFORMS

from .platforms import PLATFORM_GROUPS
from .pool import pool

LABELS: list[tuple[str, str, str]] = [
    (
        "🔌 bar-plugin",
        "#fef2c0",
        "Xbar/SwiftBar plugin code, documentation and features",
    ),
]
"""Global registry of all labels used in the project.

Structure:

.. code-block:: python

    ("label_name", "color", "optional_description")
"""


LabelSet = FrozenSet[str]
LabelGroup = Dict[str, LabelSet]


def generate_labels(
    all_labels: LabelSet, groups: LabelGroup, prefix: str, color: str
) -> dict[str, str]:
    """Generate labels."""
    # Check group definitions.
    group_entries = tuple(flatten(groups.values()))
    grouped_labels = set(group_entries)
    # Check there is no duplucates between groups.
    assert len(group_entries) == len(grouped_labels)
    # Check all labels to groups are referenced in the full label set.
    assert grouped_labels.issubset(all_labels)

    new_labels = {}

    # Create a dedicated label for each non-grouped entry.
    standalone_labels = all_labels - grouped_labels
    for label_id in standalone_labels:
        full_name = f"{prefix}{label_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert full_name not in all_labels
        new_labels[label_id] = full_name
        # Register label to the global registry.
        LABELS.append((full_name, color, label_id))

    # Create a dedicated label for each group.
    for group_id, label_ids in groups.items():
        full_name = f"{prefix}{group_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert full_name not in all_labels
        for label_id in label_ids:
            new_labels[label_id] = full_name
        # Register label to the global registry.
        LABELS.append((full_name, color, ", ".join(sorted(label_ids))))

    return new_labels


MANAGER_PREFIX = "📦 manager: "

MANAGER_LABEL_GROUPS: LabelGroup = {
    "dnf-based": frozenset({"dnf", "yum"}),
    "dpkg-based": frozenset({"apt", "apt-mint", "opkg"}),
    "npm-based": frozenset({"npm", "yarn"}),
    "pacman-based": frozenset({"pacman", "pacaur", "paru", "yay"}),
    "pip-based": frozenset({"pip", "pipx"}),
}
"""Managers sharing some origin or implementation are grouped together under the same label."""

all_manager_label_ids = frozenset(set(pool.all_manager_ids) | {"mpm"})
"""Adds ``mpm`` as its own manager alongside all those implemented."""

# Check group IDs do not collide with original labels.
assert all_manager_label_ids.isdisjoint(MANAGER_LABEL_GROUPS.keys())

MANAGER_LABELS = generate_labels(
    all_manager_label_ids,
    MANAGER_LABEL_GROUPS,
    MANAGER_PREFIX,
    "#bfdadc"
)
""" Maps all manager IDs to their labels. """


PLATFORM_PREFIX = "🖥 platform: "

PLATFORM_LABEL_GROUPS: LabelGroup = {
    g.name: {p.name for p in g.platforms}
    for g in PLATFORM_GROUPS
}
"""Similar platforms are grouped together under the same label."""

all_platform_label_ids = frozenset(flatten(PLATFORM_LABEL_GROUPS.values()))

PLATFORM_LABELS = generate_labels(
    all_platform_label_ids,
    PLATFORM_LABEL_GROUPS,
    PLATFORM_PREFIX,
    "#bfd4f2"
)
""" Maps all platform names to their labels. """
