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

from boltons.iterutils import flatten
from click_extra.platform import ANY_PLATFORM, MACOS, ANY_BSD, ANY_LINUX, ANY_UNIX_BUT_MACOS, WINDOWS

from .pool import pool


LABELS = [
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


def generate_labels(all_labels: set[str], groups: dict[str, set[str]], prefix: str, color: str) -> dict[str, str]:
    """Generate labels."""
    # Check group definitions.
    group_entries = tuple(flatten(groups.values()))
    grouped_labels = set(group_entries)
    # Check there is no duplucates between groups.
    assert len(group_entries) == len(grouped_labels)
    # Check all labels to groups are referenced in the full label set.
    assert grouped_labels.issubset(all_labels)
    # Check group IDs do not collide with original labels.
    assert all_labels.isdisjoint(groups.keys())

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


# Add mpm as its own manager.
all_manager_ids = set(pool.all_manager_ids) | {"mpm"}

MANAGER_GROUPS: dict[str, set[str]] = {
    "dnf-based": {"dnf", "yum"},
    "dpkg-based": {"apt", "apt-mint", "opkg"},
    "npm-based": {"npm", "yarn"},
    "pacman-based": {"pacman", "pacaur", "paru", "yay"},
    "pip-based": {"pip", "pipx"},
}
"""Managers sharing some origin or implementation are grouped together."""

MANAGER_LABELS = generate_labels(all_manager_ids, MANAGER_GROUPS, "📦 manager: ", "#bfdadc")
""" Maps all manager IDs to their labels. """


PLATFORM_GROUPS: dict[str, set[str]] = {
    # Group all BSD platforms but macOS.
    "BSD": ANY_BSD - {MACOS},
    "Linux": ANY_LINUX,
    "macOS": {MACOS},
    "Unix": ANY_UNIX_BUT_MACOS - ANY_LINUX - ANY_BSD,
    "Windows": {WINDOWS},
}
"""Similar platforms are grouped together."""

PLATFORM_LABELS = generate_labels(ANY_PLATFORM, PLATFORM_GROUPS, "🖥 platform: ", "#bfd4f2")
""" Maps all platform names to their labels. """