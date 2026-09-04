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
"""fwupd device-parsing tests, covering the optional fields of a device.

`fwupd_device_add_json()` writes `Name`, `DeviceId`, `Flags` and `Version`
only where the daemon read a value, so any of them can be absent from
`fwupdmgr get-devices --json`. The records below are the captured devices of
the `installed` and `outdated` samples, each stripped of the fields whose
absence is under test. They are fed straight to the parsers, so nothing here
invokes `fwupdmgr` or reads this machine's hardware.
"""

from __future__ import annotations

import json

import pytest

from meta_package_manager.managers.fwupd import FWUPD

DBX_ID = "362301da643102b9f38477387e2193e57abaa590"
"""The `UEFI dbx` device of both captured samples."""

UPDATABLE = {
    "Name": "UEFI dbx",
    "DeviceId": DBX_ID,
    "Version": "0",
    "Flags": ["internal", "updatable", "supported", "registered"],
}
"""A complete updatable device, as captured."""

FIXED = {
    "Name": "Virtio network device",
    "DeviceId": "17076870bcf7a84a9c8e999d7e54e39b446032bb",
    "Flags": ["internal", "registered", "can-verify", "can-verify-image"],
}
"""A device fwupd cannot update, captured as-is: it already carries no
`Version`, which the `updatable` test used to shadow."""

FLAGLESS = {
    "DeviceId": "20de1d77d0d1787bc56ef62f7d05de49361e1e07",
    "Plugin": "linux_display",
}
"""The captured `linux_display` device with its `Flags` dropped, the shape
that aborted every run with a `KeyError`."""

BARE = {"DeviceId": DBX_ID, "Flags": ["updatable"]}
"""An updatable device carrying neither a name nor a version."""

ANONYMOUS = {"Name": "UEFI dbx", "Version": "0", "Flags": ["updatable"]}
"""A device with no ID: nothing can address it, so it is not a package."""

RELEASES = [{"Version": "21"}, {"Version": "26"}, {"Version": "22"}]
"""The three `UEFI dbx` releases of the captured `get-updates` sample."""


def payload(*devices) -> str:
    """Wrap device records into a `get-devices` or `get-updates` payload."""
    return json.dumps({"Devices": devices})


def reported(packages) -> tuple[tuple[str, str | None, str | None, str | None], ...]:
    """Reduce packages to the four fields these two parsers populate."""
    return tuple(
        (
            package.id,
            package.name,
            str(package.installed_version) if package.installed_version else None,
            str(package.latest_version) if package.latest_version else None,
        )
        for package in packages
    )


@pytest.fixture
def manager():
    return FWUPD()


@pytest.mark.parametrize(
    ("devices", "expected"),
    (
        pytest.param((FLAGLESS,), (), id="no_flags"),
        pytest.param((FIXED,), (), id="not_updatable"),
        pytest.param((ANONYMOUS,), (), id="no_device_id"),
        pytest.param((UPDATABLE,), ((DBX_ID, "UEFI dbx", "0", None),), id="updatable"),
        pytest.param((BARE,), ((DBX_ID, None, None, None),), id="no_name_or_version"),
        pytest.param(
            (FLAGLESS, FIXED, UPDATABLE),
            ((DBX_ID, "UEFI dbx", "0", None),),
            id="mixed",
        ),
    ),
)
def test_installed(manager, stub_run_cli, devices, expected):
    stub_run_cli(manager, payload(*devices))
    assert reported(manager.installed) == expected


@pytest.mark.parametrize(
    ("devices", "expected"),
    (
        pytest.param(({**FLAGLESS, "Releases": RELEASES},), (), id="no_flags"),
        pytest.param(({**FIXED, "Releases": RELEASES},), (), id="not_updatable"),
        pytest.param(({**ANONYMOUS, "Releases": RELEASES},), (), id="no_device_id"),
        pytest.param((UPDATABLE,), (), id="no_releases"),
        pytest.param(({**UPDATABLE, "Releases": []},), (), id="empty_releases"),
        pytest.param(
            ({**UPDATABLE, "Releases": [{"Filename": "DBXUpdate.cab"}]},),
            (),
            id="release_without_version",
        ),
        pytest.param(
            ({**UPDATABLE, "Releases": RELEASES},),
            ((DBX_ID, "UEFI dbx", "0", "26"),),
            id="updatable",
        ),
        pytest.param(
            ({**BARE, "Releases": RELEASES},),
            ((DBX_ID, None, None, "26"),),
            id="no_name_or_version",
        ),
    ),
)
def test_outdated(manager, stub_run_cli, devices, expected):
    stub_run_cli(manager, payload(*devices))
    assert reported(manager.outdated) == expected
