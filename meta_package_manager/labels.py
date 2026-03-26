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
"""Utilities to generate extra labels to use for GitHub issues and PRs."""

from __future__ import annotations

from boltons.iterutils import flatten
from extra_platforms import extract_members

from .inventory import MAIN_PLATFORMS
from .pool import pool

TYPE_CHECKING = False
if TYPE_CHECKING:
    TLabelSet = frozenset[str]
    TLabelGroup = dict[str, TLabelSet]


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


def generate_labels(
    all_labels: TLabelSet,
    groups: TLabelGroup,
    prefix: str,
    color: str,
) -> dict[str, str]:
    """Generate labels.

    A dedicated label is produced for each entry of the ``all_labels`` parameter,
    unless it is part of a ``group``. In which case a dedicated label for that group
    will be created.
    """
    # Check all labels to group are referenced in the full label set.
    grouped_labels = set(flatten(groups.values()))
    assert grouped_labels.issubset(all_labels)

    label_map = {}

    # Create a dedicated label for each non-grouped entry.
    standalone_labels = all_labels - grouped_labels
    for label_id in standalone_labels:
        label_name = f"{prefix}{label_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert label_name not in all_labels
        label_map[label_id] = label_name
        # Register label to the global registry.
        LABELS.append((label_name, color, label_id))

    # Create a dedicated label for each group.
    for group_id, label_ids in groups.items():
        label_name = f"{prefix}{group_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert label_name not in all_labels
        for label_id in label_ids:
            label_map[label_id] = label_name
        # Build a description that is less than 100 characters.
        description = ""
        truncation_mark = ", …"
        for item_id in sorted(label_ids, key=str.casefold):
            new_item = f", {item_id}" if description else item_id
            if len(description) + len(new_item) <= 100 - len(truncation_mark):
                description += new_item
            else:
                description += truncation_mark
                break
        # Register label to the global registry.
        LABELS.append((label_name, color, description))

    # Sort label_map by their name.
    return dict(sorted(label_map.items(), key=lambda i: str.casefold(i[1])))


MANAGER_PREFIX = "📦 manager: "

MANAGER_LABEL_GROUPS: TLabelGroup = {
    "rpm-based": frozenset({"dnf", "dnf5", "yum", "zypper"}),
    "dpkg-based": frozenset({"apt", "apt-mint", "deb-get", "opkg", "pacstall"}),
    "homebrew": frozenset({"brew", "cask", "zerobrew"}),
    "npm-based": frozenset({"npm", "yarn", "yarn-berry"}),
    "pacman-based": frozenset({"pacman", "pacaur", "paru", "yay"}),
    "pip-based": frozenset({"pip", "pipx"}),
    "uv-based": frozenset({"uv", "uvx"}),
    "vscode-based": frozenset({"vscode", "vscodium"}),
}
"""Managers sharing the same ecosystem are grouped together under the same label.

Grouping is by ecosystem (the underlying packaging system), not by installation
paradigm. For example, source-based helpers like Pacstall and AUR helpers are grouped
with their ecosystem (dpkg-based and pacman-based respectively), even though they build
from source rather than fetching pre-built binaries.
"""

all_manager_label_ids = frozenset(set(pool.all_manager_ids) | {"mpm"})
"""Adds ``mpm`` as its own manager alongside all those implemented."""

# Check group IDs do not collide with original labels.
assert all_manager_label_ids.isdisjoint(MANAGER_LABEL_GROUPS.keys())

MANAGER_LABELS = generate_labels(
    all_manager_label_ids,
    MANAGER_LABEL_GROUPS,
    MANAGER_PREFIX,
    "#bfdadc",
)
"""Maps all manager IDs to their labels."""


PLATFORM_PREFIX = "🖥 platform: "

PLATFORM_LABEL_GROUPS: TLabelGroup = {}
for p_obj in MAIN_PLATFORMS:
    PLATFORM_LABEL_GROUPS[p_obj.name] = frozenset(
        p.name for p in extract_members(p_obj)
    )
"""Similar platforms are grouped together under the same label."""

all_platform_label_ids = frozenset(flatten(PLATFORM_LABEL_GROUPS.values()))

PLATFORM_LABELS = generate_labels(
    all_platform_label_ids,
    PLATFORM_LABEL_GROUPS,
    PLATFORM_PREFIX,
    "#bfd4f2",
)
"""Maps all platform names to their labels."""

# Force sorting of labels.
LABELS = sorted(LABELS, key=lambda i: str.casefold(i[0]))
