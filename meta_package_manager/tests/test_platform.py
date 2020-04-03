# -*- coding: utf-8 -*-
#
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

import sys
from types import FunctionType

import pytest

from ..managers import pool
from ..platform import (
    LINUX,
    MACOS,
    OS_DEFINITIONS,
    WINDOWS,
    current_os,
    is_linux,
    is_macos,
    is_windows,
    os_label
)
from .case import ManagerTestCase, unless_linux, unless_macos, unless_windows


def test_os_id_func():
    for os_id_func in [is_macos, is_linux, is_windows]:
        assert isinstance(os_id_func, FunctionType)
        assert isinstance(os_id_func(), bool)


def test_mutual_exclusion():
    if is_linux():
        assert not is_macos()
        assert not is_windows()
    if is_macos():
        assert not is_linux()
        assert not is_windows()
    if is_windows():
        assert not is_linux()
        assert not is_macos()


def test_os_definitions():
    assert isinstance(OS_DEFINITIONS, dict)
    for k, v in OS_DEFINITIONS.items():
        # OS ID.
        assert isinstance(k, str)
        assert k
        assert k.isascii()
        assert k.isalpha()
        assert k.islower()
        # Metadata.
        assert isinstance(v, tuple)
        assert len(v) == 2
        # OS Label.
        os_label = v[0]
        assert os_label
        assert isinstance(os_label, str)
        assert os_label.isascii()
        assert os_label.isalpha()
        # OS identification function.
        os_id_func = v[1]
        assert os_id_func
        assert isinstance(os_id_func, FunctionType)
        assert os_id_func.__name__ == 'is_{}'.format(k)
    # Each OS definition must be unique.
    assert len(OS_DEFINITIONS) == len({v[0] for v in OS_DEFINITIONS.values()})
    assert len(OS_DEFINITIONS) == len({v[1] for v in OS_DEFINITIONS.values()})


def test_current_os():
    os_id, os_label = current_os()
    assert os_id in OS_DEFINITIONS
    assert os_label in [os[0] for os in OS_DEFINITIONS.values()]


def test_unrecognized_os(monkeypatch):
    monkeypatch.setattr(sys, "platform", "foobar")
    with pytest.raises(SystemError):
        current_os()


def test_os_label():
    os_id, os_name = current_os()
    assert os_label(os_id) == os_name


def test_blacklisted_manager():
    """ Check all managers are accounted for on each platforms. """
    blacklists = {
        LINUX: {'brew', 'cask', 'mas'},
        MACOS: {'apt', 'flatpak', 'opkg'},
        WINDOWS: {'apt', 'cask', 'brew', 'flatpak', 'mas', 'opkg'}
    }
    blacklist = blacklists[current_os()[0]]
    # List of supported managers on the current platform.
    supported = {m.id for m in pool().values() if m.supported}
    assert supported == ManagerTestCase.MANAGER_IDS - blacklist


# Test unittest decorator helpers.

@unless_linux()
def test_unless_linux():
    assert is_linux()
    assert not is_macos()
    assert not is_windows()


@unless_macos()
def test_unless_macos():
    assert not is_linux()
    assert is_macos()
    assert not is_windows()


@unless_windows()
def test_unless_windows():
    assert not is_linux()
    assert not is_macos()
    assert is_windows()
