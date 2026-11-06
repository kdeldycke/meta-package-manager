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

"""Render tests for Sphinx cross-references in the built documentation.

Build the docs once and assert against the real HTML that the generated summary
tables deep-link to the sections they describe, that each changelog release is
anchored on its version, that intersphinx references to Click resolve to the
upstream site, and that each sidebar icon of the stylesheet lands on its
entry. This catches drift the moment a `{click:config}` or `{click:tree}`
directive stops wiring its anchors, an `intersphinx_mapping` URL goes stale,
or a stylesheet selector names a link the build never writes, none of which a
mock-based test would notice.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from meta_package_manager import _docs

PROJECT_ROOT = Path(__file__).parent.parent

# The builder the Docs workflow deploys with. Building with it here is what
# lets a defect only its output shows fail a test, like a stylesheet keyed to
# the shape of its links.
SPHINX_BUILDER = tomllib.loads(
    (PROJECT_ROOT / "pyproject.toml").read_text(encoding="UTF-8"),
)["tool"]["repomatic"]["sphinx"]["builder"]

# The `docs` group declares `requires-python = ">= 3.14"` (see [tool.uv]), so it
# resolves nowhere else: below that, `uv run --group docs` installs nothing and
# `sphinx-build` is not on PATH. Building once on the newest supported Python
# also keeps this to a single full docs build across the CI matrix.
pytestmark = [
    pytest.mark.skipif(
        not sys.platform.startswith("linux"),
        reason="docs are built on Linux in CI",
    ),
    pytest.mark.skipif(
        sys.version_info < (3, 14),
        reason="build once on the newest supported Python",
    ),
    pytest.mark.skipif(
        shutil.which("uv") is None,
        reason="needs uv to build the docs",
    ),
    # The build installs the docs group as `uv.lock` pins it. The source
    # distribution ships no lockfile, so a packager running the suite from it
    # has nothing to build from.
    pytest.mark.skipif(
        not PROJECT_ROOT.joinpath("uv.lock").is_file(),
        reason="needs the lockfile of a repository checkout",
    ),
    # Sphinx crashes with a FileNotFoundError on searchindex.js.tmp when
    # concurrent builds share the same output directory (sphinx-doc/sphinx#13702).
    # Force all tests in this module onto a single xdist worker.
    pytest.mark.xdist_group("sphinx"),
]


@pytest.fixture(scope="module")
def built_docs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the documentation once and return its output directory.

    Builds into a throwaway directory (rather than `docs/_build`) so the run is
    hermetic and never clobbers a developer's local build.
    """
    out_dir = tmp_path_factory.mktemp("sphinx-html")
    subprocess.run(
        [
            "uv",
            "--no-progress",
            "run",
            "--frozen",
            "--group",
            "docs",
            "sphinx-build",
            "--builder",
            SPHINX_BUILDER,
            str(PROJECT_ROOT / "docs"),
            str(out_dir),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )
    return out_dir


def page_file(name: str) -> str:
    """Name the file the builder writes for the document *name*."""
    if SPHINX_BUILDER == "dirhtml" and name != "index":
        return f"{name}/index.html"
    return f"{name}.html"


def read_html(built_docs: Path, name: str) -> str:
    """Read the built HTML page of the document *name*."""
    html_path = built_docs / page_file(name)
    assert html_path.exists(), f"HTML file not found: {html_path}"
    return html_path.read_text(encoding="utf-8")


def test_changelog_releases_are_anchored_on_their_version(built_docs):
    """Each release of the changelog has an anchor made from its version.

    docutils reduces a release heading to nothing and numbers its section from
    a per-page counter, so `#id94` names another release after each new one.
    The `click_extra_release_anchors` setting of `docs/conf.py` gives that
    section `#v3-6-0` instead, and the release in preparation the anchor it ships
    with.
    """
    html = read_html(built_docs, "changelog")
    missing = [
        version
        for version in _docs.changelog_releases()
        if f'<section id="v{version.replace(".", "-")}">' not in html
    ]
    assert not missing, f"changelog releases with no version anchor: {missing}"


@pytest.mark.parametrize(
    ("page", "anchor"),
    (
        # The `{click:config} mpm` summary table, one row per option.
        *(
            ("configuration", option)
            for option in ("dry-run", "jobs", "stop-on-error", "timeout")
        ),
        # The `{click:tree} mpm` summary table, one row per command.
        *(
            ("cli-parameters", command)
            for command in ("mpm-install", "mpm-remove", "mpm-sync", "mpm-upgrade")
        ),
    ),
)
def test_summary_tables_link_to_their_sections(built_docs, page, anchor):
    """A summary table deep-links each option or command to its section."""
    html = read_html(built_docs, page)
    assert f'id="{anchor}"' in html, f"missing section anchor for {anchor}"
    assert f'href="#{anchor}"' in html, f"summary table does not link to {anchor}"


def test_intersphinx_click_resolves(built_docs):
    """Click cross-references resolve to the upstream documentation site.

    The links land on the API autodoc pages (typed CLI signatures), not the
    CLI-parameters page, so scan the whole build rather than a single page.
    """
    hits = [
        page.name
        for page in sorted(built_docs.rglob("*.html"))
        if "https://click.palletsprojects.com" in page.read_text(encoding="utf-8")
    ]
    assert hits, (
        "no intersphinx link to Click found in the built docs; "
        "the mapping may be broken"
    )


@pytest.mark.parametrize("page", ("index", "install", "managers/apk"))
def test_sidebar_icons_match_their_entries(built_docs, page):
    """Each sidebar icon of `custom.css` lands on its entry, at every depth.

    The stylesheet keys an icon to the href of a toctree entry. That href is
    relative to the page, so it gains a `../` per level of nesting, and the
    builder decides its suffix: `tests.html` under `html`, `tests/` under
    `dirhtml`. A selector naming a shape the build never writes draws no icon,
    and nothing else reports it.
    """
    css = (PROJECT_ROOT / "docs" / "_static" / "custom.css").read_text(
        encoding="UTF-8",
    )
    selectors = re.findall(
        r"^(\.sidebar-tree a\.reference\.internal.*)::before \{$",
        css,
        re.MULTILINE,
    )
    assert selectors, "no sidebar icon rule in custom.css"
    sidebar = read_html(built_docs, page).partition('class="sidebar-tree"')[2]
    hrefs = re.findall(
        r'<a class="reference internal" href="([^"]*)"',
        sidebar.partition("</div>")[0],
    )
    for selector in selectors:
        tests = re.findall(r'\[href(\$?=)"([^"]*)"\]', selector)
        matches = [
            href
            for href in hrefs
            if any(
                href.endswith(value) if operator == "$=" else href == value
                for operator, value in tests
            )
        ]
        assert len(matches) == 1, f"{selector} matches {matches} on {page}"
