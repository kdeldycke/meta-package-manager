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

import logging
from datetime import datetime, timedelta, timezone

import pytest
from click.exceptions import BadParameter

from meta_package_manager.cli import Duration, cooldown_permits
from meta_package_manager.managers.cargo import Cargo
from meta_package_manager.managers.homebrew import Homebrew
from meta_package_manager.managers.npm import NPM
from meta_package_manager.managers.pip import Pip
from meta_package_manager.managers.pipx import Pipx
from meta_package_manager.managers.uv import UV, UVX

"""Test the supply-chain release-age cooldown feature."""


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        # Friendly durations.
        ("7 days", timedelta(days=7)),
        ("1 week", timedelta(weeks=1)),
        ("2 weeks", timedelta(weeks=2)),
        ("3d", timedelta(days=3)),
        ("12h", timedelta(hours=12)),
        ("30m", timedelta(minutes=30)),
        ("45s", timedelta(seconds=45)),
        ("1.5d", timedelta(days=1, hours=12)),
        # A bare number defaults to days.
        ("7", timedelta(days=7)),
        # Spacing and case are irrelevant.
        ("  6   HOURS  ", timedelta(hours=6)),
        # ISO 8601 durations.
        ("P7D", timedelta(days=7)),
        ("P1W", timedelta(weeks=1)),
        ("PT12H", timedelta(hours=12)),
        ("PT30M", timedelta(minutes=30)),
        ("PT45S", timedelta(seconds=45)),
        ("P1WT6H", timedelta(weeks=1, hours=6)),
        ("P2DT3H30M", timedelta(days=2, hours=3, minutes=30)),
        # ISO 8601 is case-insensitive.
        ("p7d", timedelta(days=7)),
        ("pt12h", timedelta(hours=12)),
        # Zero and empty values disable the gate.
        ("0", None),
        ("0 days", None),
        ("PT0H", None),
        ("", None),
        (None, None),
    ),
)
def test_duration_parsing(value, expected):
    assert Duration().convert(value, None, None) == expected


def test_duration_passthrough_timedelta():
    """An already-parsed timedelta is returned unchanged (idempotent conversion)."""
    delta = timedelta(days=2)
    assert Duration().convert(delta, None, None) is delta


@pytest.mark.parametrize(
    "value",
    (
        "bogus",
        "2 fortnights",
        "abc",
        "tomorrow",
        "-3d",
        # Bare ISO 8601 prefix with no components.
        "P",
        # Unknown ISO 8601 unit.
        "P3X",
        # Date without a time zone.
        "2024-05-01",
        "2024-05-01T00:00:00",
        # Malformed RFC 3339 timestamp.
        "2024-99-99T00:00:00Z",
    ),
)
def test_duration_invalid(value):
    with pytest.raises(BadParameter):
        Duration().convert(value, None, None)


@pytest.mark.parametrize(
    "value",
    (
        # Friendly form.
        "7 months",
        "1 year",
        "3 months",
        "2 years",
        # ISO 8601 form (M before T = months, Y = years).
        "P3M",
        "P1Y",
        "P1Y6M",
    ),
)
def test_duration_rejects_calendar_units(value):
    """Months and years are explicitly rejected because their length is ambiguous."""
    with pytest.raises(BadParameter) as exc_info:
        Duration().convert(value, None, None)
    assert "calendar units" in str(exc_info.value)
    assert "ambiguous" in str(exc_info.value)


@pytest.mark.parametrize(
    "value",
    (
        # Z suffix.
        "2024-05-01T00:00:00Z",
        # Explicit UTC offset.
        "2024-05-01T00:00:00+00:00",
        # Non-UTC offset.
        "2024-05-01T02:00:00+02:00",
        # Lowercase T and Z accepted.
        "2024-05-01t00:00:00z",
    ),
)
def test_duration_absolute_timestamp(value):
    """An RFC 3339 timestamp is converted to ``now - timestamp`` at parse time."""
    result = Duration().convert(value, None, None)
    expected = datetime.now(tz=timezone.utc) - datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert isinstance(result, timedelta)
    assert abs(result - expected) < timedelta(seconds=5)


def test_duration_future_timestamp_disables_gate():
    """A timestamp in the future is treated as 'no cooldown' (returns None)."""
    assert Duration().convert("2999-01-01T00:00:00Z", None, None) is None


