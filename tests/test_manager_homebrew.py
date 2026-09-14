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
"""Homebrew-specific tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import call, patch

import pytest

from meta_package_manager.managers.homebrew import Brew, Cask


@pytest.mark.parametrize(
    "package_id",
    (
        "wget",
        "ffmpeg",
        "python@3.14",
        "firefox",
    ),
)
@pytest.mark.parametrize("manager_class", (Brew, Cask))
def test_trust_tap_skips_core_packages(manager_class, package_id):
    """Core formulae and casks live on trusted taps and must not trigger trust."""
    manager = manager_class()
    with patch.object(manager, "run_cli") as run_cli:
        manager.trust_tap(package_id)
    run_cli.assert_not_called()


@pytest.mark.parametrize(
    "manager_class,package_id,tap_id",
    (
        (Brew, "gromgit/fuse/ntfs-3g-mac", "gromgit/fuse"),
        (Brew, "smudge/smudge/nightlight", "smudge/smudge"),
        (
            Cask,
            "homebrew/cask-versions/firefox-developer-edition",
            "homebrew/cask-versions",
        ),
    ),
)
def test_trust_tap_qualified_package(manager_class, package_id, tap_id):
    """Tap-qualified IDs are tapped (idempotent) and trusted before install."""
    manager = manager_class()
    with patch.object(manager, "run_cli") as run_cli:
        manager.trust_tap(package_id)
    assert run_cli.call_args_list == [
        call("tap", tap_id, auto_post_args=False),
        call("trust", package_id),
    ]


@pytest.mark.parametrize("manager_class", (Brew, Cask))
@pytest.mark.parametrize("ignore_auto_updates", (True, False))
def test_upgrade_all_cli_greedy_is_cask_only(manager_class, ignore_auto_updates):
    """--include-auto-updates adds --greedy to cask's upgrade-all command only.

    `brew upgrade` rejects `--greedy` alongside `--formula` (mutually
    exclusive options), so `brew` must never grow the flag.
    """
    manager = manager_class()
    manager.ignore_auto_updates = ignore_auto_updates
    cli = manager.upgrade_all_cli()
    assert "upgrade" in cli
    expect_greedy = not ignore_auto_updates and manager_class is Cask
    assert ("--greedy" in cli) is expect_greedy


@pytest.mark.parametrize("manager_class", (Brew, Cask))
def test_install_routes_through_trust_tap(manager_class):
    """install() always calls trust_tap() so the gate is uniform across paths."""
    manager = manager_class()
    with (
        patch.object(manager, "trust_tap") as trust_tap,
        patch.object(manager, "run_cli") as run_cli,
    ):
        manager.install("gromgit/fuse/ntfs-3g-mac")
    trust_tap.assert_called_once_with("gromgit/fuse/ntfs-3g-mac")
    run_cli.assert_called_once_with(
        "install",
        "--quiet",
        "gromgit/fuse/ntfs-3g-mac",
    )


def _write_formula_sbom(tmp_path, formula_name, external_refs, dep_refs=()):
    """Write a minimal `sbom.spdx.json` shaped like Homebrew's own.

    Only the fields {meth}`Homebrew._upstream_purls` reads are populated:
    the source package's `externalRefs`, plus an optional dependency
    package carrying refs of its own.
    """
    packages = [
        {
            "SPDXID": f"SPDXRef-Archive-{formula_name}-src",
            "name": formula_name,
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceLocator": locator,
                    "referenceType": "purl",
                }
                for locator in external_refs
            ],
        },
    ]
    if dep_refs:
        packages.append({
            "SPDXID": "SPDXRef-Package-openssl",
            "name": "openssl",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceLocator": locator,
                    "referenceType": "purl",
                }
                for locator in dep_refs
            ],
        })
    sbom_file = tmp_path / "sbom.spdx.json"
    sbom_file.write_text(json.dumps({"packages": packages}), encoding="UTF-8")
    return sbom_file


@pytest.mark.parametrize(
    ("external_refs", "expected"),
    (
        pytest.param(
            ("pkg:brew/yt-dlp@2026.8.19", "pkg:pypi/yt-dlp@2026.8.19"),
            ("pkg:pypi/yt-dlp@2026.8.19",),
            id="registry-purl-beside-the-brew-one",
        ),
        pytest.param(
            ("pkg:brew/actionlint@1.7.12",),
            (),
            id="no-registry-source",
        ),
        pytest.param(
            (
                "pkg:brew/pi-coding-agent@0.85.1",
                "pkg:npm/%40earendil-works/pi-coding-agent@0.85.1",
            ),
            ("pkg:npm/%40earendil-works/pi-coding-agent@0.85.1",),
            id="percent-encoded-npm-namespace",
        ),
        pytest.param(
            ("pkg:brew/homebrew%2Fcore/wget@1.25.0",),
            (),
            id="tap-qualified-brew-purl-is-still-a-brew-purl",
        ),
        pytest.param(
            ("pkg:brew/ty@0.0.79", "not-a-purl", "pkg:pypi/ty@0.0.79"),
            ("pkg:pypi/ty@0.0.79",),
            id="unparseable-locator-skipped",
        ),
    ),
)
def test_upstream_purls_reads_the_source_package(tmp_path, external_refs, expected):
    """Only non-brew purls on the source package are lifted."""
    sbom_file = _write_formula_sbom(tmp_path, "pkg", external_refs)
    purls = Brew._upstream_purls(sbom_file, "pkg")
    assert tuple(p.to_string() for p in purls) == expected


def test_upstream_purls_ignores_dependency_packages(tmp_path):
    """A dependency's own coordinate must not be attributed to the formula."""
    sbom_file = _write_formula_sbom(
        tmp_path,
        "curl",
        ("pkg:brew/curl@8.9.0",),
        dep_refs=("pkg:brew/openssl@3.3.1", "pkg:generic/openssl@3.3.1"),
    )
    assert Brew._upstream_purls(sbom_file, "curl") == ()


@pytest.mark.parametrize(
    ("sbom_path", "formula_name"),
    (
        pytest.param(None, "curl", id="no-sbom-file"),
        pytest.param(Path("/nonexistent/sbom.spdx.json"), "curl", id="unreadable"),
        pytest.param(Path("/nonexistent/sbom.spdx.json"), None, id="no-formula-name"),
    ),
)
def test_upstream_purls_degrades_to_empty(sbom_path, formula_name):
    """A missing or unreadable document costs coverage, never an error."""
    assert Brew._upstream_purls(sbom_path, formula_name) == ()


def test_upstream_purls_tolerates_malformed_json(tmp_path):
    """A truncated upstream document must not abort the whole scan."""
    sbom_file = tmp_path / "sbom.spdx.json"
    sbom_file.write_text('{"packages": [', encoding="UTF-8")
    assert Brew._upstream_purls(sbom_file, "curl") == ()
