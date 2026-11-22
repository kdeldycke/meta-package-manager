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
"""rpm-ostree availability and parser tests.

Every payload below is captured output, from Fedora IoT 45 aarch64 running
rpm-ostree `2026.3`, except `SEARCH_RENDERED`, captured on Fedora IoT 44 with
rpm-ostree `2026.1`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.execution import CLIError
from meta_package_manager.manager import PackageManager
from meta_package_manager.managers import rpm_ostree
from meta_package_manager.managers.rpm_ostree import UNCHANGED_EXIT_CODE, RPM_OSTree

DEPLOYMENT_WITH_LOCAL_RPM = """[
  {
    "unlocked" : "none",
    "base-local-replacements" : [],
    "requested-local-packages" : [
      "sl-5.02-26.fc45.aarch64"
    ],
    "base-commit-meta" : {
      "ostree.bootable" : true,
      "ostree.composefs.digest.v0" : [
        24,
        211,
        7,
        130,
        152,
        130,
        21,
        183,
        87,
        114,
        170,
        64,
        18,
        13,
        216,
        108,
        82,
        59,
        219,
        104,
        214,
        73,
        200,
        194,
        231,
        76,
        131,
        93,
        25,
        188,
        23,
        127
      ],
      "rpmostree.inputhash" : "c51fd6423374fae9e23082929ceadef826355538c6161d5d379ab556d3595597",
      "version" : "45.20261121.0",
      "rpmostree.initramfs-args" : [
        "--no-hostonly",
        "--add",
        "ignition watchdog"
      ],
      "ostree.linux" : "7.3.4-300.fc45.aarch64",
      "rpmostree.rpmmd-repos" : [
        {
          "id" : "repo-0",
          "timestamp" : 7014605364523958272
        },
        {
          "id" : "repo-1",
          "timestamp" : -5154086739475693568
        },
        {
          "id" : "repo-2",
          "timestamp" : 4190599912829747200
        },
        {
          "id" : "repo-3",
          "timestamp" : -726486455328702464
        }
      ]
    },
    "base-removals" : [],
    "gpg-enabled" : true,
    "pinned" : false,
    "osname" : "fedora-iot",
    "base-remote-replacements" : {    },
    "origin" : "fedora-iot:fedora/stable/aarch64/iot",
    "regenerate-initramfs" : false,
    "checksum" : "020a7c966b1d776114b0d95adfe318ea26614baefe61b1f38f2c7e681f043f8c",
    "requested-base-local-replacements" : [],
    "id" : "fedora-iot-020a7c966b1d776114b0d95adfe318ea26614baefe61b1f38f2c7e681f043f8c.0",
    "version" : "45.20261121.0",
    "base-version" : "45.20261121.0",
    "base-checksum" : "9282cc873b386fc0e61815760a55d0ec9aa46050ceb1c298c31600878d51e665",
    "requested-base-removals" : [],
    "requested-local-fileoverride-packages" : [],
    "serial" : 0,
    "base-timestamp" : 1795259141,
    "staged" : true,
    "booted" : false,
    "layered-commit-meta" : {
      "rpmostree.clientlayer" : true,
      "version" : "45.20261121.0",
      "rpmostree.clientlayer_version" : 6,
      "rpmostree.state-sha512" : "c4a18d9cf51f5e7295872d550b5a384cd9623067f3c11af3505ec2e3c70b00a16c173bfd031866531d76e8078335396cfc8680274ef7e9f224b61db1050a6d74",
      "rpmostree.rpmmd-repos" : [
        {
          "id" : "fedora",
          "timestamp" : 1793218657
        },
        {
          "id" : "fedora-cisco-openh264",
          "timestamp" : 1774349753
        },
        {
          "id" : "updates",
          "timestamp" : 1795309053
        }
      ],
      "ostree.linux" : "7.3.4-300.fc45.aarch64",
      "ostree.bootable" : true
    },
    "packages" : [
      "nyancat"
    ],
    "requested-packages" : [
      "nyancat"
    ],
    "timestamp" : 1795335403,
    "signatures" : [
      [
        true,
        false,
        false,
        false,
        false,
        "4F50A6114CD5C6976A7F1179655A4B02F577861E",
        1795259180,
        0,
        "RSA",
        "SHA256",
        "Fedora",
        "fedora-45-primary@fedoraproject.org",
        "4F50A6114CD5C6976A7F1179655A4B02F577861E",
        0,
        0
      ]
    ]
  }
]"""  # noqa: E501
"""`rpm-ostree status --jsonpath '$.deployments[0]'`, a deployment staged.

