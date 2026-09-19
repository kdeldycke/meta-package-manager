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
"""Yarn Classic query tests.

These tests replay captured `yarn --silent --json` streams through
`YarnClassic.search` and `YarnClassic.outdated`. They do not invoke `yarn`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from meta_package_manager.execution import CLIError
from meta_package_manager.managers.yarn import YarnClassic

REQUEST = (
    r'{"type":"verbose","data":"Performing \"GET\" request to '
    r'\"https://registry.yarnpkg.com/ms\"."}'
)

INSPECT = (
    '{"type":"inspect","data":{"name":"ms",'
    '"description":"Tiny millisecond conversion utility","version":"2.1.3"}}'
)

INFO_FAIL = '{"type":"error","data":"Received invalid response from npm."}'

NODE_WARNING = (
    "(node:79799) Warning: The 'NO_COLOR' env is ignored due to the "
    "'FORCE_COLOR' env being set."
)

OUTDATED_TABLE = (
    '{"type":"table","data":{"head":["Package","Current","Wanted","Latest",'
    '"Package Type","URL"],"body":[["ms","2.0.0","2.0.0","2.1.3","dependencies",'
    '"https://github.com/vercel/ms#readme"]]}}'
)

LICENSE_WARNING = '{"type":"warning","data":"package.json: No license field"}'

REFUSED = '{"type":"error","data":"Error: connect ECONNREFUSED 127.0.0.1:59055"}'


def finished(status: int) -> str:
    """The `--verbose` record yarn prints when the registry answers."""
    return (
        r'{"type":"verbose","data":"Request \"https://registry.yarnpkg.com/ms\" '
        f'finished with status code {status}."}}'
    )


@pytest.fixture
def yarn(monkeypatch):
    manager = YarnClassic()
    monkeypatch.setattr(manager, "cli_errors", [])
    monkeypatch.setattr(manager, "cli_path", Path("/usr/bin/yarn"), raising=False)
    monkeypatch.setattr(
        manager, "global_dir", "/home/user/.config/yarn/global", raising=False
    )
    return manager


def replay(monkeypatch, manager, stdout: str, stderr: str) -> None:
    """Stand in for `run_cli`, recording the run the way `run()` does."""

    def fake_run_cli(*args, **kwargs):
        manager._last_run = (0, stdout, stderr)
        return stdout

    monkeypatch.setattr(manager, "run_cli", fake_run_cli)


def spawn(monkeypatch, manager, code: int, stdout: str, stderr: str) -> None:
    """Stand in for the child process, so the failure gate of `run()` runs."""
    monkeypatch.setattr(
        manager, "_spawn", lambda *args, **kwargs: (code, stdout, stderr)
    )


def test_outdated_reads_exit_1_as_updates(yarn, monkeypatch, caplog):
    """Yarn exits 1 when updates exist, its warnings on `<stderr>`."""
    caplog.set_level(logging.WARNING)
    spawn(monkeypatch, yarn, 1, OUTDATED_TABLE, f"{LICENSE_WARNING}\n{NODE_WARNING}")
    packages = [
        (p.id, str(p.installed_version), str(p.latest_version)) for p in yarn.outdated
    ]
    assert packages == [("ms", "2.0.0", "2.1.3")]
    assert yarn.cli_errors == []
    assert not caplog.records


def test_outdated_registry_failure(yarn, monkeypatch, caplog):
    """A failed registry request still fails, relaying only its `error` record."""
    caplog.set_level(logging.WARNING)
    spawn(monkeypatch, yarn, 1, "", f"{LICENSE_WARNING}\n{REFUSED}")
    with pytest.raises(CLIError) as excinfo:
        list(yarn.outdated)
    assert excinfo.value.error == REFUSED
    assert yarn.cli_errors == [excinfo.value]
    assert [record.getMessage() for record in caplog.records] == [REFUSED]


def test_search_found(yarn, monkeypatch):
    stdout = "\n".join((REQUEST, finished(200), INSPECT))
    replay(monkeypatch, yarn, stdout, NODE_WARNING)
    packages = list(yarn.search("ms", extended=False, exact=False))
    assert [(p.id, p.description, str(p.latest_version)) for p in packages] == [
        ("ms", "Tiny millisecond conversion utility", "2.1.3")
    ]
    assert yarn.cli_errors == []


@pytest.mark.parametrize("status", (400, 401, 404))
def test_search_missing_package(yarn, monkeypatch, caplog, status):
    """Yarn resolves these answers to "no such package": an empty result."""
    caplog.set_level(logging.WARNING)
    stdout = "\n".join((REQUEST, finished(status)))
    replay(monkeypatch, yarn, stdout, f"{NODE_WARNING}\n{INFO_FAIL}")
    assert list(yarn.search("ms", extended=False, exact=False)) == []
    assert yarn.cli_errors == []
    assert not caplog.records


@pytest.mark.parametrize(
    ("stdout", "diagnosis"),
    (
        (
            "\n".join((REQUEST, finished(429))),
            "Received invalid response from npm. The registry answered HTTP 429.",
        ),
        (
            REQUEST,
            "Received invalid response from npm. The registry did not answer.",
        ),
    ),
    ids=("http-429", "no-answer"),
)
def test_search_registry_failure(yarn, monkeypatch, caplog, stdout, diagnosis):
    """Any other answer, or none, is a failure yarn hid behind a zero exit."""
    caplog.set_level(logging.WARNING)
    replay(monkeypatch, yarn, stdout, f"{NODE_WARNING}\n{INFO_FAIL}")
    with pytest.raises(CLIError) as excinfo:
        list(yarn.search("ms", extended=False, exact=False))
    assert excinfo.value.error == diagnosis
    assert yarn.cli_errors == [excinfo.value]
    assert [record.getMessage() for record in caplog.records] == [diagnosis]
    assert caplog.records[0].levelno == logging.WARNING


def test_search_ignores_an_earlier_run(yarn, monkeypatch):
    """A failure recorded by an earlier call never leaks into this one."""
    yarn._last_run = (0, REQUEST, INFO_FAIL)
    monkeypatch.setattr(yarn, "run_cli", lambda *args, **kwargs: INSPECT)
    assert [p.id for p in yarn.search("ms", extended=False, exact=False)] == ["ms"]
    assert yarn.cli_errors == []
