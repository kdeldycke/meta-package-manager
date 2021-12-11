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


from functools import partial

import pytest
from click_extra.tests.conftest import create_config
from click_extra.tests.conftest import invoke as invoke_extra
from click_extra.tests.conftest import runner

from ..cli import mpm

""" Fixtures, configuration and helpers for tests. """


@pytest.fixture
def invoke(invoke_extra):
    return partial(invoke_extra, mpm)


@pytest.fixture(scope="class")
def subcmd():
    """Fixture used in ``test_cli_*.py`` files to set the sub-command in all CLI
    calls.

    Must returns a string or an iterable of strings. Defaults to ``None``, which
    allows tests relying on this fixture to selectively skip running.
    """
    return None
