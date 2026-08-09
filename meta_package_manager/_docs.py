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

"""Documentation generators for pool-derived tables, diagrams and manager pages.

Private, docs-build-only helpers imported by the `{python:render}` directives in
`docs/*.md` and the committed `:mirror:` regions of `docs/benchmark.md` and
`docs/augmentations.md`. The leading-underscore name keeps them out of the public
API; shipping them with the package lets the render and `refresh-directives`
machinery import `meta_package_manager._docs` with no `sys.path` juggling. Never
imported from `__init__`, so `import meta_package_manager` stays dependency-light.

The file-writing orchestration (readme, pyproject, the `docs/managers/` stub set)
lives in `docs/docs_update.py`.

```{warning}
The generated Mermaid syntax targets the version bundled with
`sphinxcontrib-mermaid`, currently `11.12.1`. Avoid features introduced later.
```
"""

from __future__ import annotations

import csv
import inspect
import re
import sys
from functools import cache
from itertools import groupby
from pathlib import Path
from textwrap import dedent
from typing import NamedTuple

import yaml
from click_extra.table import TableFormat, render_table
from extra_platforms import Group, extract_members

from meta_package_manager.capabilities import (
    Operations,
    cleanup_orphan_is_synthesized,
    exact_search_is_synthesized,
    extended_search_is_synthesized,
    implements,
    implements_method,
    upgrade_all_is_synthesized,
)
from meta_package_manager.docstring_corpus import (
    block_commands,
    block_language,
    class_display_blocks,
    literal_blocks,
    version_trace,
)
from meta_package_manager.platforms import MAIN_PLATFORMS
from meta_package_manager.pool import pool
from meta_package_manager.specifier import PURL_MAP

# Version-gated TOML reader, following the same pattern as `tests/conftest.py`.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARK_COMPETITORS = ("topgrade", "pacaptr")
"""Competing tools shown alongside `mpm` in the benchmark page, in column order."""

DOCS_SITE_URL = "https://kdeldycke.github.io/meta-package-manager"
"""Base URL of the published documentation site.

Used by {func}`operation_matrix` to link each manager ID of `readme.md` to its
documentation page: the readme renders on GitHub and PyPI, where relative Sphinx
links cannot resolve, so the links must be absolute.
"""

EMPTY_CELLS = frozenset({"", "—", "➖"})
"""Hand-curated table cells carrying no reusable content.

The tables of `docs/cooldown.md` are reused verbatim on the per-manager pages
({func}`manager_cooldown`). A cell holding nothing, an em dash or a bare
not-applicable marker has nothing to say there and is dropped rather than
rendered as an empty fact.
"""

LOGO_DIR = PROJECT_ROOT / "docs" / "assets" / "managers"
"""Vendored brand marks and their `logos.yaml` manifest.

Wholly owned by `docs/logos_update.py`, which is run by hand: the artwork
is committed so a docs build stays hermetic and never depends on an upstream icon
set still serving the same files.
"""

MIN_LOGO_CONTRAST = 3.0
"""Contrast ratio below which a brand color reads as pale on the light theme.

Advisory only, reported by `docs/logos_update.py` and never enforced at render
time. Gating on it was tried and dropped: [WCAG 2.2 exempts logotypes from
contrast requirements](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
precisely because a brand's own color is not the author's to correct, and the
guard was repainting recognisable marks (Fedora's blue, Homebrew's amber) a flat
black. Marks keep their color on the light theme whatever this says; the dark
theme still falls back to `currentColor`, which is about legibility against a
near-black background rather than about contrast ratios.
"""

FACT_SEPARATOR = "\u00a0· "
"""Separator between the repeated values of an infobox row.

A middle dot rather than a comma: the values are code spans whose own boxes
already read as separate tokens, and a comma between them adds a mark the eye
has to skip.

The leading space is a non-breaking one, so the dot cannot start a line on its
own. The box is narrow enough to wrap most rows, and a separator orphaned at the
head of a line reads as a bullet for the value that follows it. Breaking after
the dot is fine, hence the ordinary space on that side.
"""

GITHUB_BLOB_URL = "https://github.com/kdeldycke/meta-package-manager/blob/main"
"""Base URL for linking to source files in the benchmark table.

Pinned to the `main` branch so the generated artifact references the same
revision the docs are built from.
"""

MANAGER_SECTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "manager_intro"),
    ("What `mpm` adds to `{manager_id}`", "manager_augments"),
    ("Your `{manager_id}` commands, in `mpm`", "manager_rosetta"),
    ("Operations", "manager_operations"),
    ("Selecting and configuring `{manager_id}`", "manager_selection"),
    ("Recipes", "manager_recipes"),
    ("How `mpm` drives `{manager_id}`", "manager_cli"),
    ("Privilege escalation", "manager_sudo"),
    ("Cooldown", "manager_cooldown"),
    ("Reference traces", "manager_traces"),
    ("Changelog", "manager_changelog"),
)
"""Layout of a per-manager documentation page: section title, generator function.

Single source of truth for {func}`manager_page_stub` and the structural tests.
Sections lead with the `mpm` pitch (what it adds to the native tool) and its
usage, then document `mpm`'s preconceptions about the tool (its invocation,
then the captured traces backing the parsers), and close on the release
history of that support. A section whose generator produces nothing for a
given manager is omitted from its stub.

Each title is a `str.format` template receiving the manager ID, so a heading
can name its manager; a title with no replacement field renders unchanged.

The headings live in the committed stubs, never in the generated content: the
``{python:render}`` directive nested-parses its output into the surrounding
document, where MyST headings rely on fragile section reparenting. Every
generator listed here must therefore emit heading-free MyST.
"""


