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
"""PowerShell Gallery parsing tests.

These tests cover the pure-Python parsing/quoting logic. They do not invoke
`pwsh` and are platform-agnostic.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.pwsh_gallery import (
    PWSH_Gallery,
    _pwsh_quote,
)


@pytest.fixture
def manager():
    return PWSH_Gallery()


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("PSReadLine", "'PSReadLine'"),
        ("", "''"),
        ("with space", "'with space'"),
        ("Module.With.Dots", "'Module.With.Dots'"),
        # PowerShell single-quote escape: a literal single quote is doubled.
        ("O'Brien", "'O''Brien'"),
        ("''", "''''''"),
        # Backslashes are literal inside single quotes, no escape needed.
        ("C:\\path", "'C:\\path'"),
        # Dollar signs are not expanded inside single quotes.
        ("$var", "'$var'"),
    ),
)
def test_pwsh_quote(value, expected):
    assert _pwsh_quote(value) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        ("", []),
        ("   \n\n  ", []),
        # `ConvertTo-Json -AsArray` always emits a JSON array, even for one item.
        (
            '[{"Name":"PSReadLine","Version":"2.3.6"}]',
            [{"Name": "PSReadLine", "Version": "2.3.6"}],
        ),
        (
            '[{"Name":"PSReadLine","Version":"2.3.6"},'
            '{"Name":"Pester","Version":"5.5.0"}]',
            [
                {"Name": "PSReadLine", "Version": "2.3.6"},
                {"Name": "Pester", "Version": "5.5.0"},
            ],
        ),
    ),
)
def test_parse_json_array(manager, output, expected):
    assert manager._parse_json_array(output) == expected


def test_installed_yields_packages(manager, stub_run_cli):
    stub_run_cli(manager, '[{"Name":"PSReadLine","Version":"2.3.6"}]')
    packages = list(manager.installed)
    assert len(packages) == 1
    assert packages[0].id == "PSReadLine"
    assert str(packages[0].installed_version) == "2.3.6"


def test_installed_handles_empty_pipeline(manager, stub_run_cli):
    """A fresh shell with no resources installed produces empty stdout."""
    stub_run_cli(manager, "")
    assert list(manager.installed) == []


def test_outdated_yields_only_upgrades(manager, stub_run_cli):
    output = '[{"Name":"PSReadLine","Installed":"2.3.4","Latest":"2.3.6"}]'
    stub_run_cli(manager, output)
    packages = list(manager.outdated)
    assert len(packages) == 1
    assert packages[0].id == "PSReadLine"
    assert str(packages[0].installed_version) == "2.3.4"
    assert str(packages[0].latest_version) == "2.3.6"


def test_search_passes_wildcard_pattern(manager, capture_run_cli):
    """Fuzzy search wraps the query with `*` wildcards in the expression."""
    captured = capture_run_cli(manager, "[]")
    list(manager.search("readline", extended=False, exact=False))
    assert "'*readline*'" in captured[0][0]


def test_search_exact_drops_wildcards(manager, capture_run_cli):
    """Exact search passes the query verbatim, without surrounding wildcards."""
    captured = capture_run_cli(manager, "[]")
    list(manager.search("PSReadLine", extended=False, exact=True))
    assert "'PSReadLine'" in captured[0][0]
    assert "*PSReadLine*" not in captured[0][0]


def test_search_yields_description(manager, stub_run_cli):
    output = (
        '[{"Name":"PSReadLine","Version":"2.3.6",'
        '"Description":"Great command line editing in PowerShell."}]'
    )
    stub_run_cli(manager, output)
    packages = list(manager.search("readline", extended=False, exact=False))
    assert len(packages) == 1
    assert packages[0].description == "Great command line editing in PowerShell."
    assert str(packages[0].latest_version) == "2.3.6"


def test_install_builds_expected_expression(manager, capture_run_cli):
    captured = capture_run_cli(manager)
    manager.install("PSReadLine")
    expression = captured[0][0]
    assert "Install-PSResource" in expression
    assert "'PSReadLine'" in expression
    assert "-Scope CurrentUser" in expression
    assert "-TrustRepository" in expression
    assert "-AcceptLicense" in expression
    assert "-Version" not in expression


def test_install_with_version_appends_flag(manager, capture_run_cli):
    captured = capture_run_cli(manager)
    manager.install("PSReadLine", version="2.3.6")
    expression = captured[0][0]
    assert "-Version '2.3.6'" in expression


def test_upgrade_all_cli_does_not_constrain_scope(manager):
    cli = manager.upgrade_all_cli()
    # Pre-args order: pwsh path, then -NoProfile -NonInteractive -Command, then expression.
    assert "-Command" in cli
    expression = cli[-1]
    assert expression.startswith("Update-PSResource")
    assert "-Scope" not in expression


def test_upgrade_one_cli_targets_named_package(manager):
    cli = manager.upgrade_one_cli("PSReadLine")
    expression = cli[-1]
    assert "Update-PSResource" in expression
    assert "-Name 'PSReadLine'" in expression


def test_upgrade_one_cli_with_version_appends_flag(manager):
    cli = manager.upgrade_one_cli("PSReadLine", version="2.3.6")
    expression = cli[-1]
    assert "-Version '2.3.6'" in expression


def test_remove_quotes_package_id(manager, capture_run_cli):
    captured = capture_run_cli(manager)
    manager.remove("PSReadLine")
    expression = captured[0][0]
    assert "Uninstall-PSResource" in expression
    assert "-Name 'PSReadLine'" in expression


def test_install_escapes_embedded_single_quote(manager, capture_run_cli):
    """A package ID with a literal `'` is doubled inside the quoted string."""
    captured = capture_run_cli(manager)
    manager.install("O'Brien")
    expression = captured[0][0]
    assert "'O''Brien'" in expression
