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
"""Tests for the ProtonPlus inventory and command construction.

The inventory is read from the `.protonplus` records ProtonPlus writes, laid out
here under a scratch home, so these tests neither need `protonplus` nor touch the
real machine. The records are the ones ProtonPlus `0.6.8` wrote on Solus for DXVK
(doitsujin) on Lutris.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from extra_platforms import is_any_windows

from meta_package_manager.managers.protonplus import ProtonPlus

PINNED = (
    '{"runner_endpoint":"https://api.github.com/repos/doitsujin/dxvk/releases",'
    '"runner_title":"DXVK (doitsujin)","tag":"v3.1","provider_id":"dxvk-doitsujin",'
    '"tool_id":"lutris-system/dxvk/dxvk-doitsujin","launcher_id":"lutris-system",'
    '"variant_id":"standard","release_id":"357524779"}'
)
"""The record of `protonplus install lutris-system dxvk-doitsujin` at `v3.1`."""

ROLLING = (
    '{"runner_endpoint":"https://api.github.com/repos/doitsujin/dxvk/releases",'
    '"runner_title":"DXVK (doitsujin)","tag":"v3.1.1","provider_id":"dxvk-doitsujin",'
    '"tool_id":"lutris-system/dxvk/dxvk-doitsujin","launcher_id":"lutris-system",'
    '"variant_id":"standard","release_id":"381956359"}'
)
"""The record of `protonplus install lutris-system dxvk-doitsujin latest`."""


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A scratch home, with the XDG base directories left to their defaults.

    {meth}`pathlib.Path.home` reads `HOME` on POSIX and `USERPROFILE` on Windows.
    """
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(tmp_path))
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(variable, raising=False)
    return tmp_path


def write_record(release_dir: Path, content: str) -> None:
    release_dir.mkdir(parents=True)
    (release_dir / ".protonplus").write_text(content, encoding="UTF-8")


def inventory() -> list[tuple[str, str]]:
    return [
        (package.id, str(package.installed_version))
        for package in ProtonPlus().installed
    ]


def test_installed_lists_a_runner_once_at_its_newest(home):
    dxvk = home / ".local" / "share" / "lutris" / "runtime" / "dxvk"
    write_record(dxvk / "dxvk-3.1", PINNED)
    write_record(dxvk / "DXVK (doitsujin) Latest", ROLLING)
    # Lutris's own directory carries no record, and is not a release.
    (dxvk / "dxvk").mkdir()
    assert inventory() == [("lutris-system/dxvk-doitsujin", "v3.1.1")]


@pytest.mark.skipif(is_any_windows(), reason="A symlink needs privileges on Windows.")
def test_installed_reads_a_symlinked_launcher_once(home):
    """Each record is read once, although three launcher paths reach it.

    With the XDG base directories at their defaults, `$XDG_DATA_HOME/lutris` and
    `~/.local/share/lutris` are one directory, and the Flatpak one links to it.
    """
    lutris = home / ".local" / "share" / "lutris"
    write_record(lutris / "runtime" / "dxvk" / "dxvk-3.1", PINNED)
    flatpak_data = home / ".var" / "app" / "net.lutris.Lutris" / "data"
    flatpak_data.mkdir(parents=True)
    (flatpak_data / "lutris").symlink_to(lutris)
    assert len(list(ProtonPlus._records())) == 1
    assert inventory() == [("lutris-system/dxvk-doitsujin", "v3.1")]


def test_installed_honors_xdg_data_home(home, monkeypatch):
    data = home / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    write_record(data / "lutris" / "runtime" / "dxvk" / "dxvk-3.1", PINNED)
    assert inventory() == [("lutris-system/dxvk-doitsujin", "v3.1")]


@pytest.mark.parametrize(
    "content",
    (
        pytest.param('{"tag":"v3.1"}', id="no_launcher_nor_runner"),
        pytest.param("{", id="truncated"),
        pytest.param("[]", id="not_an_object"),
    ),
)
def test_installed_skips_an_unaddressable_record(home, content):
    dxvk = home / ".local" / "share" / "lutris" / "runtime" / "dxvk"
    write_record(dxvk / "dxvk-3.1", content)
    assert inventory() == []


def test_commands_split_the_package_id(monkeypatch):
    """The ID splits into two arguments, which the docstring corpus cannot check."""
    manager = ProtonPlus()
    monkeypatch.setattr(manager, "cli_path", Path("/usr/bin/protonplus"), raising=False)
    calls = []
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: calls.append(args))

    manager.install("lutris-system/dxvk-doitsujin")
    manager.remove("lutris-system/dxvk-doitsujin")
    assert calls == [
        ("install", "lutris-system", "dxvk-doitsujin", "latest"),
        ("uninstall", "lutris-system", "dxvk-doitsujin", "all"),
    ]
    assert manager.upgrade_one_cli("lutris-system/dxvk-doitsujin")[1:] == (
        "update",
        "lutris-system",
        "dxvk-doitsujin",
    )
    assert manager.upgrade_all_cli()[1:] == ("update", "all")
