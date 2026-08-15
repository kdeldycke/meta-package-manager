from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import tomllib  # type: ignore[import-not-found]  # stdlib >=3.11; docs require >=3.12.

project_path = Path(__file__).parent.parent.resolve()

# Fetch general information about the project from pyproject.toml.
toml_path = project_path / "pyproject.toml"
toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))

# Redistribute pyproject.toml config to Sphinx.
project_id = toml_config["project"]["name"]
version = release = toml_config["project"]["version"]
url = toml_config["project"]["urls"]["Homepage"]
author = ", ".join(author["name"] for author in toml_config["project"]["authors"])

# Canonical origin of the published site, read from the one place that declares
# it. Sphinx wants a trailing slash: it joins page paths onto this verbatim to
# build the <link rel="canonical"> of every page, and sphinx-sitemap builds the
# sitemap URLs the same way. The declaration itself stays slash-less so runtime
# consumers can append rooted paths.
docs_site_url = toml_config["project"]["urls"]["Documentation"].rstrip("/") + "/"

# Title-case each word of the project ID.
project = " ".join(word.title() for word in project_id.split("-"))

# GitHub account owning the project. Factored out so a rename touches one line
# instead of every URL built from it below (repository, sponsors, social card).
github_user = "kdeldycke"

# Whole years since `1.0.0` (2016-07-05), the oldest entry of the changelog, for
# the announcement banner below. Floored, so the figure is never ahead of the
# anniversary it claims.
maintained_years = (datetime.now(tz=UTC).date() - date(2016, 7, 5)).days // 365

# Addons.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    # Adds a copy button to code blocks.
    "sphinx_copybutton",
    "sphinx_design",
    # Emits sitemap.xml from html_baseurl, so crawlers get the 81 manager pages
    # as a list instead of having to discover them by following links.
    "sphinx_sitemap",
    "sphinxext.opengraph",
    "myst_parser",
    # Docstrings are written in MyST markdown, transparently converted back to
    # reST at build time so sphinx.ext.autodoc and sphinx_autodoc_typehints
    # keep working unmodified. Must be listed before sphinx_autodoc_typehints:
    # both hook autodoc-process-docstring, and the conversion must run first.
    "click_extra.sphinx.myst_docstrings",
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
    # Render GitHub-style alerts (`> [!NOTE]`, `> [!WARNING]`, ...) as
    # admonitions. Native to myst-parser >= 5.1, which click-extra's converter
    # defers to from that version on; uv resolves 5.1 on Python 3.11+ and the
    # docs build runs on >= 3.12.
    "alert",
    "attrs_block",
    "attrs_inline",
    # Lets admonitions nest inside backtick-fenced directives (like `{tab-item}`
    # in `install.md`) without escalating fence backtick counts.
    "colon_fence",
    "deflist",
    "replacements",
    "smartquotes",
    "strikethrough",
    "tasklist",
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

