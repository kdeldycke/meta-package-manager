from __future__ import annotations

import sys
from pathlib import Path

import tomllib  # type: ignore[import-not-found]  # stdlib >=3.11; docs require >=3.12.

project_path = Path(__file__).parent.parent.resolve()

# Make this docs directory importable so the `{python:render}` block in
# benchmark.md can call the table generator in docs_update.py at build time.
sys.path.insert(0, str(Path(__file__).parent))

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["project"]["name"]
version = release = toml_config["project"]["version"]
url = toml_config["project"]["urls"]["Homepage"]
author = ", ".join(author["name"] for author in toml_config["project"]["authors"])

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    "sphinx_design",
    "sphinxext.opengraph",
    "myst_parser",
    "sphinx.ext.autosectionlabel",
    "sphinx_autodoc_typehints",
    "click_extra.sphinx",
    "sphinxcontrib.mermaid",
    # jQuery must be listed explicitly: sphinx-datatables only activates it
    # from a html-page-context callback, too late for the jquery.js static
    # file to be registered and copied, leaving `$` undefined at runtime.
    "sphinxcontrib.jquery",
    "sphinx_datatables",
]

# https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
myst_enable_extensions = [
    "attrs_block",
    "attrs_inline",
    "deflist",
    "replacements",
    "smartquotes",
    "strikethrough",
    "tasklist",
    # Lets admonitions nest inside backtick-fenced directives (like `{tab-item}`
    # in `install.md`) without escalating fence backtick counts.
    "colon_fence",
]
# Allow ```mermaid``` directive to be used without curly braces (```{mermaid}```), see:
# https://github.com/mgaitan/sphinxcontrib-mermaid/issues/99#issuecomment-2339587001
myst_fence_as_directive = ["mermaid"]

# Register every heading as a resolvable cross-reference target so in-page
# `[text](#anchor)` links resolve (and broken ones warn) at build time, making
# Sphinx the authority for internal anchors. The slug function is pinned to
# docutils' `make_id` so MyST anchors match the section IDs docutils already
# emits, keeping existing anchor URLs stable. Mirrors the upstream repomatic
# docs configuration.
myst_heading_anchors = 6
myst_heading_slug_func = "docutils.nodes.make_id"

mermaid_d3_zoom = True

# Applies to every table carrying the (default) `sphinx-datatable` class:
# currently only the binaries catalog. An empty `order` preserves the CSV's
# newest-first row order on load instead of DataTables' default first-column
# ascending sort; the page length accommodates one release's worth of
# binaries per page with room to spare. The render callback appends a
# relative hint ("9 days ago") to the Released column (index 2 in
# repomatic.binaries_page.CSV_HEADERS) at display time only, so sorting and
# searching keep operating on the raw ISO dates and the generated CSV stays
# free of hints that would go stale between releases. Passed as a raw JS
# string because a JSON dict cannot carry the function. Raw string: the JS
# regex's backslashes are not Python escapes.
datatables_options = r"""
{
    "order": [],
    "pageLength": 25,
    "columnDefs": [
        {
            "targets": 2,
            "render": function (data, type, row) {
                if (type !== "display" || !data) {
                    return data;
                }
                // Cells arrive as rendered HTML (<p>2026-07-02</p>), so
                // extract the date instead of parsing the markup.
                const match = /\d{4}-\d{2}-\d{2}/.exec(data);
                if (!match) {
                    return data;
                }
                const days = Math.floor(
                    (Date.now() - Date.parse(match[0])) / 86400000);
                if (!isFinite(days)) {
                    return data;
                }
                let hint;
                if (days <= 0) {
                    hint = "today";
                } else if (days === 1) {
                    hint = "a day ago";
                } else if (days < 30) {
                    hint = days + " days ago";
                } else if (days < 350) {
                    const months = Math.round(days / 30.44);
                    hint = months === 1 ? "a month ago" : months + " months ago";
                } else {
                    const years = Math.round(days / 365.25);
                    hint = years === 1 ? "a year ago" : years + " years ago";
                }
                // Inject inside the paragraph so the hint stays on the
                // same line as the date.
                const label = " (" + hint + ")";
                return data.includes("</p>")
                    ? data.replace("</p>", label + "</p>")
                    : data + label;
            }
        }
    ]
}
"""

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

nitpicky = True

# Concatenates the docstrings of the class and the __init__ method.
autoclass_content = "both"
# Keep the same ordering as in original source code.
autodoc_member_order = "bysource"
always_use_bars_union = True

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "click": ("https://click.palletsprojects.com", None),
    "click-extra": ("https://kdeldycke.github.io/click-extra", None),
}

# Prefix document path to section labels, to use:
# `path/to/file:heading` instead of just `heading`
autosectionlabel_prefix_document = True