It layers `nyancat` from the repositories, and `sl` from an RPM file.
"""

DB_LIST = """ostree commit: 020a7c966b1d776114b0d95adfe318ea26614baefe61b1f38f2c7e681f043f8c
 nyancat-1.5.2-19.fc45.aarch64
"""  # noqa: E501
"""`rpm-ostree db list {checksum} nyancat`, on the commit of the deployment above."""

CHECK_WITH_UPDATE = """2 metadata, 0 content objects fetched; 24 KiB transferred in 5 seconds; 0 bytes content written
Receiving metadata objects: 1/(estimating) 148 bytes/s 592 bytes...done
Enabled rpm-md repositories: fedora fedora-cisco-openh264 updates
Updating metadata for 'fedora'...done
Updating metadata for 'fedora-cisco-openh264'...done
Updating metadata for 'updates'...done
Importing rpm-md...done
rpm-md repo 'fedora'; generated: 2026-10-28T20:17:37Z solvables: 66681
rpm-md repo 'fedora-cisco-openh264'; generated: 2026-03-24T10:55:53Z solvables: 3
rpm-md repo 'updates'; generated: 2026-11-22T00:57:33Z solvables: 11615
AvailableUpdate:
        Version: 45.20261121.0 (2026-11-21T11:05:41Z)
         Commit: 9282cc873b386fc0e61815760a55d0ec9aa46050ceb1c298c31600878d51e665
   GPGSignature: Valid signature by 4F50A6114CD5C6976A7F1179655A4B02F577861E
  SecAdvisories: 2 important
           Diff: 3 upgraded
"""  # noqa: E501
"""`rpm-ostree upgrade --check` on `45.20261118.0`, which exits `0`."""

CHECK_WITHOUT_UPDATE = """1 metadata, 0 content objects fetched; 592 B transferred in 5 seconds; 0 bytes content written
Receiving metadata objects: 0/(estimating) -/s 0 bytes...done
Enabled rpm-md repositories: fedora fedora-cisco-openh264 updates
Updating metadata for 'fedora'...done
Updating metadata for 'fedora-cisco-openh264'...done
Updating metadata for 'updates'...done
Importing rpm-md...done
rpm-md repo 'fedora'; generated: 2026-10-28T20:17:37Z solvables: 66681
rpm-md repo 'fedora-cisco-openh264'; generated: 2026-03-24T10:55:53Z solvables: 3
rpm-md repo 'updates'; generated: 2026-11-22T00:57:33Z solvables: 11615
No updates available.
"""  # noqa: E501
"""`rpm-ostree upgrade --check` on `45.20261121.0`, which exits `77`."""

CHECK_NOTE = """Note: --check and --preview may be unreliable.  See https://github.com/coreos/rpm-ostree/issues/1579
"""
"""What both checks above print on `<stderr>`."""

UPGRADED_DIFF = """[
  [
    [
      0,
      "ignition",
      [
        "2.27.0-2.fc45",
        "aarch64"
      ],
      [
        "2.28.0-2.fc45",
        "aarch64"
      ]
    ],
    [
      0,
      "ignition-edge",
      [
        "2.27.0-2.fc45",
        "aarch64"
      ],
      [
        "2.28.0-2.fc45",
        "aarch64"
      ]
    ],
    [
      0,
      "sqlite-libs",
      [
        "3.53.4-1.fc45",
        "aarch64"
      ],
      [
        "3.54.1-2.fc45",
        "aarch64"
      ]
    ]
  ]
]"""
"""`rpm-ostree status --jsonpath $.cached-update.rpm-diff.upgraded`, after the
check of `45.20261118.0`."""

SEARCH_RENDERED = """
===== Name Matched =====
rust-ratatui+unstable-rendered-line-info-devel : Library that's all about cooking up terminal user interfaces
rust-ratatui-widgets+unstable-rendered-line-info-devel : Collection of widgets for building terminal user interfaces using Ratatui
rust-ratatui0.26+unstable-rendered-line-info-devel : Library that's all about cooking up terminal user interfaces
rust-ratatui0.29+unstable-rendered-line-info-devel : Library that's all about cooking up terminal user interfaces

