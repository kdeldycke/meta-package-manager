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

"""Vagrant output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.vagrant.Vagrant`. They never call
`vagrant`.
"""

from __future__ import annotations

from meta_package_manager.managers.vagrant import Vagrant

SEARCH_OUTPUT = """\
[
  {
    "name": "ubuntu/jammy64",
    "version": "20240126.0.0",
    "downloads": "1,234,567",
    "providers": "virtualbox",
    "architectures": "amd64"
  }
]"""
"""`vagrant cloud search ubuntu --json`, as the docstring of
{meth}`~meta_package_manager.managers.vagrant.Vagrant.search` shows it."""


def test_search_reads_the_registry_answer(capture_run_cli):
    """A box gives its full name and its latest version."""
    manager = Vagrant()
    calls = capture_run_cli(manager, SEARCH_OUTPUT)
    packages = [
        (p.id, str(p.latest_version))
        for p in manager.search("ubuntu", extended=False, exact=False)
    ]
    assert packages == [("ubuntu/jammy64", "20240126.0.0")]
    assert calls == [("cloud", "search", "ubuntu", "--json")]