exclude_patterns = ["_build", "_linkcheck", "html", "Thumbs.db", ".DS_Store"]

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
# Browser-tab icon: the icon-only, tight-cropped favicon (no wordmark).
html_favicon = "assets/favicon.svg"
# Emits <link rel="canonical"> on every page, and is what sphinx-sitemap builds
# its URLs from. Without it each manager page is reachable at both the
# github.io origin and the custom domain with nothing telling crawlers which
# one counts, and the vanity `<manager>.mpm.run` redirects would land on pages
# that fail to name their own canonical.
html_baseurl = docs_site_url
# Absolute base URL for OpenGraph. sphinxext.opengraph resolves og:image
# against it, so social crawlers can follow the image instead of a relative
# path they cannot resolve.
ogp_site_url = docs_site_url
# Social-card image (og:image), served from the GitHub raw host like the readme
# banner and screenshots: docs/assets/ is not copied into the built site (only
# the two sidebar logos are named in html_static_path), so a site-relative path
# would 404 for crawlers.
ogp_image = (
    f"https://raw.githubusercontent.com/{github_user}/"
    f"{project_id}/main/docs/assets/banner-social-light.png"
)
ogp_image_alt = project
html_theme_options = {
    # Sidebar logo. Furo renders this pair as .only-light/.only-dark images
    # driven by its own theme state, so the logo follows the toggle. A single
    # html_logo cannot: assets/logo-square.svg is light-only by convention, and
    # its dark navy wordmark drops to a 1.35:1 contrast ratio on the dark theme.
    # Both files are 640x640 exports of that SVG, so the swap holds geometry.
    # Furo resolves them against _static/, hence their html_static_path entries.
    "light_logo": "logo-square-light.png",
    "dark_logo": "logo-square-dark.png",
    "sidebar_hide_name": True,
    # Activates edit links.
    "source_repository": f"https://github.com/{github_user}/{project_id}",
    "source_branch": "main",
    "source_directory": "docs/",
    # Sits atop every page, so it stays a single line and leads with the track
    # record rather than pleading scarcity: how thin the maintenance is says
    # nothing to a reader who has not yet decided the project is worth funding.
    # The age is recomputed at build time, so the claim never goes stale. Each
    # call to action opens on its emoji, which gives the eye two markers to land
    # on in a line that is otherwise unbroken prose.
    "announcement": (
        f"{project} has been maintained for {maintained_years}+ years, and is "
        "free to use. You can help if you "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "🤝 purchase business support</a></strong> or "
        "<strong><a class='reference external' "
        f"href='https://github.com/sponsors/{github_user}'>"
        "🫶 sponsor the project</a></strong>."
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
    # GitHub fragment anchors are rendered client-side and not visible to linkcheck.
    r"https://github\.com/kdeldycke/click-extra#",
    # GitHub README tab fragments are rendered client-side.
    r"https://github\.com/.+\?tab=readme-ov-file#",
    # The unversioned `releases/latest/download/<file>` URLs of the readme's
    # Executables table do resolve: every release publishes those aliases beside
    # the versioned `meta-package-manager-<version>-<platform>-<arch>.<ext>`
    # artifacts. They are skipped for the throttling budget described below.
    r"https://github\.com/kdeldycke/meta-package-manager/releases/latest/download/.*",
    # The per-manager source links generated into the benchmark and augmentations
    # tables (one `blob/main` link per manager) are guarded by the table-render
    # tests and re-verified authenticated by lychee in the same CI job. Sphinx's
    # unauthenticated crawl gets throttled by GitHub to ~1 request per minute,
    # which overruns the link-check job budget.
    r"https://github\.com/kdeldycke/meta-package-manager/blob/",
    # Same budget, same guard: the tracker search each manager card links its
    # label to. A label search always answers 200, empty or not, so there is
    # nothing for linkcheck to catch here anyway.
    r"https://github\.com/kdeldycke/meta-package-manager/issues\?q=",
    # The upstream badges of the manager pages: a dozen per page over a hundred
    # pages, all served by shields.io, which answers an image to any query it
    # understands. A broken badge is a wrong forge path rather than a dead link,
    # which is what the badge catalogue tests check instead.
    r"https://img\.shields\.io/",
]

# Retry transiently-unreachable hosts before reporting them broken, so a flaky
# but valid link stays checked instead of being moved to linkcheck_ignore.
linkcheck_retries = 3

# Footer content.
html_last_updated_fmt = "%Y-%m-%d"
copyright = f"{author} and contributors"
html_show_sphinx = False

# Individual files are copied to the root of _static/, which is where Furo looks
# for the light_logo/dark_logo pair. Listing docs/assets/ wholesale would drag
# the screenshots, the dependency graph and the binary scan reports along.
html_static_path = [
    "_static",
    "assets/logo-square-dark.png",
    "assets/logo-square-light.png",
]
# Copied verbatim to the site root, where crawlers expect it. `html_static_path`
# would bury it under `_static/`, which robots.txt cannot be served from.
html_extra_path = ["robots.txt"]
# sphinx-sitemap defaults to a `{lang}{version}{link}` layout meant for sites
# publishing several translations or versions side by side. This one publishes a
# single tree, so anything but the bare link yields sitemap entries that 404.
sitemap_url_scheme = "{link}"
html_css_files = ["custom.css", "table-crosshair.css"]
html_js_files = ["table-crosshair.js"]

# Opt into click_extra.sphinx's executable directives. Enables the `click:run`
# blocks in docs/cli-parameters.md and docs/configuration.md, which run mpm's CLI
# at build time to render live --help and --params output. These directives
# execute Python during the build; mpm's own docs are the only trusted source, so
# the opt-in stays scoped to this project.
click_extra_enable_exec_directives = True

# Render the mpm Click command tree as roff .1 pages alongside the HTML build.
# Picked up by click_extra.sphinx, which writes one page per (sub)command into
# <outdir>/man/, and (when mandoc or groff is on PATH) a browser-viewable
# .html sibling next to each .1. See
# https://mpm.run/man/.
click_extra_manpages = [
    {"script": "meta_package_manager.cli:mpm", "prog_name": "mpm"},
]

# Wire Sphinx's standard manpage role to the HTML siblings generated above.
# Lets docstrings reference subcommands as {manpage}`mpm-install(1)` and
# render them as proper hyperlinks in the docs.
manpages_url = "man/{page}.{section}.html"
