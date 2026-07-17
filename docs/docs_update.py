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

The Sphinx-only pages need no content regeneration script: ``docs/benchmark.md``
and ``docs/augmentations.md`` render their per-manager tables live at build time
through ``{python:render}`` directives calling :func:`benchmark_managers_table`
and :func:`augmentations_table`, each ``docs/managers/<id>.md`` page renders its
sections the same way through the ``manager_*`` generators, and the
``<!-- matrix ... -->`` compatibility blocks of ``docs/install.md`` are refreshed
by ``update-docs``'s own directive-refresh phase
(``click-extra refresh-directives``). Only the stub *file set* of
``docs/managers/`` is committed: :func:`update_manager_stubs` creates and deletes
stubs as managers join or leave the pool, while the page content stays
build-time.

.. warning::
    The generated Mermaid syntax targets the version bundled with
    ``sphinxcontrib-mermaid``, currently ``11.12.1``. See the hard-coded
    ``MERMAID_VERSION`` constant in `sphinxcontrib-mermaid's source
    <https://github.com/mgaitan/sphinxcontrib-mermaid/blob/master/sphinxcontrib/mermaid/__init__.py>`_.
    Avoid using Mermaid features introduced after that version.
"""

from __future__ import annotations

import inspect
import re
import sys
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
from meta_package_manager.specifier import PURL_MAP

# Version-gated TOML reader, following the same pattern as ``tests/conftest.py``.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARK_COMPETITORS = ("topgrade", "pacaptr", "pacapt", "sysget", "whohas")
"""Competing tools shown alongside ``mpm`` in the benchmark page, in column order."""

DOCS_SITE_URL = "https://kdeldycke.github.io/meta-package-manager"
"""Base URL of the published documentation site.

Used by :func:`operation_matrix` to link each manager ID of ``readme.md`` to its
documentation page: the readme renders on GitHub and PyPI, where relative Sphinx
links cannot resolve, so the links must be absolute.
"""

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

MANAGER_SECTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "manager_intro"),
    ("Platforms", "manager_platforms"),
    ("Operations", "manager_operations"),
    ("Ecosystem", "manager_ecosystem"),
    ("Usage", "manager_usage"),
    ("Command line", "manager_cli"),
    ("Privilege escalation", "manager_sudo"),
    ("Cooldown", "manager_cooldown"),
    ("Reference traces", "manager_traces"),
)
"""Layout of a per-manager documentation page: section title, generator function.

Single source of truth for :func:`manager_page_stub` and the structural tests.
Sections promote ``mpm`` usage first, then document ``mpm``'s preconceptions
about the native tool (its invocation, then the captured traces backing the
parsers). A section whose generator produces nothing for a given manager is
omitted from its stub.

The headings live in the committed stubs, never in the generated content: the
``{python:render}`` directive nested-parses its output into the surrounding
document, where MyST headings rely on fragile section reparenting. Every
generator listed here must therefore emit heading-free MyST.
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
            f"[`{mid}`]({DOCS_SITE_URL}/managers/{mid}.html)"
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

    Each manager identifier in the first column is rendered as a link: to its
    dedicated documentation page for implemented managers, or to its homepage
    from the YAML's ``homepages`` mapping for competitor-only managers. IDs
    without any known URL render as plain ``\\`code\\```.

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

    Managers needing no backfill at all are left out of the table. Each listed
    manager links to its dedicated documentation page.
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
            f"[`{mid}`](managers/{mid}.md)",
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


def _toml_definition(definition_source: str) -> dict:
    """Parse a bundled TOML definition file into its raw document."""
    return tomllib.loads(
        (PROJECT_ROOT / definition_source).read_text(encoding="UTF-8"),
    )


def _cooldown_status(manager_id: str) -> tuple[str, str, str] | None:
    """Extract a manager's row from the cooldown support table.

    The "Supported managers" table of ``docs/cooldown.md`` is the hand-curated
    source of truth for release-age gating: per manager, a status glyph, the
    native mechanism and an upstream reference. A row may cover several managers
    at once, its id cell listing each as a backticked code span (like the shared
    ``uv``/``uvx`` row). Returns the three cells with their markdown preserved
    (``—`` marks an empty cell), or ``None`` when the table has no row for the
    manager yet.
    """
    text = (PROJECT_ROOT / "docs" / "cooldown.md").read_text(encoding="UTF-8")
    section = text.partition("## Supported managers")[2].partition("\n## ")[0]
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if manager_id in re.findall(r"`([^`]+)`", cells[0]):
            return cells[1], cells[2], cells[3]
    return None


