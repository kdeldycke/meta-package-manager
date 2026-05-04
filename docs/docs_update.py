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
"""Dynamic documentation content generation.

Called by repomatic's ``update-docs`` job to regenerate tables, diagrams and
other dynamic content in ``readme.md``.

.. warning::
    The generated Mermaid syntax targets the version bundled with
    ``sphinxcontrib-mermaid``, currently ``11.12.1``. See the hard-coded
    ``MERMAID_VERSION`` constant in `sphinxcontrib-mermaid's source
    <https://github.com/mgaitan/sphinxcontrib-mermaid/blob/master/sphinxcontrib/mermaid/__init__.py>`_.
    Avoid using Mermaid features introduced after that version.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from textwrap import dedent

import yaml
from click_extra.table import TableFormat, render_table
from extra_platforms import Group, extract_members

from meta_package_manager.base import Operations
from meta_package_manager.inventory import MAIN_PLATFORMS
from meta_package_manager.labels import LABELS
from meta_package_manager.pool import pool

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARK_COMPETITORS = ("topgrade", "pacaptr", "pacapt", "sysget", "whohas")
"""Competing tools shown alongside ``mpm`` in the benchmark page, in column order."""

GITHUB_BLOB_URL = "https://github.com/kdeldycke/meta-package-manager/blob/main"
"""Base URL for linking to source files in the benchmark table.

Pinned to the ``main`` branch so the generated artifact references the same
revision the docs are built from.
"""


def managers_sankey() -> str:
    """Produce a sankey diagram to map ``mpm`` to all its supported managers.

    .. warning::
        Output must stay compatible with the Mermaid version bundled in
        ``sphinxcontrib-mermaid``. See module docstring for details.
    """
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
        "Version",
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
                sorted(
                    (
                        p.name
                        for p in p_obj.members.values()  # type: ignore[attr-defined]
                    ),
                    key=str.casefold,
                ),
            )
            footnotes.append(f"{footnote_tag}: {p_obj.name}: {platforms_string}.")
        headers.append(header_title)

    headers.extend(f"`{op.name}`" for op in Operations)

    table = []
    for mid, m in sorted(pool.items()):
        line = [
            f"[`{mid}`]({m.homepage_url})"
            + ("" if not m.deprecated else f" [⚠️]({m.deprecation_url})"),
            (m.requirement or "").replace("<", r"\<"),
        ]
        line.extend(
            p_obj.icon if m.platforms.issuperset(extract_members(p_obj)) else ""
            for p_obj in MAIN_PLATFORMS
        )
        line.extend("✓" if m.implements(op) else "" for op in Operations)
        table.append(line)

    # Set each column alignment.
    alignments = ["left", "left"]
    alignments.extend(["center"] * len(MAIN_PLATFORMS))
    alignments.extend(["center"] * len(Operations))

    rendered_table = render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )

    return rendered_table, "\n\n".join(footnotes)


def manager_source_url(manager_id: str) -> str:
    """Return a GitHub URL pointing to the class definition of a manager.

    Resolves the manager class via :py:data:`meta_package_manager.pool.pool`,
    then uses :py:mod:`inspect` to derive the source file and line number of
    the class declaration. Used by the benchmark page to back each ``✓`` in
    the ``mpm`` column with a link to its implementation.
    """
    cls = type(pool[manager_id])
    src = Path(inspect.getsourcefile(cls)).resolve()  # type: ignore[arg-type]
    rel = src.relative_to(PROJECT_ROOT)
    _, lineno = inspect.getsourcelines(cls)
    return f"{GITHUB_BLOB_URL}/{rel.as_posix()}#L{lineno}"


def benchmark_managers_table() -> str:
    """Produce the ``Package manager support`` table of the benchmark page.

    The ``mpm`` column is auto-derived from the live pool: each implemented
    manager renders as ``[✓](source_url)``, linking to the class definition
    that proves the support. Competitor columns are filled from
    ``docs/benchmark.yaml``, which only encodes what the *other* tools
    support.

    Manager rows are the sorted union of pool IDs and YAML keys, so a new
    entry on either side appears in the table without manual edits.
    """
    yaml_path = PROJECT_ROOT / "docs" / "benchmark.yaml"
    competitor_data: dict[str, list[str]] = yaml.safe_load(yaml_path.read_text())[
        "managers"
    ]

    pool_ids = set(pool.all_manager_ids)
    all_ids = sorted(pool_ids | competitor_data.keys())

    headers = ["Manager", "`mpm`"]
    headers.extend(
        f"`{name}`[^{i}]" for i, name in enumerate(BENCHMARK_COMPETITORS, start=1)
    )

    table = []
    for mid in all_ids:
        row = [f"`{mid}`"]
        if mid in pool_ids:
            row.append(f"[✓]({manager_source_url(mid)})")
        else:
            row.append("")
        flags = set(competitor_data.get(mid, []))
        row.extend("✓" if name in flags else "" for name in BENCHMARK_COMPETITORS)
        table.append(row)

    alignments = ["left"] + ["center"] * (1 + len(BENCHMARK_COMPETITORS))

    return render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )


def replace_content(
    filepath: Path,
    new_content: str,
    start_tag: str,
    end_tag: str | None = None,
) -> None:
    """Replace in a file the content between start and end tags.

    The ``new_content`` payload is wrapped with a blank line on both sides so
    the resulting region is format-stable through ``mdformat``. ``mdformat``
    treats the surrounding ``<!-- ... -->`` markers as block-level HTML and
    inserts blank lines around them on every pass: emitting them up front
    avoids a generator/formatter ping-pong on every CI run.
    """
    filepath = filepath.resolve()
    assert filepath.exists(), f"File {filepath} does not exist."
    assert filepath.is_file(), f"File {filepath} is not a file."

    orig_content = filepath.read_text()

    assert start_tag in orig_content, (
        f"Start tag {start_tag!r} not found in {filepath}."
    )
    pre_content, table_start = orig_content.split(start_tag, 1)

    if end_tag:
        _, post_content = table_start.split(end_tag, 1)
    else:
        end_tag = ""
        post_content = ""

    wrapped = f"\n\n{new_content.strip()}\n\n" if new_content.strip() else "\n\n"
    filepath.write_text(
        f"{pre_content}{start_tag}{wrapped}{end_tag}{post_content}",
    )


def write_labels() -> None:
    """Write extra labels as a labelmaker TOML file for repomatic's ``sync-labels``."""
    labels_dir = PROJECT_ROOT / "extra-labels"
    labels_dir.mkdir(exist_ok=True)
    toml_file = labels_dir / "mpm.toml"

    entries = []
    for label_name, color, description in LABELS:
        # Strip leading '#' from color to match labelmaker/repomatic convention.
        color = color.lstrip("#")
        # Escape any backslashes and double-quotes in TOML strings.
        name_escaped = label_name.replace("\\", "\\\\").replace('"', '\\"')
        desc_escaped = description.replace("\\", "\\\\").replace('"', '\\"')
        entries.append(
            f"[[profiles.default.labels]]\n"
            f'name = "{name_escaped}"\n'
            f'color = "{color}"\n'
            f'description = "{desc_escaped}"'
        )

    toml_file.write_text("\n\n".join(entries) + "\n")


