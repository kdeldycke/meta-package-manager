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
from typing import Any
from unittest.mock import call, patch

import pytest

from meta_package_manager.execution import CLIError
from meta_package_manager.managers.homebrew import Brew, Cask
from meta_package_manager.package import (
    EMPTY_METADATA,
    Checksum,
    ChecksumAlgorithm,
    Dependency,
    DependencyScope,
    PackageMetadata,
    Supplier,
)


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


# Records of `brew info --json=v2`, as Homebrew `7.0.10` printed them on macOS arm64,
# trimmed to the keys the metadata parsers read. Every kept value is verbatim. The
# `ncar-ncl` record comes from `brew info --json=v2 --cask ncar-ncl`: no installed
# cask of that host depended on another cask or on a formula.

CURL_BOTTLE_SHA256 = "16b951fa8ecede2c254441c26e34814fed37c1e97382dad3016012aa2cbf20ac"

CURL_FORMULA: dict[str, Any] = {
    "name": "curl",
    "full_name": "curl",
    "tap": "homebrew/core",
    "oldnames": ["wcurl"],
    "aliases": [],
    "desc": "Get a file from an HTTP, HTTPS or FTP server",
    "license": "curl",
    "homepage": "https://curl.se",
    "versions": {"stable": "8.23.0"},
    "urls": {"stable": {"url": "https://curl.se/download/curl-8.23.0.tar.bz2"}},
    "keg_only": True,
    "keg_only_reason": {"reason": ":provided_by_macos", "explanation": ""},
    "dependencies": [
        "brotli",
        "libnghttp2",
        "libnghttp3",
        "libngtcp2",
        "libpsl",
        "libssh2",
        "openssl@4",
        "zstd",
    ],
    "build_dependencies": ["pkgconf"],
    "test_dependencies": ["pkgconf"],
    "optional_dependencies": [],
    "recommended_dependencies": [],
    "bottle": {
        "stable": {"files": {"arm64_golden_gate": {"sha256": CURL_BOTTLE_SHA256}}}
    },
    "installed": [
        {"version": "8.23.0", "installed_on_request": True, "poured_from_bottle": True},
    ],
}

GIT_DELTA_FORMULA: dict[str, Any] = {
    "name": "git-delta",
    "full_name": "git-delta",
    "aliases": ["delta"],
    "oldnames": [],
    "desc": "Syntax-highlighting pager for git and diff output",
}

NIGHTLIGHT_FORMULA: dict[str, Any] = {
    "name": "nightlight",
    "full_name": "smudge/smudge/nightlight",
    "aliases": [],
    "oldnames": [],
    "desc": "A CLI for configuring 'Night Shift' on macOS 🌕🌖🌗🌘🌑",
}

TY_FORMULA: dict[str, Any] = {
    "name": "ty",
    "full_name": "ty",
    "tap": "homebrew/core",
    "desc": "Extremely fast Python type checker, written in Rust",
    "license": "MIT",
    "homepage": "https://docs.astral.sh/ty/",
    "versions": {"stable": "0.0.91"},
    "build_dependencies": ["rust"],
    "installed": [
        {"version": "0.0.90", "installed_on_request": True, "poured_from_bottle": True},
    ],
}

ADGUARD_CASK: dict[str, Any] = {
    "token": "adguard",
    "full_token": "adguard",
    "tap": "homebrew/cask",
    "name": ["AdGuard"],
    "desc": "Stand alone ad blocker",
    "homepage": "https://adguard.com/",
    "url": "https://static.adguard.com/mac/release/AdGuard-2.20.2.2629.dmg",
    "sha256": "735aab5f60baa115fc238b2b91d1f8571b00309a8ed71797ff38ed114faba7b0",
    "auto_updates": True,
    "depends_on": {"macos": {">=": ["12"]}},
}

DISK_DRILL_CASK: dict[str, Any] = {
    "token": "disk-drill",
    "full_token": "disk-drill",
    "tap": "homebrew/cask",
    "name": ["Disk Drill"],
    "desc": "Data recovery software",
    "homepage": "https://www.cleverfiles.com/",
    "url": "https://dl.cleverfiles.com/diskdrill.dmg",
    "sha256": "no_check",
    "auto_updates": True,
    "depends_on": {"macos": {}},
}

NCAR_NCL_CASK: dict[str, Any] = {
    "token": "ncar-ncl",
    "full_token": "ncar-ncl",
    "tap": "homebrew/cask",
    "name": ["NCAR Command Language", "ncl"],
    "desc": "Interpreted language for scientific data analysis and visualization",
    "homepage": "https://www.ncl.ucar.edu/",
    "url": (
        "https://www.earthsystemgrid.org/api/v1/dataset/ncl.662.dap/file/"
        "ncl_ncarg-6.6.2-MacOS_10.14_64bit_gnu730.tar.gz"
    ),
    "sha256": "e2cd644f6b1bb41f55480b8818319e60c450998e31e5e489c69a5e84f3d1f359",
    "auto_updates": None,
    "depends_on": {"cask": ["xquartz"], "formula": ["gcc"], "macos": {}},
}