def managers_sankey() -> str:
    """Produce a sankey diagram to map `mpm` to all its supported managers.

    ```{warning}
    Output must stay compatible with the Mermaid version bundled in
    `sphinxcontrib-mermaid`. See module docstring for details.
    ```
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
    """Produce a table of managers' metadata and supported operations.

    Each manager ID links to its dedicated documentation page (absolute URL:
    the readme renders on GitHub and PyPI, where relative Sphinx links cannot
    resolve). Home pages are listed on the manager pages themselves.
    """
    # Build up the column titles.
    headers = [
        "Package manager",
        "Version",
        "Cooldown",
    ]

    # Footnotes are used to details the OSes covered by each platform group.
    footnotes = []

    # One platform column, with the legend its cells need set below the table: a
    # column per platform labelled each icon, a single one cannot. The footnote
    # naming a group's members hangs off the icon it belongs to, which is also
    # what keeps those definitions referenced instead of orphaned.
    legend = []
    for p_obj in MAIN_PLATFORMS:
        entry = f"{p_obj.icon} {p_obj.name}"
        # Add footnote for groups with more than one platform.
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            footnote_tag = f"[^{p_obj.id}]"
            entry += footnote_tag
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
        legend.append(entry)
    headers.append("Platforms")

    headers.extend(f"`{op.name}`" for op in Operations)

    table = []
    for mid, m in sorted(pool.items()):
        line = [
            f"[`{mid}`]({DOCS_SITE_URL}/managers/{mid}.html)"
            + (
                ""
                if not m.unmaintained
                else f" [⚠️]({DOCS_SITE_URL}/managers/{mid}.html)"
            ),
            _format_requirement(m.requirement or "").replace("<", r"\<"),
            "✓" if m.supports_cooldown else "",
        ]
        line.append(
            " ".join(
                p_obj.icon
                for p_obj in MAIN_PLATFORMS
                if m.platforms.issuperset(extract_members(p_obj))
            ),
        )
        line.extend("✓" if implements(m, op) else "" for op in Operations)
        table.append(line)

    # Set each column alignment.
    alignments = ["left", "left", "center", "center"]
    alignments.extend(["center"] * len(Operations))

    rendered_table = render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )

    # The legend decodes the Platforms column, so it travels with the table
    # rather than with the footnote definitions parked at the end of the readme.
    return (
        f"{rendered_table}\nPlatforms: {FACT_SEPARATOR.join(legend)}",
        "\n\n".join(footnotes),
    )


def _format_requirement(requirement: str) -> str:
    """Render a version specifier for reading: `>=2.10.0` becomes `>= 2.10`.

    Two cosmetic passes: the comparison operator is split from the version it
    applies to, and trailing zero components are dropped, since `2.10.0` and
    `2.10` pin the same floor while only one of them is worth reading.

    Shared by the readme's operation matrix and the manager infoboxes, so both
    render a requirement the same way. Display only: what the runtime parses is
    the manager's own
    {attr}`~meta_package_manager.manager.PackageManager.requirement`, which keeps
    the exact upstream release it was verified against.
    """

    def trim(match: re.Match) -> str:
        components = match.group(0).split(".")
        while len(components) > 1 and components[-1] == "0":
            components.pop()
        return ".".join(components)

    trimmed = re.sub(r"\d+(?:\.\d+)*", trim, requirement)
    # Split the comparison operator from the version it applies to, then give a
    # comma-joined range room to breathe.
    spaced = re.sub(r"(?<=[<>=!~])(?=[\d])", " ", trimmed)
    return re.sub(r",\s*", ", ", spaced)


def manager_source_url(manager_id: str) -> str:
    """Return a GitHub URL pointing to the class definition of a manager.

    Resolves the manager class via {data}`meta_package_manager.pool.pool`,
    then uses {mod}`inspect` to derive the source file and line number of
    the class declaration. Used by the benchmark page to back each `✅` in
    the `mpm` column with a link to its implementation.
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
    """Produce the `Package manager support` table of the benchmark page.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    `docs/benchmark.md`, so the table (and its source-line anchors) always
    matches the code being documented without a checked-in copy.

    The `mpm` column is auto-derived from the live pool: each implemented
    manager renders as `[✅](source_url)`, linking to the class definition
    that proves the support. Competitor columns are filled from
    `docs/benchmark.yaml`, which only encodes what the *other* tools
    support.

    Each manager identifier in the first column is rendered as a link: to its
    dedicated documentation page for implemented managers, or to its homepage
    from the YAML's `homepages` mapping for competitor-only managers. IDs
    without any known URL render as plain ``\\`code\\```.

    Support cells are normally `✅`, but render as `[🟡](url)` when the
    `(manager_id, competitor)` pair is listed in the YAML's
    `coarse_support` map, with the URL pointing to the maintainer's own
    acknowledgement of the bundling. `🟡` means the competitor can only
    reach this manager through a coarser umbrella step (topgrade's
    `--only shell` or `--only vim`), never in isolation. Refused
    managers (from the `refused` map) render as `[❌](url)` where the
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
            label = f"[`{mid}`](managers/{mid}.md)"
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
    `docs/augmentations.md`, so the table always matches the code being
    documented without a checked-in copy.

    Each `✅` marks a capability `mpm` synthesizes for a manager that lacks
    it natively, straight from the capability introspection helpers:

    - *Full* `upgrade --all`: the manager only reaches the operation through
      the one-by-one fallback
      ({func}`meta_package_manager.capabilities.upgrade_all_is_synthesized`).
    - *Orphan sweep*: the manager has no native "remove every orphan" verb, so
      `mpm cleanup --orphans` synthesizes it from the manager's orphan listing
      and per-package removal
      ({func}`meta_package_manager.capabilities.cleanup_orphan_is_synthesized`).
    - *Exact search* and *Extended search*: the manager's native search cannot
      filter that way, so `mpm` refilters the raw results itself (the
      `exact_support`/`extended_support` flags set by
      {func}`meta_package_manager.capabilities.search_capabilities` and the
      config-defined manager builder).

    Managers needing no backfill at all are left out of the table. Each listed
    manager links to its dedicated documentation page.
    """
    table = []
    for mid, manager in sorted(pool.items()):
        upgrade_all = upgrade_all_is_synthesized(manager)
        orphan_sweep = cleanup_orphan_is_synthesized(manager)
        exact = exact_search_is_synthesized(manager)
        extended = extended_search_is_synthesized(manager)
        if not (upgrade_all or orphan_sweep or exact or extended):
            continue
        table.append([
            f"[`{mid}`](managers/{mid}.md)",
            "✅" if upgrade_all else "",
            "✅" if orphan_sweep else "",
            "✅" if exact else "",
            "✅" if extended else "",
        ])

    return render_table(
        table,
        headers=[
            "Manager",
            "Full `upgrade --all`",
            "Orphan sweep",
            "Exact search",
            "Extended search",
        ],
        table_format=TableFormat.GITHUB,
        colalign=["left", "center", "center", "center", "center"],
        disable_numparse=True,
    )


def binaries_download_table() -> str:
    """Produce the per-platform download table of the latest release binaries.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    `docs/install.md`. Binaries carry the version in their filename
    (`meta-package-manager-7.3.0-linux-arm64.bin`), so no stable
    `releases/latest/download` URL can exist: the table is regenerated from
    `docs/assets/binaries.csv`, which the release pipeline extends at each
    release with the exact asset URLs, newest first.
    """
    csv_path = PROJECT_ROOT / "docs" / "assets" / "binaries.csv"
    # Cells are markdown: the version cell starts with [`7.3.0` ...] and the
    # platform cell embeds the download link as
    # [... `linux-arm64`](https://github.com/.../meta-package-manager-7.3.0-linux-arm64.bin).
    version_regexp = re.compile(r"\[`(?P<version>[^`]+)`")
    link_regexp = re.compile(r"`(?P<target>[a-z0-9]+-[a-z0-9]+)`\]\((?P<url>[^)]+)\)")
    downloads = {}
    latest_version = None
    with csv_path.open(encoding="UTF-8") as csv_file:
        for row in csv.DictReader(csv_file):
            version_match = version_regexp.search(row["Version"])
            link_match = link_regexp.search(row["Platform"])
            if not version_match or not link_match:
                continue
            if latest_version is None:
                latest_version = version_match["version"]
            if version_match["version"] != latest_version:
                break
            downloads[link_match["target"]] = link_match["url"]

    table = []
    for os_label, os_id in (
        ("Linux", "linux"),
        ("macOS", "macos"),
        ("Windows", "windows"),
    ):
        cells = [f"**{os_label}**"]
        for arch in ("arm64", "x64"):
            url = downloads.get(f"{os_id}-{arch}")
            filename = url.rsplit("/", 1)[-1] if url else None
            cells.append(f"[Download `{filename}`]({url})" if url else "")
        table.append(cells)

    return render_table(
        table,
        headers=["Platform", "`arm64`", "`x86_64`"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "left"],
        disable_numparse=True,
    )


def _fenced(content: str, language: str) -> str:
    """Wrap content in a fenced code block, lengthening the fence as needed.

    Sample outputs are arbitrary text: a fence one backtick longer than the
    longest backtick run in the content can never be terminated early.
    """
    longest = max(
        (len(run.group(0)) for run in re.finditer(r"`+", content)),
        default=0,
    )
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{content}\n{fence}"


@cache
def _toml_definition(definition_source: str) -> dict:
    """Parse a bundled TOML definition file into its raw document.

    Cached: rendering one config-defined manager's page reads the same file
    from several section generators.
    """
    return tomllib.loads(  # type: ignore[no-any-return]
        (PROJECT_ROOT / definition_source).read_text(encoding="UTF-8"),
    )


@cache
def _cooldown_table(section_title: str) -> tuple[tuple[str, ...], ...]:
    """Parse one hand-curated table of `docs/cooldown.md` into its rows.

    Both tables of the page are reused on the per-manager pages, so both are
    read the same way: the section is delimited by its own title and the next
    `##` heading, and every pipe-prefixed line of at least four cells is kept
    with its markdown preserved. The header and separator lines come along
    harmlessly, as no manager ID ever matches them.
    """
    text = (PROJECT_ROOT / "docs" / "cooldown.md").read_text(encoding="UTF-8")
    section = text.partition(section_title)[2].partition("\n## ")[0]
    rows: list[tuple[str, ...]] = []
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) >= 4:
            rows.append(cells)
    return tuple(rows)


