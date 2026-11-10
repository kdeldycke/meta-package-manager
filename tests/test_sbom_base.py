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

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from textwrap import dedent

import pytest

from meta_package_manager.sbom.base import SBOM, writer_unavailable_reason
from meta_package_manager.summary import sbom_summary

# No module-level `importorskip` here on purpose, unlike every other SBOM test
# module: what this covers is the message shown when a writer library is missing or
# too old, so skipping it exactly when that is true would cover nothing.


def test_writer_unavailable_reason_separates_absent_from_outdated():
    """The two failure modes need opposite remedies, so they cannot share a message.

    A distribution shipping a writer library below the floor already satisfies
    `[sbom-offline]`, so telling its user to install that extra strands them: they
    install it again, nothing changes, and the only clue left is a symbol name belonging
    to no package they can name. NixOS carries exactly such a `cyclonedx-python-lib`.
    """
    absent = writer_unavailable_reason(
        "no-such-distribution", ImportError("No module named 'nope'")
    )
    assert "is not installed" in absent
    assert "--upgrade" not in absent

    # Any installed distribution stands in for the outdated case: the branch
    # turns on the distribution being present, not on which one it is. pytest is
    # installed wherever the suite runs, unlike mpm in a distribution's test phase.
    outdated = writer_unavailable_reason(
        "pytest",
        ImportError("cannot import name 'PredefinedLifecycle'"),
    )
    assert "is installed but too old" in outdated
    assert "PredefinedLifecycle" in outdated
    assert "--upgrade" in outdated


def test_spdx_names_a_missing_packageurl_python():
    """A missing packageurl-python disables the SPDX writer under its own name.

    spdx-tools does not depend on it, so an install can carry spdx-tools alone. A
    message calling spdx-tools too old would send the user to upgrade the wrong
    package. Runs in a fresh interpreter, where a blocked `packageurl` import and a
    hidden distribution stand for the missing one.
    """
    pytest.importorskip("spdx_tools")
    probe = dedent("""
        import sys
        from importlib import metadata

        sys.modules["packageurl"] = None
        installed_version = metadata.version


        def version(name):
            if name == "packageurl-python":
                raise metadata.PackageNotFoundError(name)
            return installed_version(name)


        metadata.version = version

        from meta_package_manager.sbom import spdx

        print(spdx.spdx_unavailable_reason)
    """)
    result = subprocess.run(
        (sys.executable, "-c", probe),
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=True,
    )
    assert result.stdout.startswith("packageurl-python is not installed."), (
        result.stdout
    )


class CannedStatsSBOM(SBOM):
    """A document reporting fixed statistics, to drive the summary adapter."""

    def __init__(self, stats: dict[str, object]) -> None:
        super().__init__()
        self.canned_stats = stats

    def stats(self) -> dict[str, object]:
        return self.canned_stats


@pytest.mark.parametrize(
    ("stats", "bundled", "notes"),
    (
        pytest.param(
            {"packages_per_manager": {"brew": 3}, "enriched_per_manager": {"brew": 2}},
            True,
            ["2/3 packages enriched with metadata."],
            id="enriched",
        ),
        pytest.param(
            {"packages_per_manager": {"brew": 3}, "enriched_per_manager": {"brew": 2}},
            False,
            [],
            id="minimal",
        ),
        pytest.param(
            {"merged_documents": 2, "transitive_packages_merged": 5},
            False,
            ["2 upstream SBOM documents merged, adding 5 transitive packages."],
            id="merged-with-transitive-packages",
        ),
        pytest.param(
            {"merged_documents": 1},
            False,
            ["1 upstream SBOM documents merged."],
            id="merged",
        ),
        pytest.param(
            {"external_bom_references": 4},
            False,
            ["4 per-package upstream SBOMs attached by reference."],
            id="bom-references",
        ),
        pytest.param(
            {"dependency_relationships": 6, "dependency_edges": 7},
            False,
            ["6 dependency relationships emitted.", "7 dependency edges emitted."],
            id="dependencies",
        ),
        pytest.param(
            {"vulnerabilities_total": 2, "vulnerable_packages": 1},
            False,
            ["2 vulnerabilities found across 1 packages."],
            id="vulnerabilities",
        ),
    ),
)
def test_sbom_summary_notes(stats, bundled, notes):
    """Each note appears when the run produced what it counts, and only then."""
    counts, rendered = sbom_summary(CannedStatsSBOM(stats), bundled)
    assert counts == Counter(stats.get("packages_per_manager", {}))
    assert rendered == notes


def test_all_purls_is_left_to_each_renderer():
    with pytest.raises(NotImplementedError):
        SBOM().all_purls()


def test_an_alias_equal_to_its_own_purl_is_not_indexed():
    """A coordinate cannot be an alias of itself."""
    sbom = SBOM()
    purl = "pkg:pypi/yt-dlp@2026.8.19"
    sbom.register_purl_aliases(purl, (purl,))
    assert sbom.primary_purls == {purl}
    assert sbom.purl_aliases == {}


def test_a_package_is_counted_once():
    """A renderer that records one package twice still counts it once."""
    sbom = SBOM()
    sbom._track_addition("pip", "yt-dlp", None)
    sbom._track_addition("pip", "yt-dlp", None)
    assert sbom.packages_per_manager == {"pip": 1}
