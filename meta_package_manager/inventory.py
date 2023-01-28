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

"""Introspection utilities to produce comparison matrixes between managers."""

from __future__ import annotations

from pathlib import Path

from click_extra.docs_update import replace_content
from tabulate import tabulate

from .base import Operations
from .platforms import PLATFORM_GROUPS
from .pool import pool


def operation_matrix() -> str:
    """Inspect manager and print a matrix of their current implementation."""
    # Build up the column titles.
    headers = [
        "Package manager",
        "Min. version",
    ]

    # Footnotes are used to details the OSes covered by each platform group.
    footnotes = []

    for group in PLATFORM_GROUPS:
        header_title = group.name
        # Add footnote for groups with more than one platform.
        if len(group.platforms) > 1:
            footnote_tag = f"[^{group.id}]"
            header_title += footnote_tag
            platforms_string = ", ".join(
                sorted((p.name for p in group.platforms), key=str.casefold)
            )
            footnotes.append(f"{footnote_tag}: {group.name}: {platforms_string}.")
        headers.append(header_title)

    headers.extend(f"`{op.name}`" for op in Operations)

    table = []
    for mid, m in sorted(pool.items()):
        line = [
            f"[`{mid}`]({m.homepage_url})"
            + ("" if not m.deprecated else f" [⚠️]({m.deprecation_url})"),
            f"{m.requirement}",
        ]
        for group in PLATFORM_GROUPS:
            line.append(
                group.icon if group.issubset(m.platforms) and group.icon else ""
            )
        for op in Operations:
            line.append("✓" if m.implements(op) else "")
        table.append(line)

    # Set each colomn alignment.
    alignments = ["left", "left"]
    alignments.extend(["center"] * len(PLATFORM_GROUPS))
    alignments.extend(["center"] * len(Operations))

    rendered_table = tabulate(
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
            sep = "-" * max_len
        separators.append(sep)
    header_separator = f"| {' | '.join(separators)} |"

    lines = rendered_table.splitlines()
    lines[1] = header_separator

    output = "\n".join(lines)
    if footnotes:
        output += "\n\n"
        output += "\n".join(footnotes)

    return output


def update_readme() -> None:
    """Update `readme.md` at the root of the project with the implementation table for
    each manager we support."""
    replace_content(
        Path(__file__).parent.parent.joinpath("readme.md"),
        "<!-- operation-matrix-start -->\n\n",
        "\n\n<!-- operation-matrix-end -->",
        operation_matrix(),
    )
