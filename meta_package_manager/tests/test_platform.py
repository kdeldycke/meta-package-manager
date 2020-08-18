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

from types import FunctionType

import pytest

from ..managers import pool
from ..platform import (
    ALL_OS_LABELS,
    CURRENT_OS_ID,
    CURRENT_OS_LABEL,
    LINUX,
    MACOS,
    OS_DEFINITIONS,
    WINDOWS,
    current_os,
    is_linux,
    is_macos,
    is_windows,
    os_label,
)
from .conftest import MANAGER_IDS, unless_linux, unless_macos, unless_windows


def test_mutual_exclusion():
    if is_linux():
        assert not is_macos()
        assert not is_windows()
        assert CURRENT_OS_ID == LINUX
        assert CURRENT_OS_LABEL == os_label(LINUX)
    if is_macos():
        assert not is_linux()
        assert not is_windows()
        assert CURRENT_OS_ID == MACOS
        assert CURRENT_OS_LABEL == os_label(MACOS)
    if is_windows():
        assert not is_linux()
        assert not is_macos()
        assert CURRENT_OS_ID == WINDOWS
        assert CURRENT_OS_LABEL == os_label(WINDOWS)


def test_os_definitions():
    assert isinstance(OS_DEFINITIONS, dict)
    # Each OS definition must be unique.
    assert isinstance(ALL_OS_LABELS, frozenset)
    assert len(OS_DEFINITIONS) == len(ALL_OS_LABELS)
    for os_id, data in OS_DEFINITIONS.items():
        # OS ID.
        assert isinstance(os_id, str)
        assert os_id
        assert os_id.isascii()
        assert os_id.isalpha()
        assert os_id.islower()
        # Metadata.
        assert isinstance(data, tuple)
        assert len(data) == 2
        label, os_flag = data
        # OS label.
        assert label
        assert isinstance(label, str)
        assert label.isascii()
        assert label.isalpha()
        assert label in ALL_OS_LABELS
        # OS identification function.
        assert isinstance(os_flag, bool)
        os_id_func_name = "is_{}".format(os_id)
        assert os_id_func_name in globals()
        os_id_func = globals()[os_id_func_name]
        assert isinstance(os_id_func, FunctionType)
        assert isinstance(os_id_func(), bool)
        assert os_id_func() == os_flag


def test_current_os_func():
    # Function.
    os_id, label = current_os()
    assert os_id in OS_DEFINITIONS
    assert label in [os[0] for os in OS_DEFINITIONS.values()]
    # Constants.
    assert os_id == CURRENT_OS_ID
    assert label == CURRENT_OS_LABEL


def test_os_label():
    os_id, os_name = current_os()
    assert os_label(os_id) == os_name


def test_blacklisted_manager():
    """ Check all managers are accounted for on each platforms. """
    blacklists = {
        LINUX: {"brew", "cask", "mas"},
        MACOS: {"apt", "flatpak", "opkg", "snap"},
        WINDOWS: {"apt", "cask", "brew", "flatpak", "mas", "opkg", "snap"},
    }
    blacklist = blacklists[current_os()[0]]
    # List of supported managers on the current platform.
    supported = {m.id for m in pool().values() if m.supported}
    assert supported == MANAGER_IDS - blacklist


# Test unittest decorator helpers.


@unless_linux
def test_unless_linux():
    assert is_linux()
    assert not is_macos()
    assert not is_windows()


@unless_macos
def test_unless_macos():
    assert not is_linux()
    assert is_macos()
    assert not is_windows()


@unless_windows
def test_unless_windows():
    assert not is_linux()
    assert not is_macos()
    assert is_windows()
