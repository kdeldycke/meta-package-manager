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

import gc
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from click_extra import Duration

from meta_package_manager.capabilities import cooldown_is_synthesized
from meta_package_manager.cli import _package_task
from meta_package_manager.cli_maintenance import _attempt_install, cooldown_permits
from meta_package_manager.cooldown import (
    Cooldown,
    CooldownPolicy,
    CooldownSettings,
    parse_cooldown_section,
    resolve_cooldown,
)
from meta_package_manager.execution import CLIError
from meta_package_manager.manager import COOLDOWN_EXEMPT
from meta_package_manager.managers.flatpak import Flatpak
from meta_package_manager.managers.gem import Gem
from meta_package_manager.managers.homebrew import Homebrew
from meta_package_manager.managers.mas import MAS
from meta_package_manager.managers.npm import NPM
from meta_package_manager.managers.pacman import _YAY_COOLDOWN_INIT_LUA, Paru, Yay
from meta_package_manager.managers.pip import Pip
from meta_package_manager.managers.pipx import Pipx
from meta_package_manager.managers.uv import UV, UVX
from meta_package_manager.specifier import Specifier
from meta_package_manager.version import parse_version

"""Test the supply-chain release-age cooldown feature.

Parsing of the `--cooldown` value itself (friendly, ISO 8601 and RFC 3339
shapes, calendar-unit rejection, zero / future-timestamp disabling) is covered
upstream by click-extra's `Duration` test suite: only the cooldown semantics
built on top of the parsed `timedelta` are exercised here."""


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


@pytest.mark.parametrize("manager_class", (Gem, Homebrew))
def test_ungateable_managers_lack_cooldown(manager_class):
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
    """npm's `min-release-age` expects an integer count of days, not a timestamp."""
    manager = NPM()
    assert manager.cooldown_env() == {}
    manager.cooldown = cooldown
    assert manager.cooldown_env() == {"npm_config_min-release-age": expected_days}


def test_yay_advertises_cooldown_while_idle():
    """While idle, yay reports its structural capability without a version probe.

    The import-time `COOLDOWN_SUPPORTED_MANAGERS` help text reads this for every
    manager, so it must never shell out to `yay --version`.
    """
    manager = Yay()
    assert manager.cooldown is None
    assert manager.supports_cooldown is True
    assert manager.cooldown_env_var == "XDG_CONFIG_HOME"
    assert "version" not in manager.__dict__
    assert manager.cooldown_env() == {}


@pytest.mark.parametrize(
    ("version", "supported"),
    (
        ("13.0.0", True),
        ("13.0.2", True),
        ("14.1.0", True),
        ("12.4.2", False),
        ("11.0.0", False),
    ),
)
def test_yay_cooldown_version_gate(version, supported):
    """yay can enforce a cooldown only from v13.0.0, when its Lua hooks landed."""
    manager = Yay()
    # Bypass the live `yay --version` probe with a parsed fake.
    manager.__dict__["version"] = parse_version(version)
    manager.cooldown = timedelta(days=7)
    assert manager.supports_cooldown is supported
    # An unsupported version must never inject a half-configured environment.
    if not supported:
        assert manager.cooldown_env() == {}


def test_yay_cooldown_undetectable_version():
    """A yay whose version cannot be parsed cannot enforce a cooldown."""
    manager = Yay()
    manager.__dict__["version"] = None
    manager.cooldown = timedelta(days=7)
    assert manager.supports_cooldown is False
    assert manager.cooldown_env() == {}


def test_yay_cooldown_policy_gates_both_paths():
    """The generated policy gates upgrades and installs off the same cutoff."""
    assert 'create_autocmd("UpgradeSelect"' in _YAY_COOLDOWN_INIT_LUA
    assert 'create_autocmd("AURPreInstall"' in _YAY_COOLDOWN_INIT_LUA
    assert "MPM_COOLDOWN_EPOCH" in _YAY_COOLDOWN_INIT_LUA