@pytest.mark.parametrize(
    ("cooldown_input", "release_iso", "should_pass"),
    (
        # idna 3.6 was published 2023-11-25.
        # idna 3.7 was published 2024-04-11.
        # Anchor cooldown=P7D against a fake "today" of 2024-04-15:
        # cutoff = 2024-04-08, so 3.6 (older) passes but 3.7 (Apr 11) is blocked.
        # We assert the cutoff math directly since it does not depend on a real
        # registry call.
        ("P7D", "2023-11-25T00:00:00Z", True),  # idna 3.6: older than cutoff.
        ("P7D", "2024-04-11T00:00:00Z", False),  # idna 3.7: newer than cutoff.
    ),
)
def test_release_anchored_cutoff_math(
    cooldown_input, release_iso, should_pass, monkeypatch
):
    """Verify the cooldown cutoff blocks fresh releases and lets older ones pass.

    Pattern borrowed from astral-sh/uv#19475: anchor against real upstream
    release timestamps (idna 3.6 / 3.7 on PyPI) and a frozen 'today' so the
    arithmetic stays deterministic.
    """
    fake_now = datetime(2024, 4, 15, tzinfo=timezone.utc)
    cooldown = Duration().convert(cooldown_input, None, None)
    assert cooldown is not None
    cutoff = fake_now - cooldown
    release_time = datetime.fromisoformat(release_iso.replace("Z", "+00:00"))
    assert (release_time <= cutoff) is should_pass


@pytest.mark.parametrize(
    ("manager_class", "env_var"),
    (
        (NPM, "npm_config_min-release-age"),
        (Pip, "PIP_UPLOADED_PRIOR_TO"),
        (Pipx, "PIP_UPLOADED_PRIOR_TO"),
        (UV, "UV_EXCLUDE_NEWER"),
        (UVX, "UV_EXCLUDE_NEWER"),
    ),
)
def test_supported_managers_advertise_cooldown(manager_class, env_var):
    manager = manager_class()
    assert manager.supports_cooldown is True
    assert manager.cooldown_env_var == env_var


@pytest.mark.parametrize("manager_class", (Cargo, Homebrew))
def test_unsupported_managers_lack_cooldown(manager_class):
    manager = manager_class()
    assert manager.supports_cooldown is False
    assert manager.cooldown_env_var is None
    # Even with a cooldown set, no environment is injected.
    manager.cooldown = timedelta(days=7)
    assert manager.cooldown_env() == {}


@pytest.mark.parametrize("manager_class", (Pip, Pipx, UV, UVX))
def test_timestamp_based_managers_inject_cutoff(manager_class):
    """Managers whose env var expects an RFC 3339 cutoff timestamp."""
    manager = manager_class()
    # No cooldown means no injection.
    assert manager.cooldown_env() == {}
    # A cooldown injects exactly one env var holding an RFC 3339 cutoff in the past.
    manager.cooldown = timedelta(days=7)
    env = manager.cooldown_env()
    assert set(env) == {manager.cooldown_env_var}
    cutoff = datetime.fromisoformat(env[manager.cooldown_env_var])
    now = datetime.now(tz=timezone.utc)
    # The cutoff sits roughly one cooldown in the past (a minute of slack).
    assert abs((now - cutoff) - timedelta(days=7)) < timedelta(minutes=1)


@pytest.mark.parametrize(
    ("cooldown", "expected_days"),
    (
        (timedelta(days=7), "7"),
        (timedelta(weeks=2), "14"),
        (timedelta(days=1), "1"),
        # Sub-day durations round up to avoid silently disabling the gate.
        (timedelta(hours=12), "1"),
        (timedelta(hours=25), "2"),
        (timedelta(seconds=1), "1"),
    ),
)
def test_npm_injects_integer_days(cooldown, expected_days):
    """npm's ``min-release-age`` expects an integer count of days, not a timestamp."""
    manager = NPM()
    assert manager.cooldown_env() == {}
    manager.cooldown = cooldown
    assert manager.cooldown_env() == {"npm_config_min-release-age": expected_days}


def test_cooldown_permits_without_cooldown():
    manager = Homebrew()
    manager.cooldown = None
    assert cooldown_permits(manager) is True


def test_cooldown_permits_supported_manager():
    manager = UV()
    manager.cooldown = timedelta(days=7)
    assert cooldown_permits(manager) is True


def test_cooldown_permits_blocks_unsupported(caplog):
    caplog.set_level(logging.WARNING)
    manager = Homebrew()
    manager.cooldown = timedelta(days=7)
    manager.require_cooldown_support = True
    assert cooldown_permits(manager) is False
    assert "cannot enforce" in caplog.text
    assert "--allow-unsupported-managers" in caplog.text


def test_cooldown_permits_allows_unsupported_on_opt_in(caplog):
    caplog.set_level(logging.WARNING)
    manager = Homebrew()
    manager.cooldown = timedelta(days=7)
    manager.require_cooldown_support = False
    assert cooldown_permits(manager) is True
    assert "without the supply-chain safeguard" in caplog.text


def test_cli_rejects_invalid_cooldown(invoke):
    result = invoke("--cooldown", "bogus", "managers")
    assert result.exit_code == 2
    assert "not a valid duration" in result.stderr
