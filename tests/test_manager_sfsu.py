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
"""sfsu delegation tests.

`sfsu` ships no mutating verb, so its install, removal and upgrades run the
`scoop` binary through {class}`~meta_package_manager.capabilities.Delegate`.
These tests capture the command that delegation builds. They never run a binary.
"""

from __future__ import annotations

import pytest

from meta_package_manager.capabilities import Delegate, DelegatedMethod
from meta_package_manager.managers.scoop import Scoop
from meta_package_manager.managers.sfsu import SFSU


def test_install_runs_the_scoop_binary(monkeypatch, tmp_path):
    """The delegated install runs `scoop`, without the `--no-color` that `sfsu`
    appends to its own commands. The override ends with the call."""
    manager = SFSU()
    calls: list[tuple] = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return ""

    monkeypatch.setattr(manager, "which", lambda cli_name: tmp_path / cli_name)
    monkeypatch.setattr(manager, "run", fake_run)

    manager.install("hyperfine", version="1.18.0")

    assert calls == [(str(tmp_path / "scoop"), "install", "hyperfine@1.18.0")]
    assert not hasattr(manager, "_delegate_cli_path")


def test_delegated_operation_reads_as_its_descriptor_on_the_class():
    """Read from the class, a delegated operation is the descriptor, which keeps
    the documentation of the method it delegates to."""
    descriptor = SFSU.install
    assert isinstance(descriptor, DelegatedMethod)
    assert descriptor.cli_name == "scoop"
    assert descriptor.__doc__ == Scoop.install.__doc__


def test_delegate_refuses_an_attribute_that_is_not_a_method():
    with pytest.raises(TypeError, match=r"^Scoop\.name is not callable\.$"):
        Delegate(Scoop).name  # noqa: B018