@pytest.mark.parametrize(
    ("env", "expected"),
    (
        ({"XDG_CONFIG_HOME": "/xdg", "HOME": "/home/u"}, Path("/xdg/yay")),
        ({"HOME": "/home/u"}, Path("/home/u/.config/yay")),
        ({}, None),
    ),
)
def test_yay_user_config_dir(env, expected, monkeypatch):
    """The real config dir follows yay's own XDG_CONFIG_HOME over HOME precedence."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert Yay._user_yay_config_dir() == expected


def test_yay_cooldown_overlay(tmp_path, monkeypatch):
    """An active cooldown on a recent yay builds a lossless XDG_CONFIG_HOME overlay."""
    user_cfg = tmp_path / ".config" / "yay"
    user_cfg.mkdir(parents=True)
    (user_cfg / "config.json").write_text("{}")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    manager = Yay()
    manager.__dict__["version"] = parse_version("13.0.2")
    manager.cooldown = timedelta(days=7)
    env = manager.cooldown_env()

    assert set(env) == {"XDG_CONFIG_HOME", "MPM_COOLDOWN_EPOCH", "MPM_YAY_USER_DIR"}
    assert env["MPM_YAY_USER_DIR"] == str(user_cfg)

    # The cutoff sits roughly one cooldown in the past (a minute of slack).
    epoch = env["MPM_COOLDOWN_EPOCH"]
    assert epoch is not None
    cutoff = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    assert abs((now - cutoff) - timedelta(days=7)) < timedelta(minutes=1)

    # The overlay carries the generated policy and a symlink back to the real config.
    xdg_home = env["XDG_CONFIG_HOME"]
    assert xdg_home is not None
    overlay = Path(xdg_home) / "yay"
    assert (overlay / "init.lua").read_text(encoding="UTF-8") == _YAY_COOLDOWN_INIT_LUA
    config_link = overlay / "config.json"
    assert config_link.is_symlink()
    assert config_link.resolve() == (user_cfg / "config.json").resolve()

    # The directory is memoized, so repeated calls reuse the same overlay.
    assert manager.cooldown_env()["XDG_CONFIG_HOME"] == env["XDG_CONFIG_HOME"]


def test_yay_cooldown_overlay_without_user_config(tmp_path, monkeypatch):
    """With no user config present, the overlay omits the config.json symlink."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    manager = Yay()
    manager.__dict__["version"] = parse_version("13.0.2")
    manager.cooldown = timedelta(days=7)
    env = manager.cooldown_env()

    xdg_home = env["XDG_CONFIG_HOME"]
    assert xdg_home is not None
    overlay = Path(xdg_home) / "yay"
    assert (overlay / "init.lua").is_file()
    assert not (overlay / "config.json").exists()


def test_yay_cooldown_overlay_survives_manager_gc(tmp_path, monkeypatch):
    """The overlay must outlive the Yay instance's garbage collection.

    Cleanup is registered with `atexit`, not `weakref.finalize(self, ...)`: yay
    re-reads `init.lua` mid-run, so a GC-tied removal could delete the overlay before
    yay finishes and silently fail the gate open.
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    manager = Yay()
    manager.__dict__["version"] = parse_version("13.0.2")
    manager.cooldown = timedelta(days=7)
    xdg_home = manager.cooldown_env()["XDG_CONFIG_HOME"]
    assert xdg_home is not None
    init_lua = Path(xdg_home) / "yay" / "init.lua"
    assert init_lua.is_file()

    del manager
    gc.collect()
    assert init_lua.is_file(), "overlay deleted when the Yay instance was collected"


def test_yay_cooldown_epoch_clamped_to_zero(tmp_path, monkeypatch):
    """A cooldown reaching before 1970 clamps the epoch to 0.

    A negative Unix timestamp parses back to nil in yay's gopher-lua, which silently
    drops the gate; epoch 0 keeps the floor effective.
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    manager = Yay()
    manager.__dict__["version"] = parse_version("13.0.2")
    manager.cooldown = timedelta(days=40000)  # ~109 years: cutoff predates 1970.
    assert manager.cooldown_env()["MPM_COOLDOWN_EPOCH"] == "0"


