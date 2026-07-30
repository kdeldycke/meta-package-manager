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
tables deep-link to the sections they describe, and that intersphinx references
to Click resolve to the upstream site. This catches drift the moment a
`{click:config}` or `{click:tree}` directive stops wiring its anchors, or an
`intersphinx_mapping` URL goes stale, neither of which a mock-based test would
notice.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# The docs toolchain needs Python >= 3.12 (see docs/conf.py) and only pulls
# myst-parser 5.1 on 3.11+. Build once, on the newest supported Python, to keep
# this to a single full docs build across the CI matrix.
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
    # Sphinx crashes with a FileNotFoundError on searchindex.js.tmp when
    # concurrent builds share the same output directory (sphinx-doc/sphinx#13702).
    # Force all tests in this module onto a single xdist worker.
    pytest.mark.xdist_group("sphinx"),
]

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def built_docs(tmp_path_factory) -> Path:
    """Build the HTML documentation once and return its output directory.

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
            "html",
            str(PROJECT_ROOT / "docs"),
            str(out_dir),
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )
    return out_dir


def read_html(built_docs: Path, filename: str) -> str:
    """Read a built HTML page."""
    html_path = built_docs / filename
    assert html_path.exists(), f"HTML file not found: {html_path}"
    return html_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "option",
    (
        "dry-run",
        "jobs",
        "stop-on-error",
        "timeout",
    ),
)
def test_config_summary_links_to_option_sections(built_docs, option):
    """The `{click:config} mpm` summary table deep-links each option to its section."""
    html = read_html(built_docs, "configuration.html")
    assert f'id="{option}"' in html, f"missing section anchor for {option}"
    assert f'href="#{option}"' in html, f"summary table does not link to {option}"


@pytest.mark.parametrize(
    "command",
    (
        "mpm-install",
        "mpm-remove",
        "mpm-sync",
        "mpm-upgrade",
    ),
)
def test_cli_tree_links_to_command_sections(built_docs, command):
    """The `{click:tree} mpm` summary table deep-links each command to its section."""
    html = read_html(built_docs, "cli-parameters.html")
    assert f'id="{command}"' in html, f"missing section anchor for {command}"
    assert f'href="#{command}"' in html, f"summary table does not link to {command}"


def test_intersphinx_click_resolves(built_docs):
    """Click cross-references resolve to the upstream documentation site.

    The links land on the API autodoc pages (typed CLI signatures), not the
    CLI-parameters page, so scan the whole build rather than a single page.
    """
    hits = [
        page.name
        for page in sorted(built_docs.glob("*.html"))
        if "https://click.palletsprojects.com" in page.read_text(encoding="utf-8")
    ]
    assert hits, (
        "no intersphinx link to Click found in the built docs; "
        "the mapping may be broken"
    )
