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

Called by repomatic's ``update-docs`` job to regenerate the tables and diagrams
checked into ``readme.md`` (which GitHub renders as static markdown), plus the
pool-derived blocks of ``pyproject.toml``: the ``[project]`` keywords, the label
registry and the labeller rules.

The Sphinx-only pages need no regeneration script: ``docs/benchmark.md`` and
``docs/augmentations.md`` render their per-manager tables live at build time
through ``{python:render}`` directives calling :func:`benchmark_managers_table`
and :func:`augmentations_table`, and the ``<!-- matrix ... -->`` compatibility
blocks of ``docs/install.md`` are refreshed by ``update-docs``'s own
directive-refresh phase (``click-extra refresh-directives``).

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

import tomlkit
import yaml
from click_extra.table import TableFormat, render_table
from extra_platforms import Group, extract_members

from meta_package_manager.capabilities import (
    Operations,
    implements,
    upgrade_all_is_synthesized,
)
from meta_package_manager.labels import (
    LABELS,
    generate_content_rules,
    generate_file_rules,
)
from meta_package_manager.platforms import MAIN_PLATFORMS
from meta_package_manager.pool import pool

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARK_COMPETITORS = ("topgrade", "pacaptr", "pacapt", "sysget", "whohas")
"""Competing tools shown alongside ``mpm`` in the benchmark page, in column order."""

GITHUB_BLOB_URL = "https://github.com/kdeldycke/meta-package-manager/blob/main"
"""Base URL for linking to source files in the benchmark table.

Pinned to the ``main`` branch so the generated artifact references the same
revision the docs are built from.
"""

KEYWORDS_EXTRAS = (
    "alpine linux",
    "anaconda",
    "appimage",
    "atom",
    "chocolatey",
    "chromeos",
    "clear linux",
    "CLI",
    "cli-tools",
    "cyclonedx",
    "cygwin",
    "exherbo",
    "github cli",
    "gnu guix",
    "homebrew",
    "mac app store",
    "macos",
    "mageia",
    "meta-package-manager",
    "netbsd",
    "nixpkgs",
    "node",
    "openbsd",
    "package",
    "package manager",
    "package url",
    "package-manager-cli",
    "packagekit",
    "paludis",
    "php composer",
    "pkgsrc",
    "plugin",
    "portage",
    "powershell",
    "powershell-gallery",
    "psresourceget",
    "purl",
    "pwsh",
    "ruby",
    "ruby-gem",
    "rust",
    "sbom",
    "slackware",
    "slitaz",
    "solaris",
    "source mage",
    "spdx",
    "svr4",
    "swiftbar",
    "swiftbar-plugin",
    "tex live",
    "visual studio code",
    "void linux",
    "xbar",
    "xbar-plugin",
    "zb",
)
"""Curated PyPI keywords beyond the manager IDs themselves.

Ecosystem names, platform names and generic discovery terms. The manager IDs come
for free from the pool: :func:`update_keywords` merges both sets into
``pyproject.toml``. When a new manager brings a well-known ecosystem name that
differs from its ID (like ``gh-ext`` and ``github cli``), add the alias here.
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
        "Cooldown",
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
            "✓" if m.supports_cooldown else "",
        ]
        line.extend(
            p_obj.icon if m.platforms.issuperset(extract_members(p_obj)) else ""
            for p_obj in MAIN_PLATFORMS
        )
        line.extend("✓" if implements(m, op) else "" for op in Operations)
        table.append(line)

    # Set each column alignment.
    alignments = ["left", "left", "center"]
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
    the class declaration. Used by the benchmark page to back each ``✅`` in
    the ``mpm`` column with a link to its implementation.
    """
    manager = pool[manager_id]
    # A config-defined manager (built from a shipped TOML file, not a class body) has no
    # Python source line to point at; link to its bundled definition file instead.
    source = getattr(manager, "definition_source", None)
    if source:
        return f"{GITHUB_BLOB_URL}/{source}"
    cls = type(manager)
    src = Path(inspect.getsourcefile(cls)).resolve()  # type: ignore[arg-type]
    rel = src.relative_to(PROJECT_ROOT)
    _, lineno = inspect.getsourcelines(cls)
    return f"{GITHUB_BLOB_URL}/{rel.as_posix()}#L{lineno}"


