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
"""`gem`-specific behaviors: the user directory rule.

Where RubyGems installs to the user directory by default, `gem update` installs
a newer copy of each outdated gem of the system there. `outdated` and
`upgrade --all` then keep the gems with a version in the user directory.

Each test builds a new manager, whose commands answer from a table: the stubbed
probes cannot leak into the shared pool instance.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from meta_package_manager.managers.gem import Gem
from meta_package_manager.version import parse_version

PATCH_ACCESS = "meta_package_manager.managers.gem.os.access"
PATCH_ROOT = "meta_package_manager.manager._running_as_root"

GEM_PATH = Path("/usr/bin/gem")
USER_DIR = Path("/home/user/.local/share/gem/ruby/3.4.0")

ARCH_CONFIG = '"gem" => "--user-install"'
"""The configuration line that the `operating_system.rb` of Arch Linux adds."""

USER_DIR_LIST = "benchmark (default: 0.4.0)\njson (default: 2.9.1)\nrainbow (3.0.0)\n"
"""A `gem list` restricted to the user directory, which holds `rainbow` alone."""

OUTDATED = "json (2.9.1 < 3.2.0)\nrainbow (3.0.0 < 3.1.1)\n"
"""A `gem outdated` listing with a default gem and a gem of the user directory."""


def environment(
    *config_lines: str, gem_dir="/usr/lib/ruby/gems/3.4.0", user_dir=USER_DIR
):
    """A trimmed `gem environment` output, with `config_lines` in its configuration.

    A `None` `user_dir` drops the line of the user directory.
    """
    lines = [
        "RubyGems Environment:",
        "  - RUBYGEMS VERSION: 3.6.9",
        f"  - INSTALLATION DIRECTORY: {gem_dir}",
    ]
    if user_dir is not None:
        lines.append(f"  - USER INSTALLATION DIRECTORY: {user_dir}")
    lines.extend((
        "  - GEM CONFIGURATION:",
        "     - :update_sources => true",
        "     - :verbose => true",
        "     - :backtrace => true",
        "     - :bulk_threshold => 1000",
        *(f"     - {line}" for line in config_lines),
        "  - REMOTE SOURCES:",
        "     - https://rubygems.org/",
    ))
    return "\n".join(lines) + "\n"


@pytest.fixture
def new_gem(monkeypatch):
    """Build a new `gem` manager whose commands answer from a table.

    The table maps a verb (`environment`, `list`, `outdated`) to its output. The
    builder returns the manager and the list of the `(args, kwargs)` of each
    `run_cli` call.
    """
    monkeypatch.delenv("GEM_HOME", raising=False)

    def build(answers, version="3.6.9"):
        manager = Gem()
        # A new instance takes stand-in values for its cached probes, so the
        # tests never run the `gem` of the host.
        vars(manager)["cli_path"] = GEM_PATH
        vars(manager)["version"] = parse_version(version)
        calls = []

        def run_cli(*args, **kwargs):
            calls.append((args, kwargs))
            return answers.get(args[0], "")

        monkeypatch.setattr(manager, "run_cli", run_cli)
        return manager, calls

    return build


def _verbs(calls):
    """The verb of each recorded `run_cli` call."""
    return [args[0] for args, _ in calls]


def test_outdated_keeps_the_gems_of_the_user_directory(new_gem):
    """A default gem of the system leaves the listing, a gem of the user dir stays."""
    manager, calls = new_gem({
        "environment": environment(ARCH_CONFIG),
        "list": USER_DIR_LIST,
        "outdated": OUTDATED,
    })
    packages = list(manager.refiltered_outdated)

    assert [
        (p.id, str(p.installed_version), str(p.latest_version)) for p in packages
    ] == [("rainbow", "3.0.0", "3.1.1")]
    assert _verbs(calls) == ["environment", "list", "outdated"]
    _, list_kwargs = calls[1]
    assert list_kwargs["override_extra_env"] == {
        "GEM_HOME": str(USER_DIR),
        "GEM_PATH": str(USER_DIR),
    }
    assert list_kwargs["force_exec"] is True


def test_outdated_runs_no_listing_without_a_gem_in_the_user_directory(new_gem):
    """With default gems alone in the restricted listing, `gem outdated` never runs."""
    manager, calls = new_gem({
        "environment": environment(ARCH_CONFIG),
        "list": "benchmark (default: 0.4.0)\njson (default: 2.9.1)\n",
        "outdated": OUTDATED,
    })
    assert list(manager.refiltered_outdated) == []
    assert _verbs(calls) == ["environment", "list"]


def test_outdated_lists_every_gem_without_the_user_install_default(new_gem):
    """A host installing to the default directory keeps the whole listing."""
    manager, calls = new_gem({"environment": environment(), "outdated": OUTDATED})
    with patch(PATCH_ACCESS, return_value=True):
        assert [p.id for p in manager.refiltered_outdated] == ["json", "rainbow"]
    assert _verbs(calls) == ["environment", "outdated"]


@pytest.mark.parametrize(
    ("config_lines", "user_install"),
    (
        pytest.param((ARCH_CONFIG,), True, id="arch-gem-key"),
        pytest.param((':gem => "--user-install"',), True, id="symbol-gem-key"),
        pytest.param(
            ('"update" => "--user-install --no-document"',), True, id="update-key"
        ),
        pytest.param(
            ('"gem" => ["--no-document", "--user-install"]',), True, id="array-value"
        ),
        pytest.param(
            (ARCH_CONFIG, '"update" => "--no-user-install"'),
            False,
            id="update-key-wins",
        ),
        pytest.param(
            ('"update" => "--no-user-install"', ARCH_CONFIG),
            False,
            id="update-key-wins-in-any-print-order",
        ),
        pytest.param(
            ('"update" => "--user-install"', '"gem" => "--no-user-install"'),
            True,
            id="update-key-wins-over-gem-key",
        ),
        pytest.param(
            (':gem => "--no-user-install"', ARCH_CONFIG),
            False,
            id="symbol-gem-key-wins",
        ),
        pytest.param(('"install" => "--user-install"',), False, id="install-key"),
        pytest.param((), False, id="no-flag"),
    ),
)
def test_configured_flags_decide(new_gem, config_lines, user_install):
    """The last flag wins, the `update` key after the `gem` key."""
    manager, _ = new_gem({"environment": environment(*config_lines)})
    # A writable default directory keeps the fallback out of these cases.
    with patch(PATCH_ACCESS, return_value=True):
        assert (manager.user_install_dir == USER_DIR) is user_install


@pytest.mark.parametrize(
    ("version", "writable", "gem_home", "user_install"),
    (
        pytest.param("3.6.9", False, None, True, id="not-writable"),
        pytest.param("3.5.0", False, None, True, id="first-fallback-release"),
        pytest.param("3.4.5", False, None, False, id="no-fallback-before-3.5.0"),
        pytest.param("3.6.9", True, None, False, id="writable"),
        pytest.param("3.6.9", False, "environ", False, id="gem-home-in-environ"),
        pytest.param("3.6.9", False, "extra_env", False, id="gem-home-in-extra-env"),
    ),
)
def test_read_only_default_directory_falls_back_to_the_user_directory(
    new_gem, monkeypatch, tmp_path, version, writable, gem_home, user_install
):
    """Without a flag, RubyGems takes the user directory for a read-only default."""
    manager, _ = new_gem(
        {"environment": environment(gem_dir=tmp_path)}, version=version
    )
    if gem_home == "environ":
        monkeypatch.setenv("GEM_HOME", str(tmp_path))
    elif gem_home == "extra_env":
        monkeypatch.setattr(manager, "extra_env", {"GEM_HOME": str(tmp_path)})
    with patch(PATCH_ACCESS, return_value=writable):
        assert (manager.user_install_dir == USER_DIR) is user_install


def test_missing_default_directory_takes_no_fallback(new_gem, tmp_path):
    """RubyGems falls back only from a default directory that exists."""
    manager, _ = new_gem({"environment": environment(gem_dir=tmp_path / "missing")})
    with patch(PATCH_ACCESS, return_value=False):
        assert manager.user_install_dir is None


@pytest.mark.parametrize(
    "output",
    (
        pytest.param(environment(ARCH_CONFIG, user_dir=None), id="no-user-dir-line"),
        pytest.param("", id="empty-output"),
    ),
)
def test_unreadable_environment_keeps_the_rule_off(new_gem, output):
    """An output with no user directory leaves `gem` as it is."""
    manager, _ = new_gem({"environment": output})
    assert manager.user_install_dir is None


def test_upgrade_all_upgrades_the_kept_gems_one_by_one(new_gem, monkeypatch):
    """A full upgrade runs `gem update` on each gem of the user directory alone."""
    manager, _ = new_gem({
        "environment": environment(ARCH_CONFIG),
        "list": USER_DIR_LIST,
        "outdated": OUTDATED,
    })
    commands = []

    def run(*args, **kwargs):
        commands.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", run)
    manager.upgrade()
    assert commands == [(str(GEM_PATH), "update", "--quiet", "rainbow")]


def test_upgrade_all_runs_gem_update_on_the_default_directory(new_gem, monkeypatch):
    """The bare `gem update` stays for a host installing to the default directory."""
    manager, _ = new_gem({"environment": environment(), "outdated": OUTDATED})
    commands = []

    def run(*args, **kwargs):
        commands.append(args[0])
        return ""

    monkeypatch.setattr(manager, "run", run)
    with patch(PATCH_ACCESS, return_value=True):
        manager.upgrade()
    assert commands == [(str(GEM_PATH), "update", "--quiet")]


def test_sudo_turns_the_rule_off(new_gem, monkeypatch):
    """Under `mpm --sudo`, root runs `gem update`: no probe runs as the user."""
    manager, calls = new_gem({"environment": environment(ARCH_CONFIG)})
    monkeypatch.setattr(manager, "sudo", True)
    with patch(PATCH_ROOT, return_value=False):
        assert manager.user_install_dir is None
    assert calls == []


def test_root_keeps_the_rule(new_gem, monkeypatch):
    """Run as root, `mpm --sudo` escalates nothing: the probe reads root's defaults."""
    manager, _ = new_gem({"environment": environment(ARCH_CONFIG)})
    monkeypatch.setattr(manager, "sudo", True)
    with patch(PATCH_ROOT, return_value=True):
        assert manager.user_install_dir == USER_DIR