# Theme config.
html_theme = "furo"
html_title = project
html_logo = "assets/logo-square.svg"
html_theme_options = {
    "sidebar_hide_name": True,
    # Activates edit links.
    "source_repository": f"https://github.com/kdeldycke/{project_id}",
    "source_branch": "main",
    "source_directory": "docs/",
    "announcement": (
        f"{project} works fine, but is <em>maintained by only one person</em> "
        "😶‍🌫️.<br/>You can help if you "
        "<strong><a class='reference external' "
        "href='https://github.com/sponsors/kdeldycke'>"
        "purchase business support 🤝</a></strong> or "
        "<strong><a class='reference external' "
        "href='https://github.com/sponsors/kdeldycke'>"
        "sponsor the project 🫶</a></strong>."
    ),
}

# GitHub renders issue comments, README tab anchors, blob line anchors and
# commit-diff anchors with JavaScript, so the linkcheck builder cannot find
# them in the static HTML.
linkcheck_anchors_ignore = [
    r"issuecomment-\d+",
    r"readme",
    r"L\d+",
    r"diff-[0-9a-f]+",
]

# GitHub markdown READMEs and CONTRIBUTING files render their heading anchors
# client-side, so linkcheck can't validate any fragment on github.com pages.
linkcheck_anchors_ignore_for_url = [
    r"https://github\.com/.+",
]

linkcheck_ignore = [
    # These sites return 403/418/429/timeout to bots but are valid.
    r"https://claude\.ai/",
    r"https://devkitpro\.org",
    r"https://docs\.chocolatey\.org/",
    r"https://en\.opensuse\.org/",
    r"https://git\.yoctoproject\.org/",
    r"https://gitlab\.alpinelinux\.org/",
    r"https://gitlab\.manjaro\.org/",
    r"https://guix\.gnu\.org",
    r"https://liberapay\.com",
    r"https://medium\.com/",
    r"https://ohmybash\.nntoan\.com",
    r"https://openclipart\.org/",
    r"http://www\.slackware\.com/",
    r"https://www\.bitdefender\.com/",
    r"https://www\.gnu\.org/software/",
    r"https://www\.npmjs\.com",
    r"https://(www\.)?patreon\.com",
    r"https://www\.tug\.org/",
    # star-history.com renders chart fragments client-side.
    r"https://star-history\.com/",
    # GitHub fragment anchors are rendered client-side and not visible to linkcheck.
    r"https://github\.com/kdeldycke/click-extra#",
    # GitHub README tab fragments are rendered client-side.
    r"https://github\.com/.+\?tab=readme-ov-file#",
    # The unversioned `releases/latest/download/<file>` URLs in the Executables
    # table 404 until the release workflow publishes unversioned aliases. The
    # versioned `mpm-<version>-<platform>-<arch>.<ext>` artifacts do exist on
    # every release.
    r"https://github\.com/kdeldycke/meta-package-manager/releases/latest/download/.*",
    # The per-manager source links generated into the benchmark and augmentations
    # tables (one `blob/main` link per manager) are guarded by the table-render
    # tests and re-verified authenticated by lychee in the same CI job. Sphinx's
    # unauthenticated crawl gets throttled by GitHub to ~1 request per minute,
    # which overruns the link-check job budget.
    r"https://github\.com/kdeldycke/meta-package-manager/blob/",
]

# Footer content.
html_last_updated_fmt = "%Y-%m-%d"
copyright = f"{author} and contributors"
html_show_sphinx = False

html_static_path = ["_static"]
html_css_files = ["custom.css", "table-crosshair.css"]
html_js_files = ["table-crosshair.js"]

# Opt into click_extra.sphinx's executable directives. Enables the ``click:run``
# blocks in docs/cli-parameters.md and docs/configuration.md, which run mpm's CLI
# at build time to render live --help and --params output. These directives
# execute Python during the build; mpm's own docs are the only trusted source, so
# the opt-in stays scoped to this project.
click_extra_enable_exec_directives = True

# Render the mpm Click command tree as roff .1 pages alongside the HTML build.
# Picked up by click_extra.sphinx, which writes one page per (sub)command into
# <outdir>/man/, and (when mandoc or groff is on PATH) a browser-viewable
# .html sibling next to each .1. See
# https://kdeldycke.github.io/meta-package-manager/man/.
click_extra_manpages = [
    {"script": "meta_package_manager.cli:mpm", "prog_name": "mpm"},
]

# Wire Sphinx's standard :manpage: role to the HTML siblings generated above.
# Lets docstrings reference subcommands as ``:manpage:`mpm-install(1)``` and
# render them as proper hyperlinks in the docs.
manpages_url = "man/{page}.{section}.html"