def _cooldown_status(manager_id: str) -> tuple[str, str, str] | None:
    """Extract a manager's row from the cooldown support table.

    The "Supported managers" table of `docs/cooldown.md` is the hand-curated
    source of truth for release-age gating: per manager, a status glyph, the
    native mechanism and an upstream reference. A row may cover several managers
    at once, its id cell listing each as a backticked code span (like the shared
    `uv`/`uvx` row). Returns the three cells with their markdown preserved
    (`—` marks an empty cell), or `None` when the table has no row for the
    manager yet.
    """
    for cells in _cooldown_table("## Supported managers"):
        if manager_id in re.findall(r"`([^`]+)`", cells[0]):
            return cells[1], cells[2], cells[3]
    return None


def _retraction_status(manager_id: str) -> tuple[str, str, str] | None:
    """Extract a manager's registry row from the retraction table.

    The "Retraction paths by registry" table of `docs/cooldown.md` records
    whether a compromised release can be withdrawn from the registry a manager
    resolves against, and whether that registry publishes a per-version release
    date. Both are properties of the registry rather than of the manager CLI, so
    the table is keyed by registry and lists its managers in the second cell,
    each as a linked code span. Returns the registry name, the retraction shape
    and the publish-date cell, or `None` when no row covers the manager.

    ```{note}
    Every pool manager belongs to exactly one row, and the reused cells link
    absolutely so they survive the move to `docs/managers/`. Both invariants
    are guarded by `test_retraction_table_well_formed`.
    ```
    """
    for cells in _cooldown_table("## Retraction paths by registry"):
        if manager_id in re.findall(r"\[`([^`]+)`\]", cells[1]):
            return cells[0], cells[2], cells[3]
    return None


def _toml_definition_intro(definition_source: str) -> str | None:
    """Extract the description comment atop a bundled TOML definition.

    The TOML counterpart of a manager class docstring: each bundled file opens
    with a comment block describing the manager and its quirks. The boilerplate
    is stripped (the "Bundled package-manager definition" tag line and the
    schema/loader pointer), bare URLs are wrapped into autolinks, and paragraph
    breaks (lone `#` lines) are preserved. Returns `None` when nothing but
    boilerplate is found.
    """
    lines = []
    for line in (
        (PROJECT_ROOT / definition_source).read_text(encoding="UTF-8").splitlines()
    ):
        if line == "#":
            lines.append("")
        elif line.startswith("# "):
            lines.append(line[2:])
        else:
            break

    text = "\n".join(lines)
    # The schema/loader pointer spans reflowed lines, so strip it before
    # splitting paragraphs.
    text = re.sub(r"(?s)\s*See\s+docs/overrides\.md.*?for\s+the\s+loader\.", "", text)
    paragraphs = [
        p.strip("\n")
        for p in text.split("\n\n")
        if p.strip() and not p.startswith("Bundled package-manager definition")
    ]
    if not paragraphs:
        return None
    intro = "\n\n".join(paragraphs)

    def autolink(match: re.Match) -> str:
        # Keep trailing punctuation out of the link target.
        url = match.group(0).rstrip(".,;:")
        return f"<{url}>{match.group(0)[len(url) :]}"

    # MyST's linkify extension is off: turn bare URLs into explicit autolinks.
    return re.sub(r"https?://[^\s)>]+", autolink, intro)


@cache
def logo_manifest() -> dict:
    """Read the provenance manifest of the vendored brand marks."""
    manifest: dict = yaml.safe_load(
        (LOGO_DIR / "logos.yaml").read_text(encoding="UTF-8"),
    )
    return manifest


def manager_logo(manager_id: str, *, inline: bool = False) -> str:
    """Produce the inlined brand mark of a manager, or nothing when it has none.

    The SVG is injected verbatim into the page instead of being referenced as an
    image file, which is what lets CSS recolor it: the vendored marks carry no
    `fill`, so they inherit `currentColor` and stay legible on both themes. The
    brand color is passed as a custom property and the stylesheet applies it on
    the light theme only, and only for marks clearing {data}`MIN_LOGO_CONTRAST`.

    Raw HTML is invisible to the linkcheck builder, which reads a raw node's
    `source` attribute rather than its content, so 75 pages of inlined artwork
    cost the link-check budget nothing.

    :param inline: Render the small variant sitting in a table cell, rather than
        the mark floated atop a manager's own page.
    """
    slug = pool[manager_id].logo
    if not slug:
        return ""
    icon = logo_manifest()["icons"][slug]
    svg = (LOGO_DIR / f"{slug}.svg").read_text(encoding="UTF-8").strip()

    # Size the tag itself, on top of the stylesheet's own rules. The vendored
    # marks carry a `viewBox` and nothing else, so they have no intrinsic size:
    # anywhere the stylesheet does not reach, an unsized one balloons to fill its
    # container instead of rendering as an icon.
    size = 24 if inline else 96
    svg = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)

    # A table cell wraps its content in a paragraph, where a <div> would be
    # invalid markup: the inline variant is a <span>.
    tag = "span" if inline else "div"
    classes = "manager-logo manager-logo-inline" if inline else "manager-logo"
    hex_color = icon["hex"]
    style = f' style="--manager-logo-color: #{hex_color}"'
    label = f"{icon['title']} logo"
    return (
        f'<{tag} class="{classes}"{style} role="img" '
        f'aria-label="{label}">{svg}</{tag}>'
    )


def manager_card(manager_id: str) -> str:
    """Produce the infobox of a manager's page: its mark atop its key facts.

    A `{card}` floated to the side of the intro prose, in the shape an
    encyclopaedia gives a subject: identity first, then the handful of facts a
    reader wants without scrolling. Everything else the page knows (platforms in
    full, operations, ecosystem identifiers) keeps its own section below, so the
    box stays a summary rather than a second copy of the page.

    The mark rides in the card's *header* rather than its `:img-top:` option,
    which takes a URI and would emit an `<img>`: an externally referenced SVG
    cannot inherit `currentColor`, so the unfilled marks would render black and
    disappear on the dark theme. The header takes arbitrary content, so the
    inlined SVG of {func}`manager_logo` keeps adapting to both themes.

    A manager with no mark still gets the box, headerless: the facts are the
    point, and the artwork is the bonus.
    """
    m = pool[manager_id]
    source_url = manager_source_url(manager_id)
    source_path = source_url.removeprefix(f"{GITHUB_BLOB_URL}/").partition("#")[0]

    facts = [
        ("ID", f"`{manager_id}`"),
        ("Home page", f"<{m.homepage_url}>"),
        ("Source", f"[`{source_path}`]({source_url})"),
    ]
    if m.requirement:
        # Unstyled, like the readme matrix's own Version column: a table cell is
        # data, not the prose the backtick-the-version rule governs. Both angle
        # brackets need escaping here, where that column needs only one: a `<`
        # opens a tag anywhere, but the `>` of a floor requirement also opens a
        # blockquote when it leads a definition, swallowing itself and boxing the
        # version in a quote.
        requirement = (
            _format_requirement(m.requirement).replace("<", r"\<").replace(">", r"\>")
        )
        facts.append(("Version requirement", requirement))
    if m.supports_cooldown:
        facts.append(("Cooldown", "✓"))

    platforms = manager_platforms(manager_id)
    if platforms:
        facts.append(("Platforms", platforms))

    # The same reading as the readme matrix's operation columns, folded into one
    # row: what this manager can do. The Operations section below keeps the full
    # table, with the caveats each one carries.
    supported = [f"`{op.name}`" for op in Operations if implements(m, op)]
    if supported:
        facts.append(("Operations", FACT_SEPARATOR.join(supported)))

    purl_types = sorted(
        {manager_id} | {t for t, ids in PURL_MAP.items() if ids and manager_id in ids},
    )
    facts.append((
        "purl types",
        FACT_SEPARATOR.join(f"`pkg:{t}`" for t in purl_types),
    ))
    if m.brewfile_entry_type:
        facts.append((
            "Brewfile entry",
            f"`{m.brewfile_entry_type}`, in [Brewfile backups](../dump.md)",
        ))

    # A definition list, so each fact reads as a labelled row of the box.
    rows = "\n\n".join(f"**{label}**\n: {value}" for label, value in facts)

    logo = manager_logo(manager_id)
    header = f"{logo}\n^^^\n" if logo else ""
    return f"```{{card}}\n:class-card: manager-card\n\n{header}{rows}\n```"


