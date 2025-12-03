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
    ANY_WINDOWS,
    BSD_WITHOUT_MACOS,
    LINUX_LIKE,
    MACOS,
    UNIX_WITHOUT_MACOS,
    Group,
)
from tabulate import tabulate

from .base import Operations
from .pool import pool

TYPE_CHECKING = False
if TYPE_CHECKING:
    from extra_platforms import Platform


MAIN_PLATFORMS: tuple[Group | Platform, ...] = (
    BSD_WITHOUT_MACOS.copy(id="bsd", name="BSD"),
    LINUX_LIKE.copy(id="linux", name="Linux", icon="🐧"),
    MACOS,
    UNIX_WITHOUT_MACOS.copy(
        id="unix",
        name="Unix",
        platforms=tuple(UNIX_WITHOUT_MACOS - BSD_WITHOUT_MACOS - LINUX_LIKE),
    ),
    ANY_WINDOWS.copy(id="windows", name="Windows"),
)
"""Top-level classification of platforms.

This is the local reference used to classify the execution targets of ``mpm``.

Each entry of this list will have its own dedicated column in the matrix. This list is
manually maintained with tweaked IDs and names to minimize the matrix verbosity and
make it readable both in CLI and documentation.

The order of this list determine the order of the resulting columns.
"""


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


def operation_matrix() -> tuple[str, str]:
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
            line.append(
                p_obj.icon
                if m.platforms.issuperset(Group._extract_platforms(p_obj))
                else ""
            )
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

    return "\n".join(lines), "\n\n".join(footnotes)


def update_readme() -> None:
    """Update ``readme.md`` with implementation table for each manager we support."""

    readme = Path(__file__).parent.parent.joinpath("readme.md")

    replace_content(
        readme,
        managers_sankey(),
        "<!-- managers-sankey-start -->\n\n",
        "\n\n<!-- managers-sankey-end -->",
    )

    matrix, footnotes = operation_matrix()
    replace_content(
        readme,
        matrix,
        "<!-- operation-matrix-start -->\n\n",
        "\n\n<!-- operation-matrix-end -->",
    )
    replace_content(
        readme,
        footnotes,
        "<!-- operation-footnotes-start -->\n\n",
        # mdformat-footnote is stripping all HTML comments after footnotes:
        # https://github.com/executablebooks/mdformat-footnote/issues/11
        # So we protect the content to be replaced with an end tag that we put at the
        # tail of the last footnote line, without any carriage return.
        "<!-- operation-footnotes-end -->\n",
    )