def benchmark_managers_table() -> str:
    """Produce the ``Package manager support`` table of the benchmark page.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    ``docs/benchmark.md``, so the table (and its source-line anchors) always
    matches the code being documented without a checked-in copy.

    The ``mpm`` column is auto-derived from the live pool: each implemented
    manager renders as ``[✅](source_url)``, linking to the class definition
    that proves the support. Competitor columns are filled from
    ``docs/benchmark.yaml``, which only encodes what the *other* tools
    support.

    Each manager identifier in the first column is rendered as a link to its
    homepage when one is known: from the mpm class's ``homepage_url`` for
    implemented managers, or from the YAML's ``homepages`` mapping for
    competitor-only managers. IDs without any known URL render as plain
    ``\\`code\\```.

    Support cells are normally ``✅``, but render as ``[🟡](url)`` when the
    ``(manager_id, competitor)`` pair is listed in the YAML's
    ``coarse_support`` map, with the URL pointing to the maintainer's own
    acknowledgement of the bundling. ``🟡`` means the competitor can only
    reach this manager through a coarser umbrella step (topgrade's
    ``--only shell`` or ``--only vim``), never in isolation. Refused
    managers (from the ``refused`` map) render as ``[❌](url)`` where the
    URL is the specific decision or refusal that documents the declined
    support.

    Manager rows are the sorted union of pool IDs and YAML keys, so a new
    entry on either side appears in the table without manual edits.
    """
    yaml_path = PROJECT_ROOT / "docs" / "benchmark.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="UTF-8"))
    competitor_data: dict[str, list[str]] = data["managers"]
    homepages: dict[str, str] = data.get("homepages", {})
    coarse_support: dict[str, dict[str, str]] = data.get("coarse_support", {})
    refused: dict[str, dict[str, str]] = data.get("refused", {})

    pool_ids = set(pool.all_manager_ids)
    all_ids = sorted(pool_ids | competitor_data.keys() | refused.keys())

    headers = ["Manager", "`mpm`"]
    headers.extend(f"`{name}`[^{name}]" for name in BENCHMARK_COMPETITORS)

    table = []
    for mid in all_ids:
        if mid in pool_ids:
            url: str | None = pool[mid].homepage_url
        else:
            url = homepages.get(mid)
        label = f"[`{mid}`]({url})" if url else f"`{mid}`"
        row = [label]
        if mid in pool_ids:
            row.append(f"[✅]({manager_source_url(mid)})")
        else:
            row.append("")
        flags = set(competitor_data.get(mid, []))
        coarse_map = coarse_support.get(mid, {})
        refused_map = refused.get(mid, {})
        cells: list[str] = []
        for name in BENCHMARK_COMPETITORS:
            if name in flags:
                if name in coarse_map:
                    cells.append(f"[🟡]({coarse_map[name]})")
                else:
                    cells.append("✅")
            elif name in refused_map:
                cells.append(f"[❌]({refused_map[name]})")
            else:
                cells.append("")
        row.extend(cells)
        table.append(row)

    alignments = ["left"] + ["center"] * (1 + len(BENCHMARK_COMPETITORS))

    return render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )


def augmentations_table() -> str:
    """Produce the per-manager table of the augmentations page.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    ``docs/augmentations.md``, so the table always matches the code being
    documented without a checked-in copy.

    Each ``✅`` marks a capability ``mpm`` synthesizes for a manager that lacks
    it natively, straight from the capability introspection helpers:

    - *Full* ``upgrade --all``: the manager only reaches the operation through
      the one-by-one fallback
      (:func:`meta_package_manager.capabilities.upgrade_all_is_synthesized`).
    - *Exact search* and *Extended search*: the manager's native search cannot
      filter that way, so ``mpm`` refilters the raw results itself (the
      ``exact_support``/``extended_support`` flags set by
      :func:`meta_package_manager.capabilities.search_capabilities` and the
      config-defined manager builder).

    Managers needing no backfill at all are left out of the table.
    """
    table = []
    for mid, manager in sorted(pool.items()):
        upgrade_all = upgrade_all_is_synthesized(manager)
        search_func = getattr(type(manager), "search", None)
        has_search = implements(manager, Operations.search)
        exact = has_search and not getattr(search_func, "exact_support", True)
        extended = has_search and not getattr(search_func, "extended_support", True)
        if not (upgrade_all or exact or extended):
            continue
        table.append([
            f"`{mid}`",
            "✅" if upgrade_all else "",
            "✅" if exact else "",
            "✅" if extended else "",
        ])

    return render_table(
        table,
        headers=["Manager", "Full `upgrade --all`", "Exact search", "Extended search"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "center", "center", "center"],
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

    orig_content = filepath.read_text(encoding="UTF-8")

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
        encoding="UTF-8",
    )