def _toml_definition_intro(definition_source: str) -> str | None:
    """Extract the description comment atop a bundled TOML definition.

    The TOML counterpart of a manager class docstring: each bundled file opens
    with a comment block describing the manager and its quirks. The boilerplate
    is stripped (the "Bundled package-manager definition" tag line and the
    schema/loader pointer), bare URLs are wrapped into autolinks, and paragraph
    breaks (lone ``#`` lines) are preserved. Returns ``None`` when nothing but
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


def manager_intro(manager_id: str) -> str:
    """Produce the lede of a manager's documentation page.

    Rendered live at Sphinx build time by the first ``{python:render}`` block of
    ``docs/managers/<id>.md``. Stacks, in order: a deprecation warning when the
    manager is deprecated, the manager class's own docstring (whose caveats and
    notes are otherwise only surfaced by the API docs), and a facts list (home
    page, source, version requirement).

    The class docstring is reST, so it is wrapped in an ``{eval-rst}`` block
    opened with a ``py:currentmodule`` directive so module-sibling
    cross-references resolve outside their autodoc context. Config-defined
    managers get the description comment atop their bundled TOML definition
    (:func:`_toml_definition_intro`) instead of their synthesized class
    docstring, with a pointer to the file as fallback.
    """
    m = pool[manager_id]
    blocks = []

    if m.deprecated:
        blocks.append(
            "```{warning}\n"
            f"`{manager_id}` is deprecated. See the "
            f"[deprecation notice]({m.deprecation_url}).\n"
            "```",
        )

    source_url = manager_source_url(manager_id)
    source_path = source_url.removeprefix(f"{GITHUB_BLOB_URL}/").partition("#")[0]

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
            "````{eval-rst}\n"
            f".. py:currentmodule:: {type(m).__module__}\n\n"
            f"{inspect.cleandoc(docstring)}\n"
            "````",
        )

    facts = [
        f"- Home page: <{m.homepage_url}>",
        f"- Source: [`{source_path}`]({source_url})",
    ]
    if m.requirement:
        facts.append(f"- Version requirement: `{m.requirement}`")
    blocks.append("\n".join(facts))

    return "\n\n".join(blocks)


def _platform_coverage(p_obj, platforms: frozenset) -> tuple[str, str | None] | None:
    """Return the icon and partial-coverage annotation of a platform entry.

    ``None`` when the manager covers no member of the entry. The annotation is
    ``None`` on full coverage, and otherwise spells out whichever side is
    shorter: the covered members (``Exherbo Linux only``) or the missing ones
    (``except WSL1, WSL2``), so a manager backing most of a large group stays
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
    """Produce the platform bullet list of a manager's documentation page.

    One line per supported :data:`~meta_package_manager.platforms.MAIN_PLATFORMS`
    entry, with :func:`_platform_coverage`'s annotation when the manager only
    backs part of a multi-platform group: the readme's operation matrix renders
    an all-or-nothing icon, this list is where partial support is spelled out.
    """
    m = pool[manager_id]
    lines = []
    for p_obj in MAIN_PLATFORMS:
        coverage = _platform_coverage(p_obj, m.platforms)
        if coverage is None:
            continue
        icon, annotation = coverage
        line = f"- {icon} {p_obj.name}"
        if annotation:
            line += f" ({annotation})"
        lines.append(line)
    return "\n".join(lines)


