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
import logging
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
        call("tap", tap_id, auto_post_args=False, auto_extra_args=False),
        call("trust", package_id, auto_extra_args=False),
    ]


@pytest.mark.parametrize("manager_class", (Brew, Cask))
def test_no_greedy_by_default(manager_class):
    """mpm passes no `--greedy` of its own: the user adds it per operation."""
    manager = manager_class()
    assert "--greedy" not in manager.upgrade_all_cli()


def test_extra_args_reach_their_own_command(monkeypatch):
    """`extra_args` set per operation reach the commands of that operation alone.

    A `--greedy` set through `post_args` reached `brew list`, which rejects it
    ([#2171](https://github.com/kdeldycke/meta-package-manager/issues/2171)). Set
    on `outdated` and `upgrade_all`, it joins `brew outdated` and `brew upgrade`,
    before the `--cask` selector, and leaves `brew list` alone. The `brew tap`
    and `brew trust` helpers of an install get none of the install's arguments.
    """
    manager = Cask()
    manager.operation_extra_args = {
        "install": ("--no-binaries",),
        "outdated": ("--greedy",),
        "upgrade_all": ("--greedy",),
    }
    commands: list[tuple[str, ...]] = []

    def record(*args, **kwargs):
        commands.append(tuple(map(str, args)))
        return ""

    monkeypatch.setattr(manager, "run", record)
    list(manager.installed)
    list(manager.outdated)
    manager.install("homebrew/cask-versions/firefox-developer-edition")
    upgrade_all = manager.upgrade_all_cli()

    listing, outdated, tap, trust, install = commands
    assert listing[-4:] == ("list", "--quiet", "--versions", "--cask")
    assert outdated[-4:] == ("outdated", "--json=v2", "--greedy", "--cask")
    assert tap[-2:] == ("tap", "homebrew/cask-versions")
    assert trust[-3:] == (
        "trust",
        "homebrew/cask-versions/firefox-developer-edition",
        "--cask",
    )
    assert install[-3:] == (
        "homebrew/cask-versions/firefox-developer-edition",
        "--no-binaries",
        "--cask",
    )
    assert upgrade_all[-5:] == ("upgrade", "--quiet", "--yes", "--greedy", "--cask")


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


@pytest.mark.parametrize(
    ("stderr", "hint"),
    (
        pytest.param(
            "Error: Cask 'macwhisper' is not installed.",
            "The Caskroom still holds a directory for macwhisper, which is not "
            "installed. Homebrew lists no cask while that directory remains. "
            "Remove it with `brew uninstall --cask --force macwhisper`.",
            id="stale-caskroom-directory",
        ),
        pytest.param(
            "Error: Cask 'macwhisper' is unavailable: No Cask with this name exists.",
            None,
            id="other-cask-error",
        ),
    ),
)
def test_installed_names_a_stale_caskroom_directory(monkeypatch, caplog, stderr, hint):
    """A cask listing that brew aborted relays the error, plus the fix when known."""
    caplog.set_level(logging.WARNING)
    cask = Cask()
    monkeypatch.setattr(cask, "cli_errors", [])
    monkeypatch.setattr(cask, "cli_path", Path("/opt/homebrew/bin/brew"), raising=False)
    monkeypatch.setattr(cask, "_spawn", lambda *args, **kwargs: (1, "", stderr))
    assert list(cask.installed) == []
    expected = [stderr] if hint is None else [stderr, hint]
    assert [record.getMessage() for record in caplog.records] == expected
