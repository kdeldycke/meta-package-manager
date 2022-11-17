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
from click_extra.platform import ALL_OS_LABELS

from .pool import pool

CLI_NAME = "mpm"
"""Main CLI ID."""

LABELS = [
    (
        "🔌 bar-plugin",
        "#fef2c0",
        "Xbar/SwiftBar plugin code, documentation and features",
    ),
]
"""Structure: ``("label_name", "color", "optional_description")``."""


PLATFORM_LABELS = {}
""" Maps all platform names to their labels. """


MANAGER_LABELS = {}
""" Maps all manager IDs to their labels. """


MANAGER_GROUPS = {
    "dnf-based": {"dnf", "yum"},
    "dpkg-based": {"dpkg", "apt", "apt-mint", "opkg"},
    "npm-based": {"npm", "yarn"},
    "pacman-based": {"pacman", "pacaur", "paru", "yay"},
    "pip-based": {"pip", "pipx"},
}
"""Managers sharing some roots or implementation will be grouped together."""


PLATFORM_PREFIX = "🖥 platform: "
"""Default platform label prefix."""

PLATFORM_COLOR = "#bfd4f2"
"""Default platform label color."""

MANAGER_PREFIX = "📦 manager: "
"""Default manager label prefix."""

MANAGER_COLOR = "#bfdadc"
"""Default manager label color."""


# Create one label per platform.
for platform_name in ALL_OS_LABELS:
    label_id = f"{PLATFORM_PREFIX}{platform_name}"
    LABELS.append((label_id, PLATFORM_COLOR, platform_name))
    PLATFORM_LABELS[platform_name] = label_id


# Create one label per manager. Add mpm as its own manager.
non_grouped_managers = set(pool) - set(flatten(MANAGER_GROUPS.values())) | {CLI_NAME}
for manager_id in non_grouped_managers:
    label_id = f"{MANAGER_PREFIX}{manager_id}"
    LABELS.append((label_id, MANAGER_COLOR, manager_id))
    if manager_id != CLI_NAME:
        MANAGER_LABELS[manager_id] = label_id


# Add labels for grouped managers.
for group_label, manager_ids in MANAGER_GROUPS.items():
    label_id = f"{MANAGER_PREFIX}{group_label}"
    LABELS.append((label_id, MANAGER_COLOR, ", ".join(sorted(manager_ids))))
    for manager_id in manager_ids:
        MANAGER_LABELS[manager_id] = label_id
