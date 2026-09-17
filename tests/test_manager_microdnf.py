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
"""microdnf parser tests.

Every payload below is captured output, from AlmaLinux 10.2 aarch64 running
microdnf `3.10.1` and libdnf `0.73.1`. Trailing spaces are kept: the transaction
table pads its heading and `replacing` rows to the width of the table.
"""

from __future__ import annotations

import re

import pytest

from meta_package_manager.managers.microdnf import MicroDNF
from meta_package_manager.version import VersionRange, parse_version

UPGRADE_PREVIEW = (
    "Package                                             Repository     Size\n"
    "Installing:                                                            \n"
    " kernel-6.12.0-211.53.1.el10_2.aarch64              baseos       1.7 MB\n"
    " kernel-core-6.12.0-211.53.1.el10_2.aarch64         baseos      19.9 MB\n"
    " kernel-modules-6.12.0-211.53.1.el10_2.aarch64      baseos      28.3 MB\n"
    " kernel-modules-core-6.12.0-211.53.1.el10_2.aarch64 baseos      26.6 MB\n"
    "Upgrading:                                                             \n"
    " rsync-3.5.0-3.el10_2.aarch64                       baseos     474.3 kB\n"
    "  replacing rsync-3.4.4-1.el10_2.aarch64                               \n"
    " tar-2:1.35-13.el10_2.aarch64                       baseos     884.5 kB\n"
    "   replacing tar-2:1.35-11.el10.aarch64                                \n"
    "Transaction Summary:\n"
    " Installing:        4 packages\n"
    " Reinstalling:      0 packages\n"
    " Upgrading:         2 packages\n"
    " Obsoleting:        0 packages\n"
    " Removing:          0 packages\n"
    " Downgrading:       0 packages\n"
    "Operation aborted.\n"
)
"""`microdnf --assumeno upgrade`, with two upgrades and one new kernel.

The kernel packages are install-only: RPM installs their new version beside the
old one, so they sit under `Installing:` with no `replacing` row.
"""

INSTALLED_KERNELS = (
    "kernel-6.12.0-211.47.1.el10_2.aarch64\n"
    "kernel-core-6.12.0-211.47.1.el10_2.aarch64\n"
    "kernel-modules-6.12.0-211.47.1.el10_2.aarch64\n"
    "kernel-modules-core-6.12.0-211.47.1.el10_2.aarch64\n"
)
"""The installed kernels, read by the second query of `outdated`."""

INSTALL_PREVIEW = (
    "Package                    Repository    Size\n"
    "Installing:                                  \n"
    " tree-2.1.0-8.el10.aarch64 baseos     56.6 kB\n"
    "Transaction Summary:\n"
    " Installing:        1 packages\n"
    " Reinstalling:      0 packages\n"
    " Upgrading:         0 packages\n"
    " Obsoleting:        0 packages\n"
    " Removing:          0 packages\n"
    " Downgrading:       0 packages\n"
    "Operation aborted.\n"
)
"""`microdnf --assumeno install tree`, on a host where `tree` is not installed.

The same table as an upgrade preview, with an `Installing:` row for a package
the host does not have: the shape of a new dependency an upgrade pulls in.
"""

SEARCH_BUILDS = (
    "xxd-2:9.1.083-9.el10_2.2.aarch64\n"
    "xxd-2:9.1.083-9.el10_2.3.aarch64\n"
    "xxd-2:9.1.083-9.el10_2.4.aarch64\n"
    "xxd-2:9.1.083-9.el10_2.7.aarch64\n"
    "xxd-2:9.1.083-9.el10_2.12.aarch64\n"
    "xxd-2:9.1.083-9.el10_2.20.aarch64\n"
)
"""`microdnf repoquery *xxd*`: the repository keeps six builds of one package."""

SEARCH_COLD_CACHE = (
    "Downloading metadata...\n"
    "Downloading metadata...\n"
    "Downloading metadata...\n"
    "Downloading metadata...\n"
    "bash-5.2.26-6.el10.aarch64\n"
)
"""`microdnf repoquery bash` on a cold cache, which reports each download too."""