def _string_array(values: tuple[str, ...], multiline: bool = False):
    """Render strings as a ``tomlkit`` array, one item per line when asked or long.

    ``tomlkit``'s own ``multiline()`` hard-codes a 4-space indent; re-parsing an
    explicitly rendered body keeps the 2-space indent used across
    ``pyproject.toml``.
    """
    array = tomlkit.array()
    array.extend(values)
    if not multiline and len(array.as_string()) <= 76:
        return array
    body = "".join(f"  {tomlkit.item(value).as_string()},\n" for value in values)
    return tomlkit.array(f"[\n{body}]")


def _rules_aot(rules: list[tuple[str, tuple[str, ...]]], field: str):
    """Render labeller rules as a ``tomlkit`` array-of-tables.

    Each rule becomes a ``{label, <field>}`` table. The pattern array switches to
    one-item-per-line when its inline form would run long.
    """
    aot = tomlkit.aot()
    for label, values in rules:
        entry = tomlkit.table()
        entry["label"] = label
        entry[field] = _string_array(values)
        aot.append(entry)
    return aot


def update_labels() -> None:
    """Sync the label registry and labeller rules into ``pyproject.toml``.

    Regenerates the three ``[tool.repomatic.labels.*]`` arrays from
    :mod:`meta_package_manager.labels`: ``extra`` (from
    :data:`~meta_package_manager.labels.LABELS`), ``content-rules`` and
    ``file-rules`` (from the pool-derived rule generators). repomatic's
    ``sync-labels`` and labeller jobs read these inline definitions at run time.

    .. note::
        The edit is done with ``tomlkit`` round-trip so the rest of
        ``pyproject.toml`` (comments, key order, formatting) is preserved: only
        the three label arrays are regenerated. The per-entry layout matches what
        ``pyproject-fmt`` emits, so the result survives the autofix formatting
        pass without churn.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))
    labels_table = doc["tool"]["repomatic"]["labels"]

    extra = tomlkit.aot()
    for name, color, description in LABELS:
        entry = tomlkit.table()
        entry["name"] = name
        # labelmaker/repomatic expect the bare hex color, without leading '#'.
        entry["color"] = color.lstrip("#")
        entry["description"] = description
        extra.append(entry)

    arrays = {
        "content-rules": _rules_aot(generate_content_rules(), "patterns"),
        "extra": extra,
        "file-rules": _rules_aot(generate_file_rules(), "any-glob-to-any-file"),
    }
    for key, aot in arrays.items():
        labels_table[key] = aot
        # Separate the last entry from the following table with one blank line.
        last_field = list(aot[-1].keys())[-1]
        aot[-1][last_field].trivia.trail = "\n\n"

    content = tomlkit.dumps(doc)
    for key in arrays:
        # tomlkit prefixes each inserted array-of-tables with two blank lines;
        # collapse the section's leading separator to a single blank line.
        content = content.replace(
            f"\n\n\n[[tool.repomatic.labels.{key}]]",
            f"\n\n[[tool.repomatic.labels.{key}]]",
            1,
        )
    pyproject.write_text(content, encoding="UTF-8")


def update_keywords() -> None:
    """Sync the ``[project]`` keywords of ``pyproject.toml``.

    The keyword set is the pool's manager IDs merged with the curated
    :data:`KEYWORDS_EXTRAS`, so a new manager advertises itself on PyPI without
    a hand edit. Same ``tomlkit`` round-trip as :func:`update_labels`.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))

    doc["project"]["keywords"] = _string_array(
        tuple(
            sorted(set(KEYWORDS_EXTRAS) | set(pool.all_manager_ids), key=str.casefold),
        ),
        multiline=True,
    )

    pyproject.write_text(tomlkit.dumps(doc), encoding="UTF-8")


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
    orig_content = readme.read_text(encoding="UTF-8")
    pre_content, rest = orig_content.split(start_tag, 1)
    _, post_content = rest.split(end_tag, 1)
    readme.write_text(
        f"{pre_content}{start_tag}{footnotes}{end_tag}{post_content}",
        encoding="UTF-8",
    )


if __name__ == "__main__":
    update_keywords()
    update_labels()
    update_readme()