def test_yay_cooldown_no_recursion_when_version_resolved_lazily(tmp_path, monkeypatch):
    """Resolving the version lazily under an active cooldown must not recurse.

    `version` runs `yay --version` through `run()`, which injects
    `cooldown_env()`, which consults `supports_cooldown` -> `version`. The
    re-entrancy guard must break that loop. Regression for a live `RecursionError`
    the pre-seeded-version tests above could not catch.
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    manager = Yay()
    manager.cooldown = timedelta(days=7)
    # Make the binary look present so the `version` property actually probes.
    manager.__dict__["supported"] = True
    manager.__dict__["executable"] = True

    def fake_run_cli(*args, **kwargs):
        # The real run() injects cooldown_env() on every CLI call; mimic that so the
        # version probe re-enters cooldown_env -> supports_cooldown -> version.
        manager.cooldown_env()
        return "yay v13.0.2 - libalpm v13.0.1"

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)

    # Must terminate and resolve correctly (used to raise RecursionError).
    assert str(manager.version) == "13.0.2"
    assert manager.supports_cooldown is True
    assert set(manager.cooldown_env()) == {
        "XDG_CONFIG_HOME",
        "MPM_COOLDOWN_EPOCH",
        "MPM_YAY_USER_DIR",
    }


_FLATPAK_REMOTE_INFO_OUTPUT = """\
GNOME Dictionary - Check word definitions and spellings

        ID: org.gnome.Dictionary
       Ref: app/org.gnome.Dictionary/x86_64/stable
      Arch: x86_64
    Branch: stable
Collection: org.flathub.Stable
    Commit: 5697aaea8f6a55b02c34e77504cbe4e419257b482ec7cba434255f5bd6f4
   Subject: Export org.gnome.Dictionary
      Date: 2020-12-08 12:00:26 +0000
