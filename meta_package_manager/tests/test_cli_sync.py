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


from __future__ import annotations

import pytest

from .test_cli import CLISubCommandTests


@pytest.fixture()
def subcmd():
    return "sync"


class TestSync(CLISubCommandTests):
    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (f"Sync {mid} package info..." in stderr,)
