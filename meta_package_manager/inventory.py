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
"""Introspection utilities to produce feature inventory of all managers."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click_extra.docs_update import replace_content
from extra_platforms import (
    BSD,
    BSD_WITHOUT_MACOS,
    LINUX_LIKE,
    MACOS,
    UNIX,
    WINDOWS,
    Group,
    Platform,
)
from tabulate import tabulate

from .base import Operations
from .pool import pool


def managers_sankey() -> str:
    """Produce a sankey diagram to map ``mpm`` to all its supported managers."""
    table = []
    for mid, m in sorted(pool.items()):
        line = f"Meta Package Manager,{mid},1"
        table.append(line)

    output = dedent("""\
        ```mermaid
        ---
        config: {"sankey": {"showValues": false, "width": 800, "height": 400}}
        ---
        sankey-beta\n
        """)
    output += "\n".join(table)
    output += "\n```"
    return output


UNIX_WITHOUT_BSD_LINUX = Group(
    "unix_without_bsd_linux",
    "Any Unix but BSDs and Linux-like",
    "⨂",
    # UNIX - BSD - LINUX_LIKE
    tuple(p for p in UNIX if p not in BSD and p not in LINUX_LIKE),
)
"""All Unix platforms, without macOS or any Linux-like.

..todo:
    Contribute to extra-platforms?
"""


MAIN_PLATFORMS: tuple[Group | Platform, ...] = (
    BSD_WITHOUT_MACOS,
    LINUX_LIKE,
    MACOS,
    UNIX_WITHOUT_BSD_LINUX,
    WINDOWS,
)
"""Groups or platforms that will have their own dedicated column in the matrix.

This list is manually maintained with the objective of minimizing the matrix verbosity
and make it readable.

The order of this list determine the order of the resulting columns.
"""


def operation_matrix() -> str:
    """Produce a table of managers' metadata and supported operations."""
    # Build up the column titles.
    headers = [
        "Package manager",
        "Min. version",
    ]

    # Footnotes are used to details the OSes covered by each platform group.
    footnotes = []

    for p_obj in MAIN_PLATFORMS:
        header_title = p_obj.name
        # Add footnote for groups with more than one platform.
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            footnote_tag = f"[^{p_obj.id}]"
            header_title += footnote_tag
            platforms_string = ", ".join(
                sorted((p.name for p in p_obj.platforms), key=str.casefold),
            )
            footnotes.append(f"{footnote_tag}: {p_obj.name}: {platforms_string}.")
        headers.append(header_title)

    headers.extend(f"`{op.name}`" for op in Operations)

    table = []
    for mid, m in sorted(pool.items()):
        line = [
            f"[`{mid}`]({m.homepage_url})"
            + ("" if not m.deprecated else f" [⚠️]({m.deprecation_url})"),
            f"{m.requirement}",
        ]
        for p_obj in MAIN_PLATFORMS:
            if (isinstance(p_obj, Platform) and p_obj in m.platforms) or (
                isinstance(p_obj, Group) and p_obj.issubset(m.platforms)
            ):
                line.append(p_obj.icon)
            else:
                line.append("")
        for op in Operations:
            line.append("✓" if m.implements(op) else "")
        table.append(line)

    # Set each column alignment.
    alignments = ["left", "left"]
    alignments.extend(["center"] * len(MAIN_PLATFORMS))
    alignments.extend(["center"] * len(Operations))

    rendered_table = tabulate(
        table,
        headers=headers,
        tablefmt="github",
        colalign=alignments,
        disable_numparse=True,
    )

    # Manually produce Markdown alignment hints. This has been proposed upstream at:
    # https://github.com/astanin/python-tabulate/pull/261
    # https://github.com/astanin/python-tabulate/issues/53
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
        output += "\n\n".join(footnotes)

    return output


def update_readme() -> None:
    """Update ``readme.md`` with implementation table for each manager we support."""

    readme = Path(__file__).parent.parent.joinpath("readme.md")

    replace_content(
        readme,
        "<!-- managers-sankey-start -->\n",
        "\n<!-- managers-sankey-end -->",
        managers_sankey(),
    )

    replace_content(
        readme,
        "<!-- operation-matrix-start -->\n\n",
        "\n\n<!-- operation-matrix-end -->",
        operation_matrix(),
    )