def manager_logo_credits() -> str:
    """Produce the attribution block for every vendored brand mark.

    Rendered into the *Package manager logos* section of `docs/license.md`, the
    project's legal sink, rather than next to the artwork it credits. Twelve of
    the marks carry an attribution-bearing license (Debian's `CC-BY-SA-3.0`,
    NixOS' `CC-BY-4.0`, Fedora's own brand policy, ...), so crediting them is a
    license condition rather than a courtesy. Generating the block from the
    manifest keeps the credit exhaustive on its own, with no hand-maintained
    list to forget when a manager joins or leaves the pool.
    """
    manifest = logo_manifest()
    upstream = manifest["upstream"]

    table = []
    for icon in sorted(manifest["icons"].values(), key=lambda i: i["title"].casefold()):
        license_id = icon["license"]
        license_cell = (
            f"[custom]({license_id})"
            if license_id.startswith("http")
            else f"`{license_id}`"
        )
        table.append([
            f"[{icon['title']}]({icon['source']})",
            ", ".join(f"[`{mid}`](managers/{mid}.md)" for mid in icon["managers"]),
            license_cell,
        ])

    rendered = render_table(
        table,
        headers=["Mark", "Stands for", "License"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "center"],
        disable_numparse=True,
    )
    return (
        f"Brand marks come from [{upstream['name']}]({upstream['url']}) "
        f"`{upstream['version']}`, whose set is `{upstream['license']}` except "
        "where a mark declares otherwise below. Each one is inlined atop its "
        "manager's own page and in the [manager index](managers.md).\n\n"
        f"{rendered}"
    )


def manager_intro(manager_id: str) -> str:
    """Produce the lede of a manager's documentation page.

    Rendered live at Sphinx build time by the first ``{python:render}`` block of
    `docs/managers/<id>.md`. Stacks, in order: an unmaintained-project warning when
    the manager is unmaintained (or a maintenance-watch note for a still-maintained
    but slowing upstream), the manager class's own docstring (whose caveats and
    notes are otherwise only surfaced by the API docs), and a facts list (home
    page, source, version requirement).

    The class docstring is MyST, so it inlines straight into the page, after a
    `{py:currentmodule}` directive letting module-sibling cross-references
    resolve outside their autodoc context. Config-defined managers get the
    description comment atop their bundled TOML definition
    ({func}`_toml_definition_intro`) instead of their synthesized class
    docstring, with a pointer to the file as fallback.
    """
    m = pool[manager_id]
    blocks = []

    if m.unmaintained:
        blocks.append(
            "```{warning}\n"
            f"`{manager_id}` is unmaintained. {m.unmaintained_message}\n"
            "```",
        )
    elif m.maintenance_note:
        blocks.append(
            f"```{{note}}\n{m.maintenance_note}\n```",
        )

    # After the admonition, never before: the card floats, and a float placed
    # above an admonition overlaps its background box instead of clearing it.
    blocks.append(manager_card(manager_id))

    source_url = manager_source_url(manager_id)

    if getattr(m, "definition_source", None):
        blocks.append(
            _toml_definition_intro(m.definition_source)
            or f"Defined as a [bundled TOML configuration]({source_url}) rather "
            "than a Python class.",
        )
    else:
        docstring = type(m).__dict__.get("__doc__")
        assert docstring, f"Manager class of {manager_id} has no docstring."
        blocks.append(
            f"```{{py:currentmodule}} {type(m).__module__}\n```\n\n"
            f"{inspect.cleandoc(docstring)}",
        )

    return "\n\n".join(blocks)


def _ecosystem_siblings(manager_id: str) -> list[str]:
    """Pool managers sharing a purl ecosystem with the given one.

    Two managers are siblings when {data}`~meta_package_manager.specifier.PURL_MAP`
    maps them to at least one common purl type: `uv`, `pip` and `pipx` all
    resolve `pkg:pypi`, so they surface each other. Used by
    {func}`manager_augments` to name the relatable neighbors a single-ecosystem
    user already juggles. Sorted, self excluded; empty for a manager whose purl
    types no other pool manager shares (`cargo`, `gem`).
    """
    pool_ids = set(pool.all_manager_ids)
    types = {t for t, ids in PURL_MAP.items() if ids and manager_id in ids}
    siblings: set[str] = set()
    for purl_type, ids in PURL_MAP.items():
        if purl_type in types and ids:
            siblings |= set(ids) & pool_ids
    return sorted(siblings - {manager_id})


def _augment_gains(manager_id: str) -> list[str]:
    """List the capabilities `mpm` backfills for this manager specifically.

    One entry per selective augmentation the manager relies on, read from the
    same capability introspection that feeds {func}`augmentations_table`:
    synthesized full `upgrade --all`, synthesized orphan sweep, and refiltered
    `--exact`/`--extended` search. Each is phrased as what `mpm` adds, never as
    a native limitation: the introspection proves `mpm` synthesizes the
    operation for the interface it drives, not that the tool as a whole lacks it
    (the `uv` id drives uv's `pip` interface, while `uvx` drives `uv tool`,
    which does ship a native `upgrade --all`). Empty for a feature-complete
    manager.
    """
    m = pool[manager_id]
    gains = []
    if upgrade_all_is_synthesized(m):
        gains.append(
            "a one-command `upgrade --all` that refreshes every outdated package "
            "in a single run",
        )
    if cleanup_orphan_is_synthesized(m):
        gains.append(
            "a one-command `cleanup --orphans` that removes every orphaned "
            "dependency at once",
        )
    exact = exact_search_is_synthesized(m)
    extended = extended_search_is_synthesized(m)
    if exact and extended:
        gains.append(
            "`--exact` and `--extended` search, to narrow to exact names or match "
            "descriptions",
        )
    elif exact:
        gains.append("`--exact` search, to narrow results to exact names")
    elif extended:
        gains.append("`--extended` search, to match against package descriptions")
    return gains


def manager_augments(manager_id: str) -> str:
    """Produce the "What `mpm` adds" section of a manager's documentation page.

    Rendered live at Sphinx build time by the second ``{python:render}`` block
    of `docs/managers/<id>.md`, right after the intro: the pitch for a reader
    who already knows the native tool. Stacks the manager-specific backfills
    ({func}`_augment_gains`), the cross-manager reach naming the ecosystem
    neighbors the reader already juggles ({func}`_ecosystem_siblings`), and the
    universal augmentations shared by every managed tool. Every claim describes
    what `mpm` does, derived from the capability introspection, so the section
    can neither overstate a native limitation nor drift from the code. Points at
    `docs/augmentations.md` for the full, cross-manager treatment.
    """
    gains = _augment_gains(manager_id)

    siblings = _ecosystem_siblings(manager_id)
    peers = (
        ", ".join(f"`{sibling}`" for sibling in siblings)
        + " and any other manager you run"
        if siblings
        else "every other manager you run"
    )
    reach_body = (
        f"`mpm installed` and `mpm outdated` cover `{manager_id}` alongside {peers} "
        "in one table, `mpm upgrade --all` updates them together, and `mpm sbom` "
        "exports the whole machine as one bill of materials."
    )
    universal = (
        "Every `mpm` command also gains `--dry-run` and `--plan` previews, "
        "cross-scheme version comparison and purl identifiers. See "
        "[manager augmentations](../augmentations.md) for how each one is built."
    )

    if gains:
        lede = f"Through `mpm`, `{manager_id}` gains:"
        bullets = "\n".join(f"- {gain}" for gain in gains)
        reach = (
            f"Bigger still, `mpm` reaches across every manager at once: {reach_body}"
        )
        return f"{lede}\n\n{bullets}\n\n{reach}\n\n{universal}"
    reach = (
        f"`mpm` reaches across every manager at once, not `{manager_id}` alone: "
        f"{reach_body}"
    )
    return f"{reach}\n\n{universal}"


