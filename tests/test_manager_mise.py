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
"""mise output-parsing and CLI-construction tests.

These tests stub ``run_cli`` and exercise the pure-Python branches of the
``Mise`` manager. They do not invoke the real ``mise`` binary.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.mise import Mise


@pytest.fixture
def manager():
    return Mise()


def test_installed_yields_packages(manager, stub_run_cli):
    output = (
        '{"node": [{"version": "20.10.0", '
        '"install_path": "/home/me/.local/share/mise/installs/node/20.10.0"}]}'
    )
    stub_run_cli(manager, output)
    packages = list(manager.installed)
    assert len(packages) == 1
    assert packages[0].id == "node"
    assert str(packages[0].installed_version) == "20.10.0"


@pytest.mark.parametrize("output", ("", "{}"))
def test_installed_handles_empty(manager, stub_run_cli, output):
    stub_run_cli(manager, output)
    assert list(manager.installed) == []


def test_installed_yields_one_package_per_version(manager, stub_run_cli):
    output = (
        '{"node": ['
        '{"version": "18.20.0", "install_path": "/x/node/18.20.0"},'
        '{"version": "20.10.0", "install_path": "/x/node/20.10.0"}'
        "]}"
    )
    stub_run_cli(manager, output)
    packages = list(manager.installed)
    assert len(packages) == 2
    assert {p.id for p in packages} == {"node"}
    assert {str(p.installed_version) for p in packages} == {"18.20.0", "20.10.0"}


def test_installed_preserves_backend_prefix(manager, stub_run_cli):
    """Backend-prefixed IDs like ``pipx:ruff`` round-trip without rewriting."""
    output = (
        '{"pipx:ruff": [{"version": "0.6.9", "install_path": "/x/pipx-ruff/0.6.9"}]}'
    )
    stub_run_cli(manager, output)
    packages = list(manager.installed)
    assert len(packages) == 1
    assert packages[0].id == "pipx:ruff"


def test_outdated_yields_upgrades(manager, stub_run_cli):
    output = '{"node": {"requested": "20", "current": "20.0.0", "latest": "20.10.0"}}'
    stub_run_cli(manager, output)
    packages = list(manager.outdated)
    assert len(packages) == 1
    assert packages[0].id == "node"
    assert str(packages[0].installed_version) == "20.0.0"
    assert str(packages[0].latest_version) == "20.10.0"


@pytest.mark.parametrize("output", ("", "{}"))
def test_outdated_handles_empty(manager, stub_run_cli, output):
    stub_run_cli(manager, output)
    assert list(manager.outdated) == []


def test_search_parses_table(manager, stub_run_cli):
    output = (
        "node                Node.js JavaScript runtime\n"
        "node-build          Compile and install Node.js\n"
        "nodejs              alias for node\n"
    )
    stub_run_cli(manager, output)
    packages = list(manager.search("node", extended=False, exact=False))
    assert [p.id for p in packages] == ["node", "node-build", "nodejs"]
    assert packages[0].description == "Node.js JavaScript runtime"
    assert packages[1].description == "Compile and install Node.js"


def test_search_keeps_descriptions_with_inner_spaces(manager, stub_run_cli):
    """A description containing single-space-separated words is preserved
    intact: the regex only treats the run of 2+ spaces between columns as a
    delimiter."""
    output = "ripgrep            line-oriented search tool\n"
    stub_run_cli(manager, output)
    packages = list(manager.search("rg", extended=False, exact=False))
    assert len(packages) == 1
    assert packages[0].description == "line-oriented search tool"


@pytest.mark.parametrize(
    ("version", "expected_spec"),
    (
        (None, "node"),
        ("20", "node@20"),
        ("20.10.0", "node@20.10.0"),
    ),
)
def test_install_builds_spec(manager, capture_run_cli, version, expected_spec):
    captured = capture_run_cli(manager)
    manager.install("node", version=version)
    assert captured == [("install", expected_spec)]


def test_upgrade_all_cli_omits_target(manager):
    cli = manager.upgrade_all_cli()
    assert "upgrade" in cli
    # No tool argument tacked on the end.
    assert cli[-1] == "upgrade"


@pytest.mark.parametrize(
    ("version", "expected_spec"),
    (
        (None, "node"),
        ("20", "node@20"),
    ),
)
def test_upgrade_one_cli_builds_spec(manager, version, expected_spec):
    cli = manager.upgrade_one_cli("node", version=version)
    assert "upgrade" in cli
    assert cli[-1] == expected_spec


def test_remove_uses_all_flag(manager, capture_run_cli):
    """``--all`` matches mpm's "remove the package, full stop" contract even
    when ``mise`` has multiple versions of the same tool installed."""
    captured = capture_run_cli(manager)
    manager.remove("node")
    assert captured == [("uninstall", "--all", "node")]


def test_sync_runs_plugins_update(manager, capture_run_cli):
    captured = capture_run_cli(manager)
    manager.sync()
    assert captured == [("plugins", "update")]


def test_cleanup_runs_cache_clear(manager, capture_run_cli):
    captured = capture_run_cli(manager)
    manager.cleanup()
    assert captured == [("cache", "clear")]
