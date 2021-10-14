# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

# pylint: disable=redefined-outer-name

import pytest

from ..pool import DEFAULT_MANAGER_IDS
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "sync"


class TestSync(CLISubCommandTests):
    @pytest.mark.parametrize("mid", DEFAULT_MANAGER_IDS)
    def test_single_manager(self, invoke, subcmd, mid):
        result = invoke("--manager", mid, subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result, {mid})
