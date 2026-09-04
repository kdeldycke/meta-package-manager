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
"""fwupd-specific parsing tests.

These tests feed canned `fwupdmgr get-devices --json` output to the parser.
They never invoke `fwupdmgr` nor touch this machine's devices.
"""

from __future__ import annotations

import json

import pytest

from meta_package_manager.managers.fwupd import FWUPD


@pytest.fixture
def fwupd():
    return FWUPD()


def _devices_json(*devices):
    """Wrap device dicts into a `get-devices --json` payload string."""
    return json.dumps({"Devices": list(devices)})


def test_installed_skips_device_without_flags(fwupd, monkeypatch):
    """Regression test: a device with no `Flags` key must be skipped, not crash.

    `fwupdmgr get-devices --json` may list devices that carry no `Flags` key
    at all. Indexing `device["Flags"]` raised `KeyError` and aborted the run.
    """
    output = _devices_json(
        {
            "Name": "Flagless device",
            "DeviceId": "no-flags-id",
            "Version": "1.0",
        },
    )
    monkeypatch.setattr(fwupd, "run_cli", lambda *a, **kw: output)

    assert list(fwupd.installed) == []


def test_installed_reports_updatable_device(fwupd, monkeypatch):
    """A device flagged `updatable` is reported with its id, name and version."""
    output = _devices_json(
        {
            "Name": "System Firmware",
            "DeviceId": "updatable-id",
            "Version": "1.2.3",
            "Flags": ["internal", "updatable", "registered"],
        },
    )
    monkeypatch.setattr(fwupd, "run_cli", lambda *a, **kw: output)

    packages = list(fwupd.installed)
    assert len(packages) == 1
    assert packages[0].id == "updatable-id"
    assert packages[0].name == "System Firmware"
    assert str(packages[0].installed_version) == "1.2.3"


def test_installed_skips_non_updatable_device(fwupd, monkeypatch):
    """A device with `Flags` but no `updatable` entry is skipped."""
    output = _devices_json(
        {
            "Name": "Fixed device",
            "DeviceId": "fixed-id",
            "Version": "2.0",
            "Flags": ["internal", "registered"],
        },
    )
    monkeypatch.setattr(fwupd, "run_cli", lambda *a, **kw: output)

    assert list(fwupd.installed) == []


def test_installed_mixed_devices(fwupd, monkeypatch):
    """Only updatable devices survive a mix of flagless, fixed and updatable."""
    output = _devices_json(
        {"Name": "Flagless", "DeviceId": "a", "Version": "1"},
        {"Name": "Fixed", "DeviceId": "b", "Version": "2", "Flags": ["internal"]},
        {
            "Name": "Updatable",
            "DeviceId": "c",
            "Version": "3",
            "Flags": ["updatable"],
        },
    )
    monkeypatch.setattr(fwupd, "run_cli", lambda *a, **kw: output)

    assert [p.id for p in fwupd.installed] == ["c"]
