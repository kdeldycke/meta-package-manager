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
"""scoop CLI-construction tests.

These tests stub `run_cli` and exercise the pure-Python branches of the
`Scoop` manager. They do not invoke the real `scoop` binary.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.scoop import Scoop


@pytest.fixture
def manager():
    return Scoop()


@pytest.mark.parametrize(
    ("version", "expected_spec"),
    (
        (None, "hyperfine"),
        ("1.18.0", "hyperfine@1.18.0"),
    ),
)
def test_install_builds_spec(manager, capture_run_cli, version, expected_spec):
    captured = capture_run_cli(manager)
    manager.install("hyperfine", version=version)
    assert captured == [("install", expected_spec)]
