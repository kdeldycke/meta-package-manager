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
"""pipx output-parsing and CLI-construction tests.

These tests stub `run_cli` and exercise the pure-Python branches of the
`Pipx` manager. They do not invoke the real `pipx` binary.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.pipx import Pipx
from meta_package_manager.version import parse_version

INSTALLED_SNAPSHOT = """\
{
  "pipx_spec_version": "0.1",
  "venvs": {
    "pycowsay": {
      "metadata": {
        "injected_packages": {},
        "main_package": {
          "package": "pycowsay",
          "package_version": "0.0.0.1"
        }
      }
    }
  }
}
"""

OUTDATED_ENVELOPE = """\
{
  "command": ["list"],
  "data": {
    "packages_checked": 2,
    "packages": [
      {
        "environment": "poetry",
        "package": "poetry",
        "version": "2.1.0",
        "latest_version": "2.2.0",
        "injected": false,
        "pinned": true
      },
      {
        "environment": "pycowsay",
        "package": "pycowsay",
        "version": "0.0.0.1",
        "latest_version": "0.0.0.2",
        "injected": false,
        "pinned": false
      }
    ],
    "skipped": []
  },
  "errors": [],
  "exit_code": 0,
  "pipx_result_version": "1",
  "status": "success"
}
"""

PIP_PROBE = """\
[
  {
    "name": "pycowsay",
    "version": "0.0.0.1",
    "latest_version": "0.0.0.2",
    "latest_filetype": "wheel"
  },
  {
    "name": "attrs",
    "version": "21.0.0",
    "latest_version": "25.0.0",
    "latest_filetype": "wheel"
  }
]
"""


@pytest.fixture
def manager():
    return Pipx()


def test_installed_yields_packages(manager, stub_run_cli):
    stub_run_cli(manager, INSTALLED_SNAPSHOT)
    packages = list(manager.installed)
    assert len(packages) == 1
    assert packages[0].id == "pycowsay"
    assert str(packages[0].installed_version) == "0.0.0.1"


@pytest.mark.parametrize("output", ("", "{}"))
def test_installed_handles_empty(manager, stub_run_cli, output):
    stub_run_cli(manager, output)
    assert list(manager.installed) == []


@pytest.mark.parametrize(
    ("version", "expected_call"),
    (
        (None, ("list", "--json")),
        ("1.0.0", ("list", "--json")),
        ("1.15.2", ("list", "--json")),
        ("1.16.0", ("list", "--outdated", "--output=json")),
        ("1.17.2", ("list", "--outdated", "--output=json")),
    ),
)
def test_outdated_version_gate(manager, capture_run_cli, version, expected_call):
    """The native outdated query needs pipx >= 1.16.0; older ones fall back to
    enumerating the venvs before probing each with its embedded pip."""
    manager.__dict__["version"] = parse_version(version) if version else None
    calls = capture_run_cli(manager)
    assert list(manager.outdated) == []
    assert calls == [expected_call]


def test_outdated_native_parses_envelope(manager, stub_run_cli):
    manager.__dict__["version"] = parse_version("1.16.0")
    stub_run_cli(manager, OUTDATED_ENVELOPE)
    packages = list(manager.outdated)
    assert len(packages) == 2
    # Pinned packages are reported: a newer release exists even if pipx's own
    # upgrade skips them.
    assert packages[0].id == "poetry"
    assert str(packages[0].installed_version) == "2.1.0"
    assert str(packages[0].latest_version) == "2.2.0"
    assert packages[1].id == "pycowsay"
    assert str(packages[1].installed_version) == "0.0.0.1"
    assert str(packages[1].latest_version) == "0.0.0.2"


@pytest.mark.parametrize("output", ("", '{"data": {"packages": []}}'))
def test_outdated_native_handles_empty(manager, stub_run_cli, output):
    manager.__dict__["version"] = parse_version("1.16.0")
    stub_run_cli(manager, output)
    assert list(manager.outdated) == []


def test_outdated_legacy_silences_dependencies(manager, monkeypatch):
    """The per-venv pip probe only reports the venv's main package, even when
    the probe also lists its outdated dependencies."""
    manager.__dict__["version"] = parse_version("1.15.2")
    calls = []

    def fake_run_cli(*args, **kwargs):
        calls.append(args)
        return PIP_PROBE if "runpip" in args else INSTALLED_SNAPSHOT

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    packages = list(manager.outdated)
    assert calls == [
        ("list", "--json"),
        (
            "runpip",
            "pycowsay",
            "list",
            "--no-color",
            "--format=json",
            "--outdated",
            "--verbose",
            "--quiet",
        ),
    ]
    assert len(packages) == 1
    assert packages[0].id == "pycowsay"
    assert str(packages[0].installed_version) == "0.0.0.1"
    assert str(packages[0].latest_version) == "0.0.0.2"
