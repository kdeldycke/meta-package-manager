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

from meta_package_manager.capabilities import Operations
from meta_package_manager.execution import (
    DEFAULT_TIMEOUT,
    MUTATING_TIMEOUT,
    OPERATION_TIMEOUTS,
    READ_ONLY_TIMEOUT,
    SPINNER_DELAY,
)

from .fake_manager import FakeManager


def test_operation_timeouts_cover_all_operations():
    """Every routable operation must have a per-operation timeout default, so the
    map and the ``Operations`` enum never drift apart."""
    for operation in Operations:
        assert operation.name in OPERATION_TIMEOUTS


def test_read_only_tier_is_shorter_than_mutating_tier():
    """Read-only probes fail faster than state-changing operations."""
    assert READ_ONLY_TIMEOUT < MUTATING_TIMEOUT
    # Unknown operations stay on the conservative (long) side.
    assert DEFAULT_TIMEOUT == MUTATING_TIMEOUT


@pytest.mark.parametrize("active_operation", (None, "version", "search", "install"))
def test_resolve_timeout_explicit_wins(active_operation):
    """An explicit timeout (``--timeout`` or per-manager override) wins for every
    operation, including unknown ones."""
    manager = FakeManager()
    manager.timeout = 42
    manager._active_operation = active_operation
    assert manager._resolve_timeout() == 42


@pytest.mark.parametrize(
    ("active_operation", "expected"),
    (
        ("version", READ_ONLY_TIMEOUT),
        ("installed", READ_ONLY_TIMEOUT),
        ("outdated", READ_ONLY_TIMEOUT),
        ("search", READ_ONLY_TIMEOUT),
        ("install", MUTATING_TIMEOUT),
        ("upgrade", MUTATING_TIMEOUT),
        ("upgrade_all", MUTATING_TIMEOUT),
        ("remove", MUTATING_TIMEOUT),
        ("sync", MUTATING_TIMEOUT),
        ("cleanup", MUTATING_TIMEOUT),
    ),
)
def test_resolve_timeout_per_operation(active_operation, expected):
    """With no explicit timeout, each operation resolves to its tier default."""
    manager = FakeManager()
    manager.timeout = None
    manager._active_operation = active_operation
    assert manager._resolve_timeout() == expected


def test_resolve_timeout_unknown_operation_falls_back_to_default():
    """A CLI call with no known operation gets the conservative default."""
    manager = FakeManager()
    manager.timeout = None
    manager._active_operation = None
    assert manager._resolve_timeout() == DEFAULT_TIMEOUT


def test_make_spinner_disabled_without_progress():
    """Without the progress opt-in, the spinner is forced off."""
    manager = FakeManager()
    manager.progress = False
    assert manager._make_spinner().enabled is False


def test_make_spinner_defers_to_tty_with_progress():
    """With progress on, the spinner is left to auto-detect a TTY at runtime."""
    manager = FakeManager()
    manager.progress = True
    assert manager._make_spinner().enabled is None


def test_make_spinner_label_includes_manager_and_operation():
    manager = FakeManager()
    manager._active_operation = "search"
    label = manager._make_spinner().label
    assert manager.id in label
    assert "search" in label


def test_make_spinner_label_without_operation():
    manager = FakeManager()
    manager._active_operation = None
    assert manager._make_spinner().label == str(manager.id)


def test_make_spinner_uses_configured_delay():
    assert FakeManager()._make_spinner().delay == SPINNER_DELAY
