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

""" Utilities to manage extra labels to use for GitHub issues and PRs.
"""

from boltons.iterutils import flatten
from click_extra.platform import ALL_OS_LABELS

from .pool import pool

CLI_NAME = "mpm"

# Format: label name, color, optional description.
LABELS = [
    (
        "🔌 BitBar plugin",
        "#fef2c0",
        "Plugin code, documentation or features related to BitBar",
    ),
    (
        "🔌 xbar plugin",
        "#fef2c0",
        "Plugin code, documentation or features related to xbar",
    ),
]


# Maps platform and manager ID to their labels.
PLATFORM_LABELS = {}
MANAGER_LABELS = {}


# Some managers sharing some roots will be grouped together.
MANAGER_GROUPS = {
    "dpkg-like": {"dpkg", "apt", "apt-mint", "opkg"},
    "npm-like": {"npm", "yarn"},
}


# Define generated labels prefixes and colors.
PLATFORM_PREFIX = "🖥 platform: "
PLATFORM_COLOR = "#bfd4f2"
MANAGER_PREFIX = "📦 manager: "
MANAGER_COLOR = "#bfdadc"


# Create one label per platform.
for platform_id in ALL_OS_LABELS:
    label_id = f"{PLATFORM_PREFIX}{platform_id}"
    LABELS.append((label_id, PLATFORM_COLOR, platform_id))
    PLATFORM_LABELS[platform_id] = label_id


# Create one label per manager. Add mpm as its own manager.
non_grouped_managers = set(pool()) - set(flatten(MANAGER_GROUPS.values())) | {CLI_NAME}
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