def probe_version(output: str):
    """Reproduce the version probe: the first matching regex wins."""
    for regex in MicroDNF.version_regexes:
        match = re.compile(regex, re.MULTILINE).search(output)
        if match and match.group("version"):
            return parse_version(match.group("version"))
    return None


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param("3.10.1", "3.10.1", id="package-installed"),
        # The answer on a host with no `microdnf` package, like a Fedora where
        # the name is a symlink to dnf5.
        pytest.param("package microdnf is not installed\n", None, id="no-package"),
    ),
)
def test_version_probe(output, expected):
    """Only a bare version is read, and it clears the requirement."""
    version = probe_version(output)
    if expected is None:
        assert version is None
        return
    assert str(version) == expected
    assert version in VersionRange(MicroDNF.requirement)


def replay(
    monkeypatch, responses: dict[tuple[str, ...], str]
) -> tuple[MicroDNF, list[tuple]]:
    """Answer each call with the output of the first matching argument prefix."""
    manager = MicroDNF()
    calls: list[tuple] = []

    def fake_run_cli(*args, **kwargs) -> str:
        calls.append(args)
        for prefix, output in responses.items():
            if args[: len(prefix)] == prefix:
                return output
        raise AssertionError(f"Unexpected call: {args}")

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    return manager, calls


def test_outdated_reads_the_upgrade_preview(monkeypatch):
    """Upgrades pair with their `replacing` row, kernels with the installed list."""
    manager, calls = replay(
        monkeypatch,
        {
            ("--assumeno", "upgrade"): UPGRADE_PREVIEW,
            ("repoquery", "--installed"): INSTALLED_KERNELS,
        },
    )

    found = [
        (package.id, str(package.installed_version), str(package.latest_version))
        for package in manager.outdated
    ]
    assert found == [
        ("kernel", "6.12.0-211.47.1.el10_2", "6.12.0-211.53.1.el10_2"),
        ("kernel-core", "6.12.0-211.47.1.el10_2", "6.12.0-211.53.1.el10_2"),
        ("kernel-modules", "6.12.0-211.47.1.el10_2", "6.12.0-211.53.1.el10_2"),
        ("kernel-modules-core", "6.12.0-211.47.1.el10_2", "6.12.0-211.53.1.el10_2"),
        ("rsync", "3.4.4-1.el10_2", "3.5.0-3.el10_2"),
        # The epoch stays in both versions.
        ("tar", "2:1.35-11.el10", "2:1.35-13.el10_2"),
    ]
    # The rows paired by a `replacing` row are not queried again.
    assert calls == [
        ("--assumeno", "upgrade"),
        (
            "repoquery",
            "--installed",
            "kernel",
            "kernel-core",
            "kernel-modules",
            "kernel-modules-core",
        ),
    ]


def test_outdated_skips_packages_not_installed(monkeypatch):
    """An `Installing:` row is only an update when its package is installed."""
    manager, calls = replay(
        monkeypatch,
        {
            ("--assumeno", "upgrade"): INSTALL_PREVIEW,
            ("repoquery", "--installed"): "",
        },
    )

    assert list(manager.outdated) == []
    assert calls[-1] == ("repoquery", "--installed", "tree")


def test_outdated_with_nothing_to_do(monkeypatch):
    """An up-to-date host prints one line and needs no second query."""
    manager, calls = replay(
        monkeypatch, {("--assumeno", "upgrade"): "Nothing to do.\n"}
    )

    assert list(manager.outdated) == []
    assert calls == [("--assumeno", "upgrade")]


@pytest.mark.parametrize(
    ("output", "query", "exact", "expected"),
    (
        pytest.param(
            SEARCH_BUILDS,
            "xxd",
            False,
            [("xxd", "2:9.1.083-9.el10_2.20")],
            id="newest-build",
        ),
        pytest.param(
            SEARCH_COLD_CACHE,
            "bash",
            True,
            [("bash", "5.2.26-6.el10")],
            id="download-lines",
        ),
    ),
)
def test_search(monkeypatch, output, query, exact, expected):
    """One package per name, at its newest build, whatever else is printed."""
    manager, calls = replay(monkeypatch, {("repoquery",): output})

    found = [
        (package.id, str(package.latest_version))
        for package in manager.search(query, extended=False, exact=exact)
    ]
    assert found == expected
    assert calls == [("repoquery", query if exact else f"*{query}*")]
