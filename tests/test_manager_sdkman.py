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

"""SDKMAN! output tests.

These tests stub `run` and replay the samples documented on
{class}`~meta_package_manager.managers.sdkman.SDKMAN`. They never call `bash`
or `sdk`.
"""

from __future__ import annotations

from pathlib import Path

from meta_package_manager.managers.sdkman import SDKMAN

UPGRADE_OUTPUT = """\
Available defaults:
gradle (local: 2.3, 1.11; default: 8.9)
java (local: 21.0.4-tem; default: 25.0.2-tem)

Use prescribed default version(s)? (Y/n):"""
"""`echo n | sdk upgrade`, as the docstring of
{attr}`~meta_package_manager.managers.sdkman.SDKMAN.outdated` shows it."""


def test_outdated_reads_the_declined_upgrade(monkeypatch):
    """Each candidate gives its first local version and the default it can
    move to, read from an upgrade that the piped `n` declines.
    """
    manager = SDKMAN()
    monkeypatch.setattr(
        manager,
        "cli_path",
        Path("/home/user/.sdkman/bin/sdkman-init.sh"),
        raising=False,
    )
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return UPGRADE_OUTPUT

    monkeypatch.setattr(manager, "run", fake_run)
    packages = [
        (p.id, str(p.installed_version), str(p.latest_version))
        for p in manager.outdated
    ]
    assert packages == [
        ("gradle", "2.3", "8.9"),
        ("java", "21.0.4-tem", "25.0.2-tem"),
    ]
    [(args, kwargs)] = calls
    assert args[:2] == ("bash", "-c")
    assert args[2].endswith(" && echo n | sdk upgrade")
    # These two keep the listing free of color, and stop a user's own
    # `sdkman_auto_answer` from accepting the upgrade.
    assert kwargs["extra_env"] == {
        "sdkman_colour_enable": "false",
        "sdkman_auto_answer": "false",
    }