def manager_operations(manager_id: str) -> str:
    """Produce the operations table of a manager's documentation page.

    One row per member of :class:`~meta_package_manager.capabilities.Operations`,
    in enum order. The *Notes* column points out the capabilities ``mpm``
    synthesizes on top of the native CLI, mirroring the introspection of
    :func:`augmentations_table`, and is dropped entirely for the managers
    needing no backfill.
    """
    m = pool[manager_id]
    search_func = getattr(type(m), "search", None)
    table = []
    for op in Operations:
        supported = implements(m, op)
        note = ""
        if supported and op is Operations.upgrade_all and upgrade_all_is_synthesized(m):
            note = "[backfilled by `mpm`](../augmentations.md)"
        elif supported and op is Operations.search:
            missing = [
                label
                for label, native in (
                    ("exact", getattr(search_func, "exact_support", True)),
                    ("extended", getattr(search_func, "extended_support", True)),
                )
                if not native
            ]
            if missing:
                note = (
                    f"{' and '.join(missing)} search "
                    "[backfilled by `mpm`](../augmentations.md)"
                )
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

    Gives the version-probe block of the manager pages ``python`` highlighting
    (Pygments ships no standalone regex lexer). Falls back to ``repr()`` —
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
    """Produce the command-line section of a manager's documentation page.

    Documents how ``mpm`` drives the manager: binary names and lookup tweaks,
    the arguments and environment forced on every call, then the version probe
    and its parsing regexes. Beyond the always-shown CLI names and version
    probe, only non-default facts are listed. The argv fragments (pre-commands,
    forced arguments) are collated into single code spans, matching how they
    appear on the command line. Escalation and cooldown each have their own
    section (:func:`manager_sudo`, :func:`manager_cooldown`).

    Bundled TOML managers additionally show the version probe's captured
    ``[samples]`` output as a terminal transcript; the per-operation samples
    render in the reference-traces section (:func:`manager_traces`).
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

    version_sample = None
    source = getattr(m, "definition_source", None)
    if source:
        doc = _toml_definition(source)
        version_sample = doc.get("samples", {}).get("version", {}).get("output")

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


def manager_ecosystem(manager_id: str) -> str:
    """Produce the ecosystem section of a manager's documentation page.

    Lists the [purl](https://github.com/package-url/purl-spec) types the manager
    responds to (its own ID plus the ecosystem types mapped to it by
    :data:`~meta_package_manager.specifier.PURL_MAP`), and its Brewfile entry
    type when Homebrew Bundle's DSL covers it.
    """
    m = pool[manager_id]
    purl_types = sorted(
        {manager_id} | {t for t, ids in PURL_MAP.items() if ids and manager_id in ids},
    )
    types_list = ", ".join(f"`pkg:{t}`" for t in purl_types)
    lines = [
        "- Accepted [purl](https://github.com/package-url/purl-spec) types: "
        f"{types_list}",
    ]
    if m.brewfile_entry_type:
        lines.append(
            f"- Maps to `{m.brewfile_entry_type}` entries in "
            "[Brewfile backups](../dump.md)",
        )
    return "\n".join(lines)


def manager_usage(manager_id: str) -> str:
    """Produce the usage section of a manager's documentation page.

    A few ready-to-paste invocations targeting this manager alone, each gated on
    the operation being implemented, a ``--dry-run`` variant to try ``mpm``
    without touching the system, and pointers to the selection and configuration
    levers.
    """
    m = pool[manager_id]
    examples = [f"$ mpm --{manager_id} installed"]
    if implements(m, Operations.search):
        examples.append(f'$ mpm --{manager_id} search "query"')
    if implements(m, Operations.upgrade_all):
        examples.append(f"$ mpm --{manager_id} upgrade --all")
    if implements(m, Operations.install):
        examples.append(f"$ mpm install pkg:{manager_id}/hello")
    if implements(m, Operations.upgrade_all):
        examples.append(f"$ mpm --dry-run --{manager_id} upgrade --all")
    elif implements(m, Operations.install):
        examples.append(f"$ mpm --dry-run install pkg:{manager_id}/hello")
    fence = "```shell-session\n" + "\n".join(examples) + "\n```"

    dry_run = (
        "Every example above accepts [`--dry-run`](../augmentations.md), which "
        "simulates the underlying manager calls without touching the system: the "
        "safe way to watch what `mpm` would do before trusting it."
    )

    outro = (
        f"Deselect the manager for a single run with `--no-{manager_id}`, disable "
        "it from your [configuration](../configuration.md), or tune its invocation "
        "attributes with [per-manager overrides](../overrides.md)."
    )
    return f"{fence}\n\n{dry_run}\n\n{outro}"


def manager_sudo(manager_id: str) -> str:
    """Produce the privilege-escalation section of a manager's documentation page.

    States which escalation policy applies (system-wide ``sudo`` wrapping,
    internal escalation, or none) and how to flip it, deriving everything from
    the escalation attributes so the page can never contradict the code. For
    config-defined managers that do not escalate internally, the operations
    marked ``sudo = true`` in the bundled TOML definition are listed by name.
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
    of ``docs/cooldown.md`` (status, native mechanism, upstream reference), so
    the page and the cooldown overview can never diverge. Tops it with the
    enforcement facts derived from the manager's declarations: the injected
    environment variable when ``mpm`` drives a native gate, or the fail-closed
    skip applying to everyone else.
    """
    m = pool[manager_id]
    row = _cooldown_status(manager_id)

    parts = []
    if m.supports_cooldown:
        parts.append(
            "`mpm` natively enforces its [release-age cooldown](../cooldown.md) "
            f"on {m.name}, injecting the `{m.cooldown_env_var}` environment "
            "variable on every call.",
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
        if mechanism != "—":
            facts.append(f"- Mechanism: {mechanism}")
        if reference != "—":
            facts.append(f"- Reference: {reference}")
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

    The raw native outputs captured in the bundled TOML definition's
    ``[samples]`` fixtures, replayed as terminal transcripts: the reference
    ``mpm``'s parsers were written against. Surfacing them lets users seasoned
    in the native tool spot wrong assumptions, or output formats a newer
    release has since changed. Empty for managers without operation samples
    (the section is then omitted from the stub); the version probe transcript
    stays in the command-line section, next to the regexes consuming it.
    """
    m = pool[manager_id]
    source = getattr(m, "definition_source", None)
    if not source:
        return ""
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
    if not fences:
        return ""
    intro = (
        "Raw native outputs captured in the "
        f"[bundled definition]({manager_source_url(manager_id)}): the reference "
        f"`mpm`'s parsers were written against. If you know {m.name} well and a "
        "transcript below looks wrong, or a newer release changed its output "
        "format, [report it]"
        "(https://github.com/kdeldycke/meta-package-manager/issues)."
    )
    return "\n\n".join((intro, *fences))


def managers_index_table() -> str:
    """Produce the manager index table of ``docs/managers.md``.

    Rendered live at Sphinx build time. Each manager links to its dedicated
    documentation page, deprecated managers carry the same ``⚠️`` marker as the
    readme's operation matrix, and platform icons follow the same coverage
    reading as the manager pages: a partially-backed group keeps its icon with
    :func:`_platform_coverage`'s annotation (``🐧 (Exherbo Linux only)``)
    instead of disappearing, as it does in the readme's all-or-nothing matrix.
    """
    table = []
    for mid, m in sorted(pool.items()):
        id_cell = f"`{mid}`" + (
            "" if not m.deprecated else f" [⚠️]({m.deprecation_url})"
        )
        parts = []
        for p_obj in MAIN_PLATFORMS:
            coverage = _platform_coverage(p_obj, m.platforms)
            if coverage is None:
                continue
            icon, annotation = coverage
            parts.append(f"{icon} ({annotation})" if annotation else icon)
        table.append([f"[{m.name}](managers/{mid}.md)", id_cell, " ".join(parts)])
    rendered = render_table(
        table,
        headers=["Manager", "ID", "Platforms"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "center"],
        disable_numparse=True,
    )
    return f"`mpm` can drive {len(pool)} package managers:\n\n{rendered}"


def manager_page_stub(manager_id: str) -> str:
    """Produce the committed stub of a manager's documentation page.

    The stub carries the page title and the section headings from
    :data:`MANAGER_SECTIONS`; every section body is a ``{python:render}`` block
    so the content renders live at Sphinx build time and never drifts from the
    pool. A section whose generator produces nothing for this manager (like
    reference traces for class-based managers) is left out. The block
    formatting mirrors ``docs/benchmark.md`` so the stubs are an ``mdformat``
    fixpoint.
    """
    m = pool[manager_id]
    blocks = [f"# {{octicon}}`package` {m.name}"]
    for title, func_name in MANAGER_SECTIONS:
        if not globals()[func_name](manager_id).strip():
            continue
        if title:
            blocks.append(f"## {title}")
        blocks.append(
            "```{python:render}\n"
            f"from docs_update import {func_name}\n\n"
            f'print({func_name}("{manager_id}"))\n'
            "```",
        )
    return "\n\n".join(blocks) + "\n"


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

    Both layouts replicate ``pyproject-fmt``'s canonical style: inline arrays
    are padded with spaces inside the brackets, exploded arrays get a 2-space
    indent (``tomlkit``'s own ``multiline()`` hard-codes 4) and a trailing
    comma. Any deviation is churn: the ``format-pyproject`` autofix job would
    endlessly rewrite what the ``update-docs`` job regenerates.
    ``test_pyproject_updates_are_pyproject_fmt_fixpoint`` guards the match.
    """
    items = [tomlkit.item(value).as_string() for value in values]
    inline = f"[ {', '.join(items)} ]"
    # 78 preserves the historical 76-character budget of the unpadded form.
    if not multiline and len(inline) <= 78:
        return tomlkit.array(inline)
    body = "".join(f"  {item},\n" for item in items)
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


def update_manager_stubs() -> None:
    """Sync the committed page stubs of ``docs/managers/``.

    The directory is wholly owned by this function: one ``<id>.md`` stub per
    pool manager, nothing else. A stub is only rewritten when its content
    differs (keeping ``update-docs`` autofix diffs minimal), and stubs whose
    manager left the pool are deleted. ``test_manager_stubs_in_sync`` guards
    the contract.
    """
    stub_dir = PROJECT_ROOT / "docs" / "managers"
    stub_dir.mkdir(parents=True, exist_ok=True)

    expected = {mid: manager_page_stub(mid) for mid in pool.all_manager_ids}

    for stub in stub_dir.glob("*.md"):
        if stub.stem not in expected:
            stub.unlink()

    for mid, content in expected.items():
        stub = stub_dir / f"{mid}.md"
        if not stub.exists() or stub.read_text(encoding="UTF-8") != content:
            stub.write_text(content, encoding="UTF-8")


if __name__ == "__main__":
    update_keywords()
    update_labels()
    update_manager_stubs()
    update_readme()
