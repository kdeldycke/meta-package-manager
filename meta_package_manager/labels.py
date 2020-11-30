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

""" Utilities to manage GitHub labels to use in issues and PR management.
"""

from boltons.iterutils import flatten

from . import CLI_NAME
from .managers import pool
from .platform import ALL_OS_LABELS

# Format: label name, color, optional description.
LABELS = [
    (
        "🔌 BitBar plugin",
        "#fef2c0",
        "Plugin code, documentation or features related to BitBar",
    ),
    ("🐛 bug", "#d73a4a", "Something isn't working, or a fix is proposed"),
    ("🔩 CI/CD", "#dbca13", "Tests, automation and management of the project"),
    (
        "📗 documentation",
        "#006b75",
        "Update to non-code (manual, readme, tutorial, docstrings, ...) and "
        "its generation",
    ),
    ("🔄 duplicate", "#cfd3d7", "This issue or pull request already exists"),
    ("✨ enhancement", "#84b6eb", "Improvement or change of an existing feature"),
    (
        "🆕 feature request",
        "#fbca04",
        "Something not existing yet that need to be implemented",
    ),
    ("🌱 good first issue", "#7057ff", "A place for newcomers to start contributing"),
    ("🆘 help wanted", "#008672", "Extra attention is needed"),
    ("🎲 can't reproduce", "#fec1c1", "Root cause unlikely to come from the project"),
    ("❓ question", "#d876e3", "Further information is requested"),
    ("🚫 wont do/fix", "#eeeeee", "This will not be worked on"),
]


# Maps platform and manager ID to their labels.
PLATFORM_LABELS = {}
MANAGER_LABELS = {}


# Some managers sharing some roots will be grouped together.
MANAGER_GROUPS = {
    "dpkg-like": {"dpkg", "apt", "opkg"},
    "npm-like": {"npm", "yarn"},
}

# Define some colors.
PLATFORM_COLOR = "#bfd4f2"
MANAGER_COLOR = "#bfdadc"


# Create one label per platform.
for platform_id in ALL_OS_LABELS:
    label_id = f"🖥 platform: {platform_id}"
    LABELS.append((label_id, PLATFORM_COLOR, platform_id))
    PLATFORM_LABELS[platform_id] = label_id


# Create one label per manager. Add mpm as its own manager.
non_grouped_managers = set(pool()) - set(flatten(MANAGER_GROUPS.values())) | {CLI_NAME}
for manager_id in non_grouped_managers:
    label_id = f"📦 manager: {manager_id}"
    LABELS.append((label_id, MANAGER_COLOR, manager_id))
    if manager_id != CLI_NAME:
        MANAGER_LABELS[manager_id] = label_id


# Add labels for grouped managers.
for group_label, manager_ids in MANAGER_GROUPS.items():
    label_id = f"📦 manager: {group_label}"
    LABELS.append((label_id, MANAGER_COLOR, ", ".join(sorted(manager_ids))))
    for manager_id in manager_ids:
        MANAGER_LABELS[manager_id] = label_id
