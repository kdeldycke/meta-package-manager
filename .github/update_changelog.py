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

"""Adds a new empty entry at the top of the changelog."""

import configparser
from pathlib import Path

# Extract current version as per bump2version.
config_file = Path(__file__).parent.joinpath("../.bumpversion.cfg").resolve()
print(f"Open {config_file}")
config = configparser.ConfigParser()
config.read_string(config_file.read_text())
current_version = config["bumpversion"]["current_version"]
print(f"Current version: {current_version}")
assert current_version

# Open changelog.
changelog_file = Path(__file__).parent.joinpath("../changelog.md").resolve()
print(f"Open {changelog_file}")
content = changelog_file.read_text()

# Extract body.
TOP_TITLE = "# Changelog\n"
assert content.startswith(TOP_TITLE)
body = content.split(TOP_TITLE, 1)[1].strip()

# Recompose full changelog with new top entry.
changelog_file.write_text(
    f"{TOP_TITLE}\n"
    f"## {{gh}}`{current_version} (unreleased) <compare/v{current_version}...main>`\n\n"
    "```{{important}}\n"
    "This version is not released yet and is under active development.\n"
    "```\n\n"
    f"{body}\n"
)