===== Summary Matched =====
nyancat : Nyancat rendered in your terminal
"""  # noqa: E501
"""`rpm-ostree search rendered`: four packages match by name, one by summary."""

DENIAL = "error: rpmostreed OS operation AutomaticUpdateTrigger not allowed for user"
"""What `rpm-ostree upgrade --check` prints on `<stderr>` for a user who is not root."""


@pytest.fixture
def manager():
    return RPM_OSTree()


def stub_by_verb(manager, monkeypatch, outputs, calls=None):
    """Answer each `run_cli` call with the output keyed by its first argument."""

    def run_cli(*args, **kwargs):
        if calls is not None:
            calls.append(args)
        return outputs[args[0]]

    monkeypatch.setattr(manager, "run_cli", run_cli)


def test_unavailable_without_ostree_boot(manager, monkeypatch, tmp_path):
    """The base conditions met, the ostree marker decides alone."""
    marker = tmp_path / "ostree-booted"
    monkeypatch.setattr(rpm_ostree, "OSTREE_BOOTED", marker)
    monkeypatch.setattr(
        PackageManager, "unavailable_reason", property(lambda self: None)
    )

    assert manager.unavailable_reason == (
        f"{marker} is missing: the host did not boot from ostree"
    )

    marker.touch()
    assert manager.unavailable_reason is None


def test_base_reason_wins_over_ostree_marker(manager, monkeypatch, tmp_path):
    """A host failing a base condition reports that condition first."""
    monkeypatch.setattr(rpm_ostree, "OSTREE_BOOTED", tmp_path / "ostree-booted")
    monkeypatch.setattr(
        PackageManager,
        "unavailable_reason",
        property(lambda self: "not supported on macOS"),
    )

    assert manager.unavailable_reason == "not supported on macOS"


def test_installed_reads_layered_and_local_packages(manager, monkeypatch):
    calls: list[tuple] = []
    stub_by_verb(
        manager,
        monkeypatch,
        {"status": DEPLOYMENT_WITH_LOCAL_RPM, "db": DB_LIST},
        calls,
    )

    packages = [
        (package.id, str(package.installed_version), package.arch)
        for package in manager.installed
    ]

    assert packages == [
        ("nyancat", "1.5.2-19.fc45", "aarch64"),
        ("sl", "5.02-26.fc45", "aarch64"),
    ]
    # Only the repository package needs the RPM database of the commit: the
    # local RPM carries its version in its own request.
    assert calls[1] == (
        "db",
        "list",
        "020a7c966b1d776114b0d95adfe318ea26614baefe61b1f38f2c7e681f043f8c",
        "nyancat",
    )


@pytest.mark.parametrize(
    ("nevra", "expected"),
    [
        ("nyancat-1.5.2-19.fc45.aarch64", ("nyancat", "1.5.2-19.fc45", "aarch64")),
        (
            "NetworkManager-1:1.56.0-1.fc44.aarch64",
            ("NetworkManager", "1:1.56.0-1.fc44", "aarch64"),
        ),
        (
            "aardvark-dns-2:1.17.0-3.fc44.aarch64",
            ("aardvark-dns", "2:1.17.0-3.fc44", "aarch64"),
        ),
    ],
)
def test_parse_nevra(manager, nevra, expected):
    """Dashes in the name and an epoch in the version both split right.

    The NEVRA strings are lines of `rpm-ostree db list` on Fedora IoT 44 and 45.
    """
    assert manager._parse_nevra(nevra) == expected


def test_outdated_reads_the_cached_diff(manager, monkeypatch):
    stub_by_verb(
        manager,
        monkeypatch,
        {"upgrade": CHECK_WITH_UPDATE, "status": UPGRADED_DIFF},
    )

    packages = [
        (
            package.id,
            str(package.installed_version),
            str(package.latest_version),
            package.arch,
        )
        for package in manager.outdated
    ]

    assert packages == [
        ("ignition", "2.27.0-2.fc45", "2.28.0-2.fc45", "aarch64"),
        ("ignition-edge", "2.27.0-2.fc45", "2.28.0-2.fc45", "aarch64"),
        ("sqlite-libs", "3.53.4-1.fc45", "3.54.1-2.fc45", "aarch64"),
    ]


def test_outdated_up_to_date_under_stop_on_error(manager, monkeypatch):
    """The status of an up-to-date host is not an error, even when strict."""

    def run_cli(*args, **kwargs):
        if args[0] == "upgrade":
            # What `run()` does with a non-zero exit under `--stop-on-error`.
            error = CLIError(UNCHANGED_EXIT_CODE, CHECK_WITHOUT_UPDATE, CHECK_NOTE)
            manager.cli_errors.append(error)
            raise error
        return "[]"

    monkeypatch.setattr(manager, "run_cli", run_cli)

    assert list(manager.outdated) == []
    assert manager.cli_errors == []


def test_outdated_reraises_a_failed_check(manager, monkeypatch):
    def run_cli(*args, **kwargs):
        raise CLIError(1, "", DENIAL)

    monkeypatch.setattr(manager, "run_cli", run_cli)

    with pytest.raises(CLIError):
        list(manager.outdated)


def test_outdated_skips_cached_update_after_failed_check(manager, monkeypatch):
    """A failed check must not report the update an earlier check cached."""
    calls: list[tuple] = []

    def run_cli(*args, **kwargs):
        calls.append(args)
        if args[0] == "upgrade":
            manager.cli_errors.append(CLIError(1, "", DENIAL))
        return UPGRADED_DIFF

    monkeypatch.setattr(manager, "run_cli", run_cli)

    assert list(manager.outdated) == []
    assert calls == [("upgrade", "--check")]


@pytest.mark.parametrize(
    ("extended", "expected"),
    [
        (
            False,
            [
                "rust-ratatui+unstable-rendered-line-info-devel",
                "rust-ratatui-widgets+unstable-rendered-line-info-devel",
                "rust-ratatui0.26+unstable-rendered-line-info-devel",
                "rust-ratatui0.29+unstable-rendered-line-info-devel",
            ],
        ),
        (
            True,
            [
                "rust-ratatui+unstable-rendered-line-info-devel",
                "rust-ratatui-widgets+unstable-rendered-line-info-devel",
                "rust-ratatui0.26+unstable-rendered-line-info-devel",
                "rust-ratatui0.29+unstable-rendered-line-info-devel",
                "nyancat",
            ],
        ),
    ],
)
def test_search_reads_the_name_section_unless_extended(
    manager, monkeypatch, extended, expected
):
    stub_by_verb(manager, monkeypatch, {"search": SEARCH_RENDERED})

    results = list(manager.search("rendered", extended=extended, exact=False))

    assert [package.id for package in results] == expected
    assert results[-1].description is not None
