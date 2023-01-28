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

""" Utilities to manage GitHub labels to use in issues and PR management.
"""

from __future__ import annotations

import json
from pathlib import Path

from meta_package_manager.labels import LABELS


def write_labels():
    """Write down labels into JSON file."""
    json_file = Path(__file__).parent.joinpath("../.github/labels-extra.json").resolve()

    # Debug messages.
    for label_name, _, _ in LABELS:
        print(f"Generated label: {label_name}")
    print(f"{len(LABELS)} labels generated.")
    print(f"Saving to: {json_file}")

    # Save to json definition file.
    label_defs = [
        dict(zip(["name", "color", "description"], label)) for label in LABELS
    ]
    json_file.write_text(
        json.dumps(
            label_defs,
            indent=2,
            separators=(",", ": "),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    write_labels()