CASK_SUPPLIER = Supplier(
    name="Homebrew Cask", url="https://github.com/Homebrew/homebrew-cask"
)


def _stub_brew(monkeypatch, manager, info, prefix):
    """Answer the two `brew` calls of the metadata batch without spawning `brew`.

    `brew --prefix` prints `prefix`, or nothing when it is `None`. `brew info
    --json=v2 --installed` prints `info` encoded as JSON, or verbatim when it is
    text already, and raises it when it is an exception. Linux and Windows runners
    have no `brew`: the stub is what lets these tests run there.
    """

    def run_cli(*args, **kwargs):
        if args == ("--prefix",):
            return f"{prefix or ''}\n"
        assert args == ("info", "--json=v2", "--installed")
        if isinstance(info, Exception):
            raise info
        return info if isinstance(info, str) else json.dumps(info)

    monkeypatch.setattr(manager, "run_cli", run_cli)


@pytest.mark.parametrize(
    ("output", "prefix"),
    (
        pytest.param("/opt/homebrew\n", Path("/opt/homebrew"), id="apple-silicon"),
        pytest.param(
            "/home/linuxbrew/.linuxbrew\n",
            Path("/home/linuxbrew/.linuxbrew"),
            id="linux",
        ),
        pytest.param("\n", None, id="no-output"),
        pytest.param(CLIError(1, "", ""), None, id="failed-call"),
    ),
)
def test_brew_prefix(monkeypatch, output, prefix):
    """`brew --prefix` locates the Cellar, and a failed call leaves it unknown.

    The `--formula` and `--cask` selectors stay off the command: they would ask
    for the prefix of a package instead of the prefix of Homebrew.
    """
    manager = Brew()

    def run_cli(*args, **kwargs):
        assert args == ("--prefix",)
        assert kwargs == {
            "auto_post_args": False,
            "auto_extra_args": False,
            "must_succeed": True,
        }
        if isinstance(output, Exception):
            raise output
        return output

    monkeypatch.setattr(manager, "run_cli", run_cli)
    assert manager._brew_prefix == prefix


def test_package_metadata_batch_skips_an_empty_inventory(monkeypatch):
    """No package to enrich means no `brew info` call."""
    manager = Brew()
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: pytest.fail("brew ran for an empty inventory"),
    )
    assert list(manager.package_metadata_batch([])) == []


@pytest.mark.parametrize(
    "info",
    (
        pytest.param(CLIError(1, "", ""), id="failed-call"),
        pytest.param(
            json.dumps({"formulae": [CURL_FORMULA], "casks": []})[:200],
            id="truncated-json",
        ),
        pytest.param("", id="no-output"),
    ),
)
def test_package_metadata_batch_degrades_to_empty(monkeypatch, tmp_path, info):
    """A `brew info` that fails or answers no record leaves every package bare."""
    manager = Brew()
    _stub_brew(monkeypatch, manager, info, tmp_path)
    packages = [manager.package(id="curl"), manager.package(id="git-delta")]

    results = list(manager.package_metadata_batch(packages))

    assert [package.id for package, _ in results] == ["curl", "git-delta"]
    assert all(metadata is EMPTY_METADATA for _, metadata in results)


def test_package_metadata_batch_resolves_every_formula_name(monkeypatch, tmp_path):
    """A package finds its formula record under each name the record carries.

    `brew list` can report a formula under an old name, an alias or its
    tap-qualified name. A package that the payload does not describe stays bare.
    """
    manager = Brew()
    payload = {
        "formulae": [CURL_FORMULA, GIT_DELTA_FORMULA, NIGHTLIGHT_FORMULA],
        "casks": [],
    }
    _stub_brew(monkeypatch, manager, payload, tmp_path)
    package_ids = ("curl", "wcurl", "delta", "smudge/smudge/nightlight", "wget")

    results = list(
        manager.package_metadata_batch(
            manager.package(id=package_id) for package_id in package_ids
        )
    )

    assert [(package.id, metadata.description) for package, metadata in results] == [
        ("curl", CURL_FORMULA["desc"]),
        ("wcurl", CURL_FORMULA["desc"]),
        ("delta", GIT_DELTA_FORMULA["desc"]),
        ("smudge/smudge/nightlight", NIGHTLIGHT_FORMULA["desc"]),
        ("wget", None),
    ]
    assert results[-1][1] is EMPTY_METADATA


