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

import inspect
import runpy
import sys
from functools import partial

import pytest

from meta_package_manager.__main__ import main

MAIN_SCRIPT = inspect.getfile(main)
"""The `__main__.py` file that `python -m meta_package_manager` runs."""


@pytest.mark.parametrize(
    "entry_point",
    (
        pytest.param(main, id="function"),
        pytest.param(
            partial(runpy.run_path, MAIN_SCRIPT, run_name="__main__"), id="script"
        ),
    ),
)
def test_entry_point_runs_the_cli(monkeypatch, capsys, tmp_path, entry_point):
    """Both entry points run the CLI as `mpm`.

    The `main()` function the `mpm` script calls, and the `__main__.py` file `python -m
    meta_package_manager` runs, with the path of that file in `sys.argv[0]`.

    The version itself is not checked: click-extra resolves it once per process,
    from the stack of whichever test reads it first. The configuration inputs of
    the eager pre-load are pinned to an empty folder, so the test never reads
    the configuration of the machine it runs on.
    """
    monkeypatch.setattr(sys, "argv", [MAIN_SCRIPT, "--version"])
    monkeypatch.delenv("MPM_CONFIG", raising=False)
    monkeypatch.setattr(
        "meta_package_manager.config.get_app_dir", lambda app_name: str(tmp_path)
    )
    with pytest.raises(SystemExit) as exited:
        entry_point()
    assert exited.value.code == 0
    assert capsys.readouterr().out.startswith("mpm, version ")
