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

"""Introspection utilities to produce comparison matrixes between managers."""

from pathlib import Path

from click_extra.platform import LINUX, MACOS, WINDOWS
from tabulate import tabulate

from .pool import OPERATION_IDS, implements, pool


def manager_operations():
    """Inspect manager and print a matrix of their current implementation."""
    # Build up the column titles.
    headers = [
        "Package manager",
        "Min. version",
        "Linux",
        "macOS",
        "Windows",
    ]
    headers.extend(f"`{oid}`" for oid in OPERATION_IDS)

    table = []
    for mid, m in sorted(pool.items()):
        #import pdb; pdb.set_trace()
        line = [
            f"[`{mid}`]({m.homepage_url})",
            f"{m.requirement}",
            "🐧" if LINUX in m.platforms else '',
            "🍎" if MACOS in m.platforms else '',
            "🪟" if WINDOWS in m.platforms else '',
        ]
        for operation_id in OPERATION_IDS:
            line.append("✓" if implements(m, operation_id) else "")
        table.append(line)

    # Set each colomn alignment.
    alignments = [
        "left","left",
        "center","center","center"
    ]
    alignments.extend(["center"] * len(OPERATION_IDS))

    output = tabulate(
        table,
        headers=headers,
        tablefmt="github",
        colalign=alignments,
        disable_numparse=True,
    )

    # Manually produce Markdown alignment hints.
    # See: https://github.com/astanin/python-tabulate/issues/53
    separators = []
    for col_index, header in enumerate(headers):
        cells = [line[col_index] for line in table] + [header]
        max_len = max(len(c) for c in cells)
        align = alignments[col_index]
        if align == "center":
            sep = f":{'-' * (max_len - 2)}:"
        elif align == "right":
            sep = f"{'-' * (max_len - 1)}:"
        else:
            sep = '-' * max_len
        separators.append(sep)
    header_separator = f"| {' | '.join(separators)} |"

    lines = output.splitlines()
    lines[1] = header_separator

    return '\n'.join(lines)


def update_readme():
    """Update `readme.md` at the root of the project with the implementation table for each manager we support."""
    # Load-up `readme.md`.
    readme = Path(__file__).parent.parent.joinpath("readme.md").resolve()
    content = readme.read_text()

    # Extract pre- and post-content surounding the section we're trying to update.
    section_title = "## Supported package managers and operations"
    pre_content, section_start = content.split(section_title, 1)
    post_content = section_start.split('##', 1)[1]

    # Reconstruct the readme with our updated section.
    readme.write_text(
        f"{pre_content}"
        f"{section_title}\n\n"
        f"{manager_operations()}\n\n"
        f"##{post_content}"
    )