def update_readme() -> None:
    """Update ``readme.md`` with implementation table for each manager we support."""
    readme = PROJECT_ROOT / "readme.md"

    replace_content(
        readme,
        managers_sankey(),
        "<!-- managers-sankey-start -->",
        "<!-- managers-sankey-end -->",
    )

    matrix, footnotes = operation_matrix()
    replace_content(
        readme,
        matrix,
        "<!-- operation-matrix-start -->",
        "<!-- operation-matrix-end -->",
    )
    # mdformat-footnote strips HTML comments after footnote definitions
    # (https://github.com/executablebooks/mdformat-footnote/issues/11), so the
    # end tag has to be wedged against the tail of the last footnote line (no
    # leading newline) to survive a format pass. That breaks the trailing-blank
    # convention of replace_content(), so the footnote section is written
    # inline.
    start_tag = "<!-- operation-footnotes-start -->\n\n"
    end_tag = "<!-- operation-footnotes-end -->\n"
    orig_content = readme.read_text()
    pre_content, rest = orig_content.split(start_tag, 1)
    _, post_content = rest.split(end_tag, 1)
    readme.write_text(f"{pre_content}{start_tag}{footnotes}{end_tag}{post_content}")


def update_benchmark() -> None:
    """Refresh the auto-generated table in ``docs/benchmark.md``."""
    benchmark = PROJECT_ROOT / "docs" / "benchmark.md"
    replace_content(
        benchmark,
        benchmark_managers_table(),
        "<!-- benchmark-managers-start -->",
        "<!-- benchmark-managers-end -->",
    )


if __name__ == "__main__":
    write_labels()
    update_readme()
    update_benchmark()