"""


def _probed_flatpak(monkeypatch, dates, cooldown=timedelta(days=7)):
    """A flatpak manager whose release-date probe answers from `dates`."""
    manager = Flatpak()
    manager.cooldown = cooldown
    monkeypatch.setattr(manager, "release_date", dates.get)
    return manager


@pytest.mark.parametrize("manager_class", (Flatpak, MAS, Paru))
def test_probe_managers_advertise_synthesized_cooldown(manager_class):
    manager = manager_class()
    assert manager.supports_cooldown is True
    assert manager.cooldown_env_var is None
    # The gate runs through the probe: no environment is ever injected.
    manager.cooldown = timedelta(days=7)
    assert manager.cooldown_env() == {}


def test_cooldown_is_synthesized_classifier():
    assert cooldown_is_synthesized(Flatpak) is True
    assert cooldown_is_synthesized(MAS) is True
    assert cooldown_is_synthesized(Paru) is True
    # A native env var (npm), an env-var overlay (yay) and an ungateable
    # manager (brew) all sit outside the synthesized classification.
    assert cooldown_is_synthesized(NPM) is False
    assert cooldown_is_synthesized(Yay) is False
    assert cooldown_is_synthesized(Homebrew) is False


def test_cooldown_permits_probe_backed_manager():
    manager = Flatpak()
    manager.cooldown = timedelta(days=7)
    assert cooldown_permits(manager) is True


def test_hold_reason_inactive_without_cooldown(monkeypatch):
    manager = Flatpak()
    monkeypatch.setattr(
        manager,
        "release_date",
        lambda package_id: pytest.fail("probe must not run without a cooldown"),
    )
    assert manager.cooldown_hold_reason("org.example.Fig") is None


def test_hold_reason_passes_aged_release(monkeypatch):
    aged = datetime.now(tz=timezone.utc) - timedelta(days=30)
    manager = _probed_flatpak(monkeypatch, {"org.example.Fig": aged})
    assert manager.cooldown_hold_reason("org.example.Fig") is None


def test_hold_reason_holds_fresh_release(monkeypatch):
    fresh = datetime.now(tz=timezone.utc) - timedelta(days=1)
    manager = _probed_flatpak(monkeypatch, {"org.example.Kiwi": fresh})
    reason = manager.cooldown_hold_reason("org.example.Kiwi")
    assert reason is not None
    assert "within the cooldown window" in reason


def test_hold_reason_fail_closed_on_unknown_date(monkeypatch):
    manager = _probed_flatpak(monkeypatch, {})
    reason = manager.cooldown_hold_reason("org.example.Plum")
    assert reason == "its latest release cannot be dated (fail-closed)"


def test_hold_reason_fail_closed_on_probe_error(monkeypatch):
    manager = Flatpak()
    manager.cooldown = timedelta(days=7)

    def broken_probe(package_id):
        raise CLIError(1, "", "error: nothing matches org.example.Plum")

    monkeypatch.setattr(manager, "release_date", broken_probe)
    reason = manager.cooldown_hold_reason("org.example.Plum")
    assert reason == "its latest release cannot be dated (fail-closed)"


def test_hold_reason_best_effort_waives_unknown_date(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    manager = _probed_flatpak(monkeypatch, {})
    manager.cooldown_policy = CooldownPolicy.best_effort
    assert manager.cooldown_hold_reason("org.example.Plum") is None
    assert "without the supply-chain safeguard" in caplog.text


def test_hold_reason_off_policy_skips_probe(monkeypatch):
    manager = Flatpak()
    manager.cooldown = timedelta(days=7)
    manager.cooldown_policy = CooldownPolicy.off
    monkeypatch.setattr(
        manager,
        "release_date",
        lambda package_id: pytest.fail("probe must not run under an off policy"),
    )
    assert manager.cooldown_hold_reason("org.example.Fig") is None


def test_hold_reason_dry_run_skips_probe(monkeypatch):
    manager = Flatpak()
    manager.cooldown = timedelta(days=7)
    manager.dry_run = True
    monkeypatch.setattr(
        manager,
        "release_date",
        lambda package_id: pytest.fail("probe must not run under --dry-run"),
    )
    assert manager.cooldown_hold_reason("org.example.Fig") is None


def test_hold_reason_naive_datetime_read_as_utc(monkeypatch):
    fresh_naive = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    manager = _probed_flatpak(monkeypatch, {"org.example.Kiwi": fresh_naive})
    assert manager.cooldown_hold_reason("org.example.Kiwi") is not None


def test_synthesized_gate_reroutes_upgrade_all(monkeypatch):
    """An active probe-backed cooldown swaps the native one-shot upgrade for the
    per-package path: eligible packages upgrade, too-fresh ones are held."""
    manager = Flatpak()
    manager.cooldown = timedelta(days=7)
    now = datetime.now(tz=timezone.utc)
    dates = {
        "org.example.Fig": now - timedelta(days=30),
        "org.example.Kiwi": now - timedelta(days=1),
    }
    monkeypatch.setattr(manager, "release_date", dates.get)
    outdated = tuple(
        SimpleNamespace(id=package_id, installed_version="1.0", latest_version="2.0")
        for package_id in sorted(dates)
    )
    monkeypatch.setattr(Flatpak, "outdated", property(lambda self: iter(outdated)))
    monkeypatch.setattr(
        manager,
        "upgrade_all_cli",
        lambda: pytest.fail("the native one-shot upgrade must not run"),
    )
    monkeypatch.setattr(
        manager,
        "upgrade_one_cli",
        lambda package_id, version=None: ("flatpak", "update", package_id),
    )
    ran = []

    def fake_run(*args, **kwargs):
        ran.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", fake_run)
    manager.upgrade()
    assert ran == [("flatpak", "update", "org.example.Fig")]


def test_upgrade_all_without_cooldown_keeps_native_path(monkeypatch):
    manager = Flatpak()
    assert manager.cooldown is None
    monkeypatch.setattr(
        manager,
        "upgrade_all_cli",
        lambda: ("flatpak", "update", "--noninteractive"),
    )
    ran = []

    def fake_run(*args, **kwargs):
        ran.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", fake_run)
    manager.upgrade()
    assert ran == [("flatpak", "update", "--noninteractive")]


def test_flatpak_release_date_reads_installed_origin(monkeypatch):
    manager = Flatpak()
    monkeypatch.setitem(
        manager.__dict__, "installed_ids", frozenset({"org.gnome.Dictionary"})
    )

    def fake_run_cli(*args, **kwargs):
        if args[0] == "info":
            return "ID: org.gnome.Dictionary\nOrigin: flathub\n"
        assert args[0] == "remote-info"
        assert args[2] == "flathub"
        return _FLATPAK_REMOTE_INFO_OUTPUT

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    published = manager.release_date("org.gnome.Dictionary")
    assert published == datetime(2020, 12, 8, 12, 0, 26, tzinfo=timezone.utc)


def test_flatpak_release_date_probes_every_remote_for_a_new_app(monkeypatch):
    manager = Flatpak()
    monkeypatch.setitem(manager.__dict__, "installed_ids", frozenset())

    def fake_run_cli(*args, **kwargs):
        if args[0] == "remotes":
            return "fedora\nflathub\n"
        assert args[0] == "remote-info"
        if args[2] == "fedora":
            raise CLIError(1, "", "error: nothing matches org.gnome.Dictionary")
        return _FLATPAK_REMOTE_INFO_OUTPUT

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    published = manager.release_date("org.gnome.Dictionary")
    assert published == datetime(2020, 12, 8, 12, 0, 26, tzinfo=timezone.utc)


def test_flatpak_release_date_none_without_date_line(monkeypatch):
    manager = Flatpak()
    monkeypatch.setitem(manager.__dict__, "installed_ids", frozenset())

    def fake_run_cli(*args, **kwargs):
        if args[0] == "remotes":
            return "flathub\n"
        return "ID: org.gnome.Dictionary\n"

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    assert manager.release_date("org.gnome.Dictionary") is None


_PARU_AUR_INFO_OUTPUT = """\
Repository      : aur
Name            : paru
Version         : 2.1.0-1
Description     : Feature packed AUR helper
First Submitted : Wed, 21 Oct 2020 20:07:31
Last Modified   : Sat, 12 Jul 2025 14:52:15
Out Of Date     : No
"""

_PARU_REPO_INFO_OUTPUT = """\
Repository      : extra
Name            : firefox
Version         : 141.0-1
Description     : Fast, Private & Safe Web Browser
Build Date      : Tue, 22 Jul 2025 09:14:02
"""


def test_paru_release_date_reads_aur_last_modified(monkeypatch):
    manager = Paru()
    monkeypatch.setattr(
        manager, "run_cli", lambda *args, **kwargs: _PARU_AUR_INFO_OUTPUT
    )
    published = manager.release_date("paru")
    assert published == datetime(2025, 7, 12, 14, 52, 15, tzinfo=timezone.utc)


def test_paru_release_date_parses_space_padded_days(monkeypatch):
    output = _PARU_AUR_INFO_OUTPUT.replace(
        "Sat, 12 Jul 2025 14:52:15", "Wed,  2 Jul 2025 08:01:02"
    )
    manager = Paru()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    published = manager.release_date("paru")
    assert published == datetime(2025, 7, 2, 8, 1, 2, tzinfo=timezone.utc)


def test_paru_release_date_exempts_repository_packages(monkeypatch):
    manager = Paru()
    monkeypatch.setattr(
        manager, "run_cli", lambda *args, **kwargs: _PARU_REPO_INFO_OUTPUT
    )
    assert manager.release_date("firefox") is COOLDOWN_EXEMPT


def test_paru_release_date_none_on_unparsable_date(monkeypatch):
    output = _PARU_AUR_INFO_OUTPUT.replace(
        "Sat, 12 Jul 2025 14:52:15", "sometime last summer"
    )
    manager = Paru()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    assert manager.release_date("paru") is None


def test_paru_release_date_none_without_fields(monkeypatch):
    manager = Paru()
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: "Name : paru\n")
    assert manager.release_date("paru") is None


def test_hold_reason_passes_exempt_sentinel(monkeypatch):
    manager = _probed_flatpak(monkeypatch, {"org.example.Fig": COOLDOWN_EXEMPT})
    assert manager.cooldown_hold_reason("org.example.Fig") is None


def test_paru_gated_upgrade_all_rides_the_ignore_flag(monkeypatch):
    """Held AUR packages are excluded from the single `--sysupgrade`
    transaction instead of rerouting to per-package upgrades."""
    manager = Paru()
    manager.cooldown = timedelta(days=7)
    now = datetime.now(tz=timezone.utc)
    dates = {
        "fig": COOLDOWN_EXEMPT,
        "kiwi": now - timedelta(days=1),
        "plum": now - timedelta(days=30),
    }
    monkeypatch.setattr(manager, "release_date", dates.get)
    outdated = tuple(
        SimpleNamespace(id=package_id, installed_version="1.0", latest_version="2.0")
        for package_id in sorted(dates)
    )
    monkeypatch.setattr(Paru, "outdated", property(lambda self: iter(outdated)))
    monkeypatch.setattr(manager, "build_cli", lambda *args, sudo=False: ("paru", *args))
    ran = []

    def fake_run(*args, **kwargs):
        ran.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", fake_run)
    manager.upgrade()
    assert ran == [
        ("paru", "--sync", "--refresh", "--sysupgrade", "--ignore=kiwi"),
    ]


def test_paru_gated_upgrade_all_without_holds_keeps_native_cli(monkeypatch):
    manager = Paru()
    manager.cooldown = timedelta(days=7)
    aged = datetime.now(tz=timezone.utc) - timedelta(days=30)
    monkeypatch.setattr(
        manager, "release_date", {"fig": COOLDOWN_EXEMPT, "plum": aged}.get
    )
    outdated = tuple(
        SimpleNamespace(id=package_id, installed_version="1.0", latest_version="2.0")
        for package_id in ("fig", "plum")
    )
    monkeypatch.setattr(Paru, "outdated", property(lambda self: iter(outdated)))
    monkeypatch.setattr(manager, "build_cli", lambda *args, sudo=False: ("paru", *args))
    ran = []

    def fake_run(*args, **kwargs):
        ran.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", fake_run)
    manager.upgrade()
    assert ran == [("paru", "--sync", "--refresh", "--sysupgrade")]


def test_mas_release_date_reads_catalog_record(monkeypatch):
    manager = MAS()

    def fake_run_cli(*args, **kwargs):
        assert args == ("lookup", "999999999", "--json")
        return (
            '{"adamID":999999999,"currentVersionReleaseDate":'
            '"2020-03-18T17:39:23Z","name":"Papaya","version":"2.0"}'
        )

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)
    published = manager.release_date("999999999")
    assert published == datetime(2020, 3, 18, 17, 39, 23, tzinfo=timezone.utc)


def test_mas_release_date_none_without_date_field(monkeypatch):
    manager = MAS()
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: '{"adamID":999999999,"name":"Papaya"}',
    )
    assert manager.release_date("999999999") is None


def test_mas_release_date_none_on_unparsable_date(monkeypatch):
    manager = MAS()
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: (
            '{"adamID":999999999,"currentVersionReleaseDate":"soon","name":"Papaya"}'
        ),
    )
    assert manager.release_date("999999999") is None


def test_attempt_install_reports_cooldown_status(monkeypatch):
    manager = _probed_flatpak(monkeypatch, {})
    spec = Specifier(raw_spec="org.example.Fig", package_id="org.example.Fig")
    assert _attempt_install(manager, spec) == "cooldown"


def test_package_task_holds_fresh_release(monkeypatch):
    fresh = datetime.now(tz=timezone.utc) - timedelta(days=1)
    manager = _probed_flatpak(monkeypatch, {"org.example.Kiwi": fresh})
    spec = Specifier(raw_spec="org.example.Kiwi", package_id="org.example.Kiwi")
    task = _package_task(
        manager,
        spec,
        threading.Lock(),
        action=lambda m, s: pytest.fail("a held package must not run its action"),
        verb="install",
        past="installed",
        prep="with",
        operation="install",
        record_failure=lambda s: pytest.fail(
            "a held package must not be recorded as a failure"
        ),
    )
    ok, label = task()
    assert ok is False
    assert "(cooldown)" in label


def test_cooldown_permits_without_cooldown():
    manager = Homebrew()
    manager.cooldown = None
    assert cooldown_permits(manager) is True


def test_cooldown_permits_supported_manager():
    manager = UV()
    manager.cooldown = timedelta(days=7)
    assert cooldown_permits(manager) is True


def test_cooldown_permits_blocks_ungateable(caplog):
    caplog.set_level(logging.WARNING)
    manager = Homebrew()
    manager.cooldown = timedelta(days=7)
    manager.cooldown_policy = CooldownPolicy.enforce
    assert cooldown_permits(manager) is False
    assert "cannot enforce" in caplog.text
    assert "--cooldown best-effort" in caplog.text


def test_cooldown_permits_allows_best_effort(caplog):
    caplog.set_level(logging.WARNING)
    manager = Homebrew()
    manager.cooldown = timedelta(days=7)
    manager.cooldown_policy = CooldownPolicy.best_effort
    assert cooldown_permits(manager) is True
    assert "without the supply-chain safeguard" in caplog.text


def test_cooldown_permits_allows_off(caplog):
    """`off` exempts a manager from the gate entirely, like best-effort."""
    caplog.set_level(logging.WARNING)
    manager = Homebrew()
    manager.cooldown = timedelta(days=7)
    manager.cooldown_policy = CooldownPolicy.off
    assert cooldown_permits(manager) is True


def test_off_policy_suppresses_env_injection():
    """An `off` policy holds back the cutoff even where a manager could honor it."""
    manager = UV()
    manager.cooldown = timedelta(days=7)
    manager.cooldown_policy = CooldownPolicy.off
    assert manager.cooldown_env() == {}


def test_cli_rejects_invalid_cooldown(invoke):
    result = invoke("--cooldown", "bogus", "managers")
    assert result.exit_code == 2
    assert "not a valid duration" in result.stderr


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        # Duration grammar flows through click-extra's Duration type.
        ("7 days", timedelta(days=7)),
        ("12h", timedelta(hours=12)),
        ("P7D", timedelta(days=7)),
        # Zero, off and future timestamps all read as "no gate".
        ("0", CooldownPolicy.off),
        ("off", CooldownPolicy.off),
        ("OFF", CooldownPolicy.off),
        ("2999-01-01T00:00:00Z", CooldownPolicy.off),
        # Posture keywords, case-insensitively.
        ("enforce", CooldownPolicy.enforce),
        ("best-effort", CooldownPolicy.best_effort),
        ("Best-Effort", CooldownPolicy.best_effort),
        # Empty stays "unspecified": resolution inherits both axes.
        ("", None),
    ),
)
def test_cooldown_option_parses_windows_and_keywords(raw, expected):
    """The `--cooldown` union spells a window or an enforcement posture."""
    assert Cooldown().convert(raw, None, None) == expected


@pytest.mark.parametrize(
    ("section", "expected"),
    (
        (None, CooldownSettings(duration=None, policy=None)),
        ({}, CooldownSettings(duration=None, policy=None)),
        (
            {"period": "1 week"},
            CooldownSettings(duration=timedelta(days=7), policy=None),
        ),
        (
            {"period": "1 week", "policy": "best-effort"},
            CooldownSettings(
                duration=timedelta(days=7), policy=CooldownPolicy.best_effort
            ),
        ),
        # A zero period reads as "no window".
        ({"period": "0"}, CooldownSettings(duration=None, policy=None)),
        # The deprecated top-level string spelling is the window.
        (
            "1 week",
            CooldownSettings(duration=timedelta(days=7), policy=None, legacy=True),
        ),
    ),
)
def test_parse_cooldown_section(section, expected):
    assert parse_cooldown_section(section) == expected


@pytest.mark.parametrize(
    ("section", "reason"),
    (
        # A posture without a window would be a standing no-op gate.
        ({"policy": "best-effort"}, "requires a period"),
        # off is a CLI-only keyword; configuration disables via the period.
        ({"period": "1 week", "policy": "off"}, "CLI-only"),
        ({"policy": "sideways"}, "unknown policy"),
        ({"period": "bogus"}, "not a valid duration"),
        ({"windows": "1 week"}, "unknown key"),
    ),
)
def test_parse_cooldown_section_rejects(section, reason):
    with pytest.raises(ValueError, match=reason):
        parse_cooldown_section(section)


def test_parse_cooldown_section_rejects_wrong_shape():
    """A section that is neither a table nor a string is a type error."""
    with pytest.raises(TypeError, match="expected a table"):
        parse_cooldown_section(["1 week"])


@pytest.mark.parametrize(
    ("flag", "settings", "expected"),
    (
        # Nothing anywhere: no gate, fail-closed posture by default.
        (None, CooldownSettings(None, None), (None, CooldownPolicy.enforce)),
        # The configuration alone decides both axes.
        (
            None,
            CooldownSettings(timedelta(days=7), CooldownPolicy.best_effort),
            (timedelta(days=7), CooldownPolicy.best_effort),
        ),
        # A flag window inherits the configured posture.
        (
            timedelta(days=1),
            CooldownSettings(timedelta(days=7), CooldownPolicy.best_effort),
            (timedelta(days=1), CooldownPolicy.best_effort),
        ),
        # A flag posture inherits the configured window.
        (
            CooldownPolicy.best_effort,
            CooldownSettings(timedelta(days=7), None),
            (timedelta(days=7), CooldownPolicy.best_effort),
        ),
        # A flag posture overrides the configured one.
        (
            CooldownPolicy.enforce,
            CooldownSettings(timedelta(days=7), CooldownPolicy.best_effort),
            (timedelta(days=7), CooldownPolicy.enforce),
        ),
        # off forces the window off too, whatever the configuration.
        (
            CooldownPolicy.off,
            CooldownSettings(timedelta(days=7), CooldownPolicy.best_effort),
            (None, CooldownPolicy.off),
        ),
    ),
)
def test_resolve_cooldown(flag, settings, expected):
    """The flag and the configuration merge axis by axis."""
    assert resolve_cooldown(flag, settings) == expected


def test_cli_cooldown_config_table(tmp_path, invoke):
    """A `[mpm.cooldown]` table reaches the gate through the configuration."""
    conf = tmp_path / "config.toml"
    conf.write_text('[mpm.cooldown]\nperiod = "1 week"\n', encoding="UTF-8")
    # A posture keyword inherits the configured window, so the run has an
    # active gate and the "no effect" note stays off.
    result = invoke(
        "--config",
        str(conf),
        "--verbosity",
        "INFO",
        "--cooldown",
        "best-effort",
        "managers",
    )
    assert result.exit_code == 0
    assert "has no effect" not in result.stderr


def test_cli_cooldown_keyword_without_window_is_a_noop(invoke):
    """A posture keyword with no window anywhere logs an INFO note."""
    result = invoke("--verbosity", "INFO", "--cooldown", "best-effort", "managers")
    assert result.exit_code == 0
    assert "--cooldown best-effort has no effect" in result.stderr


def test_cli_cooldown_legacy_config_spelling(tmp_path, invoke):
    """The deprecated top-level string still sets the window, with a warning."""
    conf = tmp_path / "config.toml"
    conf.write_text('[mpm]\ncooldown = "1 week"\n', encoding="UTF-8")
    result = invoke("--config", str(conf), "managers")
    assert result.exit_code == 0
    assert "Deprecated configuration" in result.stderr
    assert "[mpm.cooldown] period" in result.stderr


def test_cli_cooldown_config_policy_without_period(tmp_path, invoke):
    """A standing posture without a window is rejected at load time."""
    conf = tmp_path / "config.toml"
    conf.write_text('[mpm.cooldown]\npolicy = "best-effort"\n', encoding="UTF-8")
    result = invoke("--config", str(conf), "managers")
    assert result.exit_code == 1
    assert "requires a period" in result.stderr