ROSETTA_OPERATIONS: tuple[tuple[str, str, str, bool], ...] = (
    # (manager method, task label, mpm-command template, whether it takes an operand).
    ("installed", "List what's installed", "mpm --{id} installed", False),
    ("outdated", "List outdated packages", "mpm --{id} outdated", False),
    ("search", "Search for a package", "mpm --{id} search {op}", True),
    ("install", "Install a package", "mpm install pkg:{id}/{op}", True),
    ("upgrade_one_cli", "Upgrade one package", "mpm --{id} upgrade {op}", True),
    ("upgrade_all_cli", "Upgrade everything", "mpm --{id} upgrade --all", False),
    ("remove", "Remove a package", "mpm remove pkg:{id}/{op}", True),
    ("orphans", "List orphaned dependencies", "mpm --{id} orphans", False),
    ("cleanup_cache", "Clear caches", "mpm --{id} cleanup --cache", False),
    ("doctor_cli", "Run health checks", "mpm --{id} doctor", False),
)
"""Rows of the Rosetta table, in display order.

Each tuple is the native operation method, its task label, the `mpm` command
template and whether the command takes a package operand. The native call is
harvested from the method's own documented sample; a row is dropped when
nothing is harvestable (see {func}`manager_rosetta`).
"""

_ROSETTA_TOML_MEMBER = {
    "upgrade_one_cli": "upgrade_one",
    "upgrade_all_cli": "upgrade_all",
    "doctor_cli": "doctor",
}
"""Methods whose name differs from their operation key in a bundled TOML definition."""


def _native_invocation(manager, member: str) -> tuple[list[str], str | None] | None:
    """Return the native command tokens and operand documented for an operation.

    The command is read from the manager's own captured sample, so it is exactly
    what the tool is invoked with: a bundled TOML manager's operation spec
    (`cli` plus `args`), or the first documented `shell-session` block of a
    class-based manager's method. The MRO is walked so an operation defined on a
    shared base (`Homebrew` for `brew`/`cask`) is found, not just the leaf class
    body. The forced arguments {func}`manager_cli` documents separately are
    stripped to leave the recognizable native form, a trailing `| jq`-style
    illustration is dropped, and the operand is the last non-flag token. `None`
    when the operation documents no command.
    """
    forced = set(manager.pre_args) | set(manager.post_args)

    tokens = None
    source = getattr(manager, "definition_source", None)
    if source:
        operations = _toml_definition(source)["mpm"]["managers"][manager.id].get(
            "operations",
            {},
        )
        spec = operations.get(_ROSETTA_TOML_MEMBER.get(member, member))
        if spec:
            tokens = [spec.get("cli", manager.cli_names[0]), *spec.get("args", ())]
    else:
        for klass in type(manager).__mro__:
            try:
                blocks = class_display_blocks(klass).get(member, ())
            except (TypeError, OSError):
                continue  # A built-in base (object) has no source to harvest.
            commands = block_commands(blocks[0]) if blocks else []
            if commands:
                tokens = commands[0]
                break

    if not tokens:
        return None
    if "|" in tokens:  # Drop a `... | jq` illustration, keep the real command.
        tokens = tokens[: tokens.index("|")]
    core = [t for t in tokens if t not in forced]
    if not core:
        return None
    return core, _example_operand(manager, core)


def _example_operand(manager, core: list[str]) -> str | None:
    """Pick the example package operand out of a documented command.

    Best-effort heuristics over the audited failure classes; `None` (rendered as
    a placeholder) whenever the guess would mislead:

    - Candidates are the non-flag tokens, stripped of shell quoting, skipping
      `sudo`, the binary and any token restating the manager itself (winget's
      `--source winget` would otherwise shadow the package id).
    - Two candidates sitting in flag-value position means the package id cannot
      be told from the other value (PowerShell's `-Name X -Scope CurrentUser`).
    - The operand is the last candidate, except a version-looking tail hands
      over to the token before it (`asdf install nodejs 20.10.0`) when that one
      is not the leading subcommand: `mas install 945397020` keeps its numeric
      id.
    - A glob or quote residue is never a usable example (conda's `"*pytz*"`).
    """
    excluded = set(manager.cli_names) | {manager.id, "sudo"}
    candidates = []
    for position, token in enumerate(core):
        cleaned = token.strip("'\"")
        if not cleaned or cleaned.startswith("-") or cleaned in excluded:
            continue
        flag_value = position > 0 and core[position - 1].startswith("-")
        candidates.append((cleaned, flag_value))
    if not candidates:
        return None
    if sum(flag_value for _, flag_value in candidates) >= 2:
        return None
    operand = candidates[-1][0]
    if operand[0].isdigit() and len(candidates) >= 3:
        operand = candidates[-2][0]
    if any(char in operand for char in "*?\"'"):
        return None
    return operand


def manager_rosetta(manager_id: str) -> str:
    """Produce the command-mapping section of a manager's documentation page.

    A Rosetta table for a reader fluent in the native tool: each operation as
    the native call `mpm` makes (harvested by {func}`_native_invocation`) beside
    the uniform `mpm` command. Native DSL placeholders (`{package_id}`) are
    rewritten to `<pkg>`-style angle brackets, and a manager documenting fewer
    than three operations yields nothing (the section is then omitted from its
    stub), so the table appears only where it is useful. A closing note points
    at `--dry-run`, since the table lists every invocation the flag applies to.
    """
    m = pool[manager_id]
    rows = []
    for member, task, mpm_template, has_operand in ROSETTA_OPERATIONS:
        native = _native_invocation(m, member)
        if native:
            core, operand = native
            native_cell = "`" + " ".join(core) + "`"
        elif member == "upgrade_all_cli" and upgrade_all_is_synthesized(m):
            native_cell, operand = "—", None  # No single native command.
        else:
            continue
        operand = operand if (has_operand and operand) else "<pkg>"
        mpm_cell = "`" + mpm_template.format(id=manager_id, op=operand) + "`"
        # Rewrite DSL operand placeholders (`{package_id}`) to angle brackets.
        native_cell = re.sub(r"\{(\w+)\}", r"<\1>", native_cell)
        mpm_cell = re.sub(r"\{(\w+)\}", r"<\1>", mpm_cell)
        rows.append([task, native_cell, mpm_cell])

    if len(rows) < 3:
        return ""

    table = render_table(
        rows,
        headers=["To…", f"With `{manager_id}`", "With `mpm`"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "left"],
        disable_numparse=True,
    )
    intro = (
        f"You already know `{manager_id}`: each operation maps one-to-one onto "
        "`mpm`, in an interface shared by every manager."
    )
    dry_run = (
        "Prefix any command above with [`--dry-run`](../augmentations.md) to "
        "simulate the underlying manager calls without touching the system: the "
        "safe way to watch what `mpm` would do before trusting it."
    )
    return f"{intro}\n\n{table}\n\n{dry_run}"