def test_formula_metadata_maps_the_record(monkeypatch):
    """A formula record fills the portable fields and the Homebrew extras.

    The bottle digest becomes the checksum, each dependency list keeps its scope,
    and the keg-only reason is kept. With no known prefix, no upstream SBOM is
    looked up.
    """
    manager = Brew()
    _stub_brew(monkeypatch, manager, {"formulae": [CURL_FORMULA], "casks": []}, None)

    [(_, metadata)] = manager.package_metadata_batch([manager.package(id="curl")])

    assert metadata == PackageMetadata(
        download_url="https://curl.se/download/curl-8.23.0.tar.bz2",
        homepage="https://curl.se",
        license_declared="curl",
        license_concluded="curl",
        supplier=Supplier(name="Homebrew Formulae", url="https://brew.sh"),
        description="Get a file from an HTTP, HTTPS or FTP server",
        summary="Get a file from an HTTP, HTTPS or FTP server",
        dependencies=(
            *(Dependency(name) for name in CURL_FORMULA["dependencies"]),
            Dependency("pkgconf", DependencyScope.BUILD),
            Dependency("pkgconf", DependencyScope.TEST),
        ),
        checksums=(Checksum(ChecksumAlgorithm.SHA256, CURL_BOTTLE_SHA256),),
        extras={
            "brew.tap": "homebrew/core",
            "brew.installed_on_request": True,
            "brew.poured_from_bottle": True,
            "brew.keg_only": True,
            "brew.keg_only_reason": ":provided_by_macos",
        },
    )


@pytest.mark.parametrize(
    ("keg_version", "found", "upstream_purls"),
    (
        pytest.param("0.0.90", True, ["pkg:pypi/ty@0.0.90"], id="installed-version"),
        pytest.param("0.0.91", False, [], id="stable-version"),
    ),
)
def test_formula_metadata_reads_the_sbom_of_the_installed_keg(
    monkeypatch, tmp_path, keg_version, found, upstream_purls
):
    """The upstream SBOM is read from the keg of the installed version.

    The record of `ty` names `0.0.91` as its stable version, while the host still
    had `0.0.90` installed, the only keg holding an SBOM. The source package of
    that document is the one Homebrew wrote, a brew purl beside the PyPI one.
    """
    keg = tmp_path / "Cellar" / "ty" / keg_version
    keg.mkdir(parents=True)
    sbom_file = _write_formula_sbom(
        keg, "ty", ("pkg:brew/homebrew/core/ty@0.0.90", "pkg:pypi/ty@0.0.90")
    )
    manager = Brew()
    _stub_brew(monkeypatch, manager, {"formulae": [TY_FORMULA], "casks": []}, tmp_path)

    [(_, metadata)] = manager.package_metadata_batch([manager.package(id="ty")])

    assert metadata.external_sbom_path == (sbom_file if found else None)
    assert [purl.to_string() for purl in metadata.extra_purls] == upstream_purls
    assert metadata.dependencies == (Dependency("rust", DependencyScope.BUILD),)


@pytest.mark.parametrize(
    ("cask", "expected"),
    (
        pytest.param(
            ADGUARD_CASK,
            PackageMetadata(
                download_url=ADGUARD_CASK["url"],
                homepage="https://adguard.com/",
                supplier=CASK_SUPPLIER,
                description="Stand alone ad blocker",
                summary="AdGuard",
                checksums=(Checksum(ChecksumAlgorithm.SHA256, ADGUARD_CASK["sha256"]),),
                extras={"brew.tap": "homebrew/cask", "brew.auto_updates": True},
            ),
            id="auto-updating",
        ),
        pytest.param(
            DISK_DRILL_CASK,
            PackageMetadata(
                download_url="https://dl.cleverfiles.com/diskdrill.dmg",
                homepage="https://www.cleverfiles.com/",
                supplier=CASK_SUPPLIER,
                description="Data recovery software",
                summary="Disk Drill",
                extras={"brew.tap": "homebrew/cask", "brew.auto_updates": True},
            ),
            id="unchecked-download",
        ),
        pytest.param(
            NCAR_NCL_CASK,
            PackageMetadata(
                download_url=NCAR_NCL_CASK["url"],
                homepage="https://www.ncl.ucar.edu/",
                supplier=CASK_SUPPLIER,
                description=NCAR_NCL_CASK["desc"],
                summary="NCAR Command Language",
                dependencies=(Dependency("xquartz"), Dependency("gcc")),
                checksums=(
                    Checksum(ChecksumAlgorithm.SHA256, NCAR_NCL_CASK["sha256"]),
                ),
                extras={"brew.tap": "homebrew/cask"},
            ),
            id="cask-and-formula-dependencies",
        ),
    ),
)
def test_cask_metadata_maps_the_record(monkeypatch, tmp_path, cask, expected):
    """A cask record fills the portable fields from its leaner schema.

    The first of its names is the summary. A `no_check` digest yields no
    checksum, and a cask with no `auto_updates` setting gets no such extra.
    """
    manager = Cask()
    _stub_brew(monkeypatch, manager, {"formulae": [], "casks": [cask]}, tmp_path)

    [(_, metadata)] = manager.package_metadata_batch([
        manager.package(id=cask["token"])
    ])

    assert metadata == expected