def manager_recipes(manager_id: str) -> str:
    """Produce the recipes section of a manager's documentation page.

    A few copy-paste jobs a reader would otherwise script around the native
    tool: snapshot and restore, an SBOM export, and (when the manager implements
    it) a CI health gate. Each is a real `mpm` invocation, gated on the
    operation being available so no unsupported command is shown.
    """
    m = pool[manager_id]
    lines = [
        (
            f"- Snapshot and clone a machine: `mpm --{manager_id} dump "
            f"{manager_id}.toml`, then `mpm restore {manager_id}.toml` on the next one."
        ),
    ]
    if m.brewfile_entry_type:
        lines.append(
            f"- Export a Brewfile entry instead: `mpm --{manager_id} dump "
            "--brewfile Brewfile`.",
        )
    lines.append(
        f"- Export a compliance SBOM: `mpm --{manager_id} sbom` (CycloneDX by "
        "default, `--spdx` for SPDX).",
    )
    if implements(m, Operations.doctor):
        lines.append(
            f"- Gate CI on health: `mpm --{manager_id} doctor` relays {m.name}'s "
            "own diagnosis and exits non-zero on trouble.",
        )
    intro = (
        f"A few jobs you would otherwise script around `{manager_id}`, one `mpm` "
        "command each:"
    )
    return f"{intro}\n\n" + "\n".join(lines)


def _platform_coverage(p_obj, platforms: frozenset) -> tuple[str, str | None] | None:
    """Return the icon and partial-coverage annotation of a platform entry.

    `None` when the manager covers no member of the entry. The annotation is
    `None` on full coverage, and otherwise spells out whichever side is
    shorter: the covered members (`Exherbo Linux only`) or the missing ones
    (`except WSL1, WSL2`), so a manager backing most of a large group stays
    readable.
    """
    members = set(extract_members(p_obj))
    covered = members & platforms
    if not covered:
        return None
    annotation = None
    if covered != members:
        missing = members - covered
        side, template = (
            (missing, "except {}")
            if len(missing) < len(covered)
            else (covered, "{} only")
        )
        names = ", ".join(sorted((p.name for p in side), key=str.casefold))
        annotation = template.format(names)
    return p_obj.icon, annotation


def manager_platforms(manager_id: str) -> str:
    """Produce the platform row of a manager's infobox.

    Every supported {data}`~meta_package_manager.platforms.MAIN_PLATFORMS` entry
    on one line, with {func}`_platform_coverage`'s annotation when the manager
    only backs part of a multi-platform group: the readme's operation matrix
    renders an all-or-nothing icon, this row is where partial support is spelled
    out.

    Entries are separated the same way as every other repeated infobox value,
    which also keeps a coverage annotation from running into the platform that
    follows it.
    """
    m = pool[manager_id]
    entries = []
    for p_obj in MAIN_PLATFORMS:
        coverage = _platform_coverage(p_obj, m.platforms)
        if coverage is None:
            continue
        icon, annotation = coverage
        # Non-breaking too: an icon stranded at the end of a line, with its name
        # starting the next, reads as two separate platforms.
        entry = f"{icon}\u00a0{p_obj.name}"
        if annotation:
            entry += f" ({annotation})"
        entries.append(entry)
    return FACT_SEPARATOR.join(entries)


def manager_operations(manager_id: str) -> str:
    """Produce the operations table of a manager's documentation page.

    One row per member of {class}`~meta_package_manager.capabilities.Operations`,
    in enum order. The *Notes* column points out the capabilities `mpm`
    synthesizes on top of the native CLI, mirroring the introspection of
    {func}`augmentations_table`, and is dropped entirely for the managers
    needing no backfill.
    """
    m = pool[manager_id]
    table = []
    for op in Operations:
        supported = implements(m, op)
        note = ""
        if supported and op is Operations.upgrade_all and upgrade_all_is_synthesized(m):
            note = "[backfilled by `mpm`](../augmentations.md)"
        elif supported and op is Operations.search:
            missing = [
                label
                for label, synthesized in (
                    ("exact", exact_search_is_synthesized(m)),
                    ("extended", extended_search_is_synthesized(m)),
                )
                if synthesized
            ]
            if missing:
                note = (
                    f"{' and '.join(missing)} search "
                    "[backfilled by `mpm`](../augmentations.md)"
                )
        elif (
            supported
            and op is Operations.remove
            and implements_method(m, "remove_orphan")
        ):
            note = "`--orphans` also drops the package's orphaned dependencies"
        elif supported and op is Operations.cleanup:
            if implements_method(m, "cleanup_orphan"):
                note = "`--orphans` runs the system-wide orphan sweep"
            elif cleanup_orphan_is_synthesized(m):
                note = "`--orphans` sweep [backfilled by `mpm`](../augmentations.md)"
        table.append([f"`{op.name}`", "✓" if supported else "", note])

    headers = ["Operation", "Supported", "Notes"]
    colalign = ["left", "center", "left"]
    if not any(row[2] for row in table):
        table = [row[:2] for row in table]
        headers = headers[:2]
        colalign = colalign[:2]

    return render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=colalign,
        disable_numparse=True,
    )


def _python_regex_literal(pattern: str) -> str:
    """Render a regex as the Python raw-string literal it is declared as in source.

    Gives the version-probe block of the manager pages `python` highlighting
    (Pygments ships no standalone regex lexer). Falls back to `repr()` —
    escaped, non-raw — for the rare pattern a raw literal cannot express: one
    containing both quote characters, or ending with a backslash.
    """
    if not pattern.endswith("\\"):
        if '"' not in pattern:
            return f'r"{pattern}"'
        if "'" not in pattern:
            return f"r'{pattern}'"
    return repr(pattern)


def manager_cli(manager_id: str) -> str:
    """Produce the invocation section of a manager's documentation page.

    Documents how `mpm` drives the manager: binary names and lookup tweaks,
    the arguments and environment forced on every call, then the version probe
    and its parsing regexes. Beyond the always-shown CLI names and version
    probe, only non-default facts are listed. The argv fragments (pre-commands,
    forced arguments) are collated into single code spans, matching how they
    appear on the command line. Escalation and cooldown each have their own
    section ({func}`manager_sudo`, {func}`manager_cooldown`).

    The version probe additionally shows its captured output as a terminal
    transcript, from the `[samples.version]` fixture of a bundled TOML manager
    or the `version_regexes` docstring of a class-based one; the per-operation
    samples render in the reference-traces section ({func}`manager_traces`).
    """
    m = pool[manager_id]

    def code_list(values) -> str:
        return ", ".join(f"`{v}`" for v in values)

    lines = [f"- CLI names, in lookup order: {code_list(m.cli_names)}"]
    if m.cli_search_path:
        lines.append(f"- Extra CLI search paths: {code_list(m.cli_search_path)}")
    if m.pre_cmds:
        lines.append(f"- Pre-commands: `{' '.join(m.pre_cmds)}`")
    if m.pre_args:
        lines.append(f"- Arguments forced before each call: `{' '.join(m.pre_args)}`")
    if m.post_args:
        lines.append(f"- Arguments forced after each call: `{' '.join(m.post_args)}`")
    if m.extra_env:
        lines.append("- Environment forced on each call:")
        lines.extend(f"  - `{k}={v}`" for k, v in sorted(m.extra_env.items()))
    if m.timeout is not None:
        lines.append(f"- Call timeout: {m.timeout} seconds")

    source = getattr(m, "definition_source", None)
    if source:
        doc = _toml_definition(source)
        version_sample = doc.get("samples", {}).get("version", {}).get("output")
    else:
        version_sample = version_trace(type(m))

    probe = " ".join(((m.version_cli or m.cli_names[0]), *m.version_cli_options))
    regex_suffix = (
        " the first of these regular expressions to match"
        if len(m.version_regexes) > 1
        else ""
    )
    regex_fence = _fenced(
        "\n".join(_python_regex_literal(regex) for regex in m.version_regexes),
        "python",
    )

    parts = ["\n".join(lines)]
    if m.pre_args or m.post_args or m.extra_env:
        parts.append(
            "`mpm` forces those arguments and variables on every call, so runs "
            "stay quiet, non-interactive and reproducible: the defaults you would "
            "set in CI anyway.",
        )
    if version_sample:
        transcript = version_sample.strip("\n")
        parts.append("The version is probed by running:")
        parts.append(_fenced(f"$ {probe}\n{transcript}", "shell-session"))
        parts.append(f"and extracted with{regex_suffix}:")
    else:
        parts.append(
            f"The version is extracted from the output of `{probe}` "
            f"with{regex_suffix}:",
        )
    parts.append(regex_fence)

    return "\n\n".join(parts)


def manager_selection(manager_id: str) -> str:
    """Produce the selection-and-configuration section of a manager's page.

    The levers to control this manager's participation: the one-run
    `--no-<id>` deselector, the persistent selection toggle in the
    configuration file, and a per-manager override block for tuning how `mpm`
    drives it. The command-to-command mapping lives in the Rosetta section
    ({func}`manager_rosetta`); this one points at the fuller
    [configuration](configuration.md) and [overrides](overrides.md) references
    rather than restating them.
    """
    select = (
        f"Deselect `{manager_id}` for a single run with `--no-{manager_id}`, or "
        "persist the choice in your [configuration](../configuration.md):"
    )
    select_toml = _fenced(f"[mpm]\n{manager_id} = false", "toml")
    tune = (
        "Keep it enabled but tune how `mpm` drives it with a "
        "[per-manager override](../overrides.md):"
    )
    tune_toml = _fenced(f"[mpm.managers.{manager_id}]\ntimeout = 900", "toml")
    template = (
        f"`mpm config-template {manager_id}` prints every overridable attribute "
        "as a ready-to-paste block."
    )
    parts = [select, select_toml, tune, tune_toml, template]
    return "\n\n".join(parts)


def manager_sudo(manager_id: str) -> str:
    """Produce the privilege-escalation section of a manager's documentation page.

    States which escalation policy applies (system-wide `sudo` wrapping,
    internal escalation, or none) and how to flip it, deriving everything from
    the escalation attributes so the page can never contradict the code. For
    config-defined managers that do not escalate internally, the operations
    marked `sudo = true` in the bundled TOML definition are listed by name.
    """
    m = pool[manager_id]
    if m.internal_sudo:
        policy = (
            f"{m.name} runs `sudo` from inside its own commands: `mpm` never "
            "wraps it, keeps an already-warm credential cache alive for those "
            "internal escalations, and warns when a mutating call goes silent "
            "on a terminal with a cold cache, since a password prompt may be "
            "hiding in the stream."
        )
    elif m.default_sudo:
        policy = (
            "System-wide manager: `mpm` wraps its privileged operations in "
            "`sudo` out of the box. Instead of letting the tool prompt "
            "mid-run, `mpm` primes the credential cache up-front, with a "
            "single branded password prompt at most. Turn escalation off for "
            "rootless setups with `--no-sudo` or the per-manager "
            "[`sudo` override](../overrides.md)."
        )
    else:
        policy = (
            "`mpm` runs this manager as the current user and never prepends "
            "`sudo` by default. Flip the policy for its privileged operations "
            "with `--sudo` or the per-manager [`sudo` override](../overrides.md)."
        )

    parts = [policy]
    source = getattr(m, "definition_source", None)
    if source and not m.internal_sudo:
        operations = _toml_definition(source)["mpm"]["managers"][manager_id].get(
            "operations",
            {},
        )
        # Map the definition-schema operation names to the user-facing ones.
        privileged = sorted(
            {"upgrade_one": "upgrade"}.get(op, op)
            for op, spec in operations.items()
            if spec.get("sudo")
        )
        if privileged:
            ops_list = ", ".join(f"`{op}`" for op in privileged)
            plural = "s" if len(privileged) > 1 else ""
            parts.append(f"Root is required for its {ops_list} operation{plural}.")
        else:
            parts.append("None of its operations needs root.")
    parts.append("See [privilege escalation](../sudo.md) for the full policy.")
    return "\n\n".join(parts)


def manager_cooldown(manager_id: str) -> str:
    """Produce the cooldown section of a manager's documentation page.

    Reuses the manager's row from the hand-curated "Supported managers" table
    of `docs/cooldown.md` (status, native mechanism, upstream reference), so
    the page and the cooldown overview can never diverge. Tops it with the
    enforcement facts derived from the manager's declarations: the injected
    environment variable when `mpm` drives a native gate, or the fail-closed
    skip applying to everyone else.

    Closes on the registry the manager resolves against, from the same page's
    "Retraction paths by registry" table. A gate that no withdrawal ever
    follows delays a compromised release instead of avoiding it, so whether
    the registry can pull a bad version belongs next to whether `mpm` can gate
    the manager at all.
    """
    m = pool[manager_id]
    row = _cooldown_status(manager_id)

    parts = []
    if m.supports_cooldown:
        parts.append(
            "`mpm` natively enforces its [release-age cooldown](../cooldown.md) "
            f"on {m.name}, injecting the `{m.cooldown_env_var}` environment "
            "variable on every call. Point it at a window "
            f"(`mpm --cooldown 7 --{manager_id} upgrade --all`) to skip anything "
            "published in the last 7 days: a guard against a compromised or "
            "yanked fresh release landing before anyone notices.",
        )
    elif row:
        parts.append(
            f"State of {m.name}'s release-age gating, from the "
            "[cooldown support table](../cooldown.md#supported-managers):",
        )
    else:
        parts.append(
            "Not yet assessed in the "
            "[cooldown support table](../cooldown.md#supported-managers).",
        )
    if row:
        status, mechanism, reference = row
        facts = [f"- Status: {status}"]
        if mechanism not in EMPTY_CELLS:
            facts.append(f"- Mechanism: {mechanism}")
        if reference not in EMPTY_CELLS:
            facts.append(f"- Reference: {reference}")
        parts.append("\n".join(facts))

    retraction = _retraction_status(manager_id)
    if retraction:
        registry, withdrawal, publish_date = retraction
        parts.append(
            "A cooldown only pays off where a compromised release can be "
            "withdrawn while the clock runs, and can only be emulated where the "
            "registry dates its releases. From the [retraction table]"
            "(../cooldown.md#retraction-paths-by-registry):",
        )
        facts = [f"- Registry: {registry}"]
        if withdrawal not in EMPTY_CELLS:
            facts.append(f"- Retraction: {withdrawal}")
        if publish_date not in EMPTY_CELLS:
            facts.append(f"- Publish date: {publish_date}")
        parts.append("\n".join(facts))

    if not m.supports_cooldown and any(
        implements(m, op)
        for op in (Operations.install, Operations.upgrade, Operations.upgrade_all)
    ):
        parts.append(
            "With `--cooldown` set, `mpm` skips this manager's install and "
            "upgrade operations rather than run them unguarded (fail-closed); "
            "`--allow-unsupported-managers` opts back in.",
        )
    return "\n\n".join(parts)


def manager_traces(manager_id: str) -> str:
    """Produce the reference-traces section of a manager's documentation page.

    Raw native outputs replayed as terminal transcripts: the reference `mpm`'s
    parsers were written against. Surfacing them lets users seasoned in the
    native tool spot wrong assumptions, or output formats a newer release has
    since changed. The captures come from the bundled TOML definition's
    `[samples]` fixtures for a config-defined manager, or from the
    `shell-session` blocks documented in a class-based manager's
    `installed`/`outdated` docstrings (harvested by
    {func}`~meta_package_manager.docstring_corpus.literal_blocks`, the same
    literal blocks the corpus test round-trips). Empty for managers without such
    samples (the section is then omitted from the stub); the version probe
    transcript stays in the command-line section, next to the regexes consuming
    it.
    """
    m = pool[manager_id]
    source = getattr(m, "definition_source", None)
    if source:
        doc = _toml_definition(source)
        samples = doc.get("samples", {})
        operations = doc["mpm"]["managers"][manager_id].get("operations", {})
        fences = []
        for op in Operations:
            spec = operations.get(op.name, {})
            for sample in samples.get(op.name, ()):
                command = " ".join((
                    spec.get("cli", m.cli_names[0]),
                    *spec.get("args", ()),
                ))
                output = sample["output"].strip("\n")
                fences.append(_fenced(f"$ {command}\n{output}", "shell-session"))
        source_label = "bundled definition"
    else:
        fences = [
            _fenced(block, block_language(block))
            for _, _, block in literal_blocks(
                type(m), ("installed", "outdated", "orphans")
            )
        ]
        source_label = "manager source"
    if not fences:
        return ""
    intro = (
        "Raw native outputs captured in the "
        f"[{source_label}]({manager_source_url(manager_id)}): the reference "
        f"`mpm`'s parsers were written against. If you know {m.name} well and a "
        "transcript below looks wrong, or a newer release changed its output "
        "format, [report it]"
        "(https://github.com/kdeldycke/meta-package-manager/issues)."
    )
    outro = (
        "Feed any of these through `mpm` and the raw output becomes one uniform "
        "table, the same shape for every manager: filter it, project columns, or "
        f"export it (`mpm --{manager_id} installed --output json`, or `csv`, "
        "`toml`, `yaml`), each package carrying a purl and a version comparable "
        "across managers."
    )
    return "\n\n".join((intro, *fences, outro))


class ChangelogEntry(NamedTuple):
    """One changelog bullet, resolved to the release that shipped it."""

    version: str
    """Package version of the release the entry sits under."""

    date: str
    """Release date, or `unreleased` for the development section."""

    url: str
    """Comparison URL carried by the release heading."""

    flag: str | None
    """Bold marker opening the entry (`Breaking`), or `None` for a plain one."""

    text: str
    """Entry body, verbatim from the changelog."""


@cache
def _changelog_entries() -> dict[str, tuple[ChangelogEntry, ...]]:
    """Index `changelog.md` by the managers each of its entries is scoped to.

    Every changelog bullet opens with a comma-separated scope tag, and
    `test_changelog` already enforces that vocabulary: tags are sorted,
    deduplicated and drawn from the pool IDs plus the platform IDs and the
    `mpm`, `bar-plugin` and `gnome-shell` scopes. So the changelog needs no
    heuristic mining, only a read: scopes naming a pool manager are kept, the
    project-wide ones dropped, and a multi-scope entry is filed under each
    manager it names.

    Entries keep their changelog order, which is newest release first and
    curated within a release. Cached: one parse feeds all the manager pages.

    ```{note}
    A scope whose manager left the pool silently drops its entries here, but
    `test_changelog` fails on it first, since the same vocabulary check builds
    its allowed set from the live pool.
    ```
    """
    release = re.compile(
        r"^## \[`(?P<version>[^`]+)` \((?P<date>[^)]+)\)\]\((?P<url>[^)]+)\)",
    )
    bullet = re.compile(
        r"^- (?:\*\*(?P<flag>[A-Za-z]+):\*\* )?"
        r"\[(?P<scopes>[a-z0-9,\-]+)\] (?P<text>.+)$",
    )

    entries: dict[str, list[ChangelogEntry]] = {}
    version = date = url = ""
    changelog = (PROJECT_ROOT / "changelog.md").read_text(encoding="UTF-8")
    for line in changelog.splitlines():
        heading = release.match(line)
        if heading:
            version, date, url = heading.group("version", "date", "url")
            continue
        match = bullet.match(line)
        if not match:
            continue
        for manager_id in match["scopes"].split(","):
            if manager_id not in pool:
                continue
            entries.setdefault(manager_id, []).append(
                ChangelogEntry(version, date, url, match["flag"], match["text"]),
            )
    return {mid: tuple(items) for mid, items in entries.items()}


def manager_changelog(manager_id: str) -> str:
    """Produce the release-history section of a manager's documentation page.

    Every change `mpm` shipped for this manager, grouped by the release that
    carried it, newest first. The entry text is reproduced verbatim: the
    changelog is the curated wording, and rewriting it here would be one more
    thing to drift. Reproducing it is only safe because every link it carries
    is absolute, so nothing breaks one directory deeper in `docs/managers/`.

    A change scoped to several managers is repeated verbatim on each of their
    pages, carrying no marker of the others: a reader is on one manager's page
    to read about that manager.

    ```{note}
    Released headings are not linkable: `myst_heading_slug_func` is
    `docutils.nodes.make_id`, which strips a heading holding no letter down to
    the empty string, so `` `7.5.0` (2026-08-03) `` yields no anchor at all.
    Each version therefore links to the comparison URL its own heading
    carries, which is parsed rather than guessed, exists for every release, and
    costs `linkcheck` nothing since the changelog page already cites it.
    ```
    """
    entries = _changelog_entries().get(manager_id, ())
    if not entries:
        return ""

    lines: list[str] = []
    releases = groupby(entries, key=lambda e: (e.version, e.date, e.url))
    for (version, date, url), shipped in releases:
        lines.append(f"- [`{version}`]({url}) ({date})")
        for entry in shipped:
            flag = f"**{entry.flag}:** " if entry.flag else ""
            lines.append(f"  - {flag}{entry.text}")
    return "\n".join(lines)


def managers_index_table() -> str:
    """Produce the manager index table of `docs/managers.md`.

    Rendered live at Sphinx build time. Both the name and the ID link to the
    manager's dedicated page, since a reader scanning for `apt-mint` looks at the
    identifier column, not the prose name. The `⚠️` marker of the readme's
    operation matrix gets a column of its own rather than trailing the ID, which
    kept a sort-worthy fact glued to an identifier. Platform icons follow the same
    coverage reading as the manager pages: a partially-backed group keeps its icon
    with {func}`_platform_coverage`'s annotation (`🐧 (Exherbo Linux only)`)
    instead of disappearing, as it does in the readme's all-or-nothing matrix.
    """
    table = []
    for mid, m in sorted(pool.items()):
        id_cell = f"[`{mid}`](managers/{mid}.md)"
        parts = []
        for p_obj in MAIN_PLATFORMS:
            coverage = _platform_coverage(p_obj, m.platforms)
            if coverage is None:
                continue
            icon, annotation = coverage
            parts.append(f"{icon} ({annotation})" if annotation else icon)
        # The artwork is spliced in after rendering: a multi-kilobyte SVG in a
        # cell would pad every other row of the column to its own width.
        table.append([
            f"%logo:{mid}%",
            f"[{m.name}](managers/{mid}.md)",
            id_cell,
            "⚠️" if m.unmaintained else "",
            " ".join(parts),
        ])
    rendered = render_table(
        table,
        # The mark column is headerless: the artwork labels itself, and the
        # managers whose upstream has no usable mark leave the cell empty.
        headers=["", "Manager", "ID", "Unmaintained", "Platforms"],
        table_format=TableFormat.GITHUB,
        colalign=["center", "left", "left", "center", "center"],
        disable_numparse=True,
    )
    for mid in pool:
        rendered = rendered.replace(f"%logo:{mid}%", manager_logo(mid, inline=True))
    return f"`mpm` can drive {len(pool)} package managers:\n\n{rendered}"


def manager_page_stub(manager_id: str) -> str:
    """Produce the committed stub of a manager's documentation page.

    The stub carries the page title and the section headings from
    {data}`MANAGER_SECTIONS`; every section body is a ``{python:render}`` block
    so the content renders live at Sphinx build time and never drifts from the
    pool. A section whose generator produces nothing for this manager (like
    reference traces for a manager documenting no literal output samples) is
    left out. The block
    formatting mirrors `docs/benchmark.md` so the stubs are an `mdformat`
    fixpoint.
    """
    m = pool[manager_id]
    blocks = [f"# {{octicon}}`package` {m.name}"]
    for title, func_name in MANAGER_SECTIONS:
        if not globals()[func_name](manager_id).strip():
            continue
        if title:
            blocks.append(f"## {title.format(manager_id=manager_id)}")
        blocks.append(
            "```{python:render}\n"
            f"from meta_package_manager._docs import {func_name}\n\n"
            f'print({func_name}("{manager_id}"))\n'
            "```",
        )
    return "\n\n".join(blocks) + "\n"
