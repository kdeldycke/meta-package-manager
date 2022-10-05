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

from __future__ import annotations

import re
import subprocess
from collections import Counter
from itertools import product

import pytest
from boltons.iterutils import flatten
from click_extra.run import args_cleanup, env_copy
from click_extra.tests.conftest import unless_macos

from .. import bar_plugin


def _invokation_matrix(*iterables):
    """Pre-compute a matrix of all possible options for invokation."""
    for args in product(*iterables):
        yield args_cleanup(args)


def _shell_invokation_matrix():
    """Pre-compute a matrix of all possible options used for shell invokation.

    See the list of shell supported by SwiftBar at:
    https://github.com/swiftbar/SwiftBar/commit/366695d594884fe141bc1752ab0f25d2c43334fa

    Returns:

    .. code-block:: python
        (
            ('bash', '-c'),
            ('bash', '--login', '-c'),
            ('/bin/bash', '-c'),
            ('/bin/bash', '--login', '-c'),
            ('zsh', '-c'),
            ('zsh', '--login', '-c'),
            ('/bin/zsh', '-c'),
            ('/bin/zsh', '--login', '-c'),
            ('/usr/bin/env', 'bash', '-c'),
            ('/usr/bin/env', 'bash', '--login', '-c'),
            ('/usr/bin/env', '/bin/bash', '-c'),
            ('/usr/bin/env', '/bin/bash', '--login', '-c'),
            ('/usr/bin/env', 'zsh', '-c'),
            ('/usr/bin/env', 'zsh', '--login', '-c'),
            ('/usr/bin/env', '/bin/zsh', '-c'),
            ('/usr/bin/env', '/bin/zsh', '--login', '-c'),
        )
    """
    return _invokation_matrix(
        # Env prefixes.
        (None, "/usr/bin/env"),
        # Naked and full binary paths.
        flatten((bin_id, f"/bin/{bin_id}") for bin_id in ("bash", "zsh")),
        # Options.
        (
            "-c",
            # XXX Login shell defaults to Python 2.7 on GitHub macOS runners and is picked up by surprise for bar plugin tests:
            # Traceback (most recent call last):
            #   File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/runpy.py",
            #   line 163, in _run_module_as_main
            #     mod_name, _Error)
            #   File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/runpy.py",
            #   line 111, in _get_module_details
            #     __import__(mod_name)  # Do not catch exceptions initializing package
            #   File "meta_package_manager/__init__.py", line 33, in <module>
            #     from click_extra.logging import logger
            # ImportError: No module named click_extra.logging
            # ("--login", "-c"),
        ),
    )


def _python_invokation_matrix():
    """Pre-compute a matrix of all possible options used for python invokation.

    Returns:

    .. code-block:: python
        (
            ('python',),
            ('python3',),
            ('/usr/bin/env', 'python'),
            ('/usr/bin/env', 'python3'),
        )
    """
    return _invokation_matrix(
        # Env prefixes.
        (None, "/usr/bin/env"),
        # Binary paths
        ("python", "python3"),
    )


def _subcmd_args(invoke_args: tuple[str, ...] | None, *subcmd_args: str):
    """Cleanup args and eventually concatenate all ``subcmd_args`` items to a space
    separated string if ``invoke_args`` is defined and its last argument is equal to
    ``-c``."""
    raw_args: list[str] = []
    if invoke_args:
        raw_args.extend(invoke_args)
        if invoke_args[-1] == "-c":
            subcmd_args = (" ".join(subcmd_args),)
    raw_args.extend(subcmd_args)
    return args_cleanup(raw_args)


@unless_macos
class TestBarPlugin:

    common_checklist = [
        # Menubar line. Required.
        (r"(🎁↑\d+|📦✓)( ⚠️\d+)? \| dropdown=false$", True),
        # Submenus and sections marker. Required.
        (r"-{3,5}$", True),
        # Upgrade all line. Required.
        (
            r"(--)?🆙 Upgrade all \S+ packages? \| shell=\S+( param\d+=\S+)+ "
            r"refresh=true terminal=(false|true alternate=true)$",
            True,
        ),
        # Error line. Optional.
        (
            r"(--)?.+ \| font=Menlo size=12 color=red trim=false "
            r"ansi=false emojize=false( symbolize=false)?$",
            False,
        ),
    ]

    def plugin_output_checks(self, checklist, extra_env=None):
        """Run the plugin script and check its output against the checklist."""

        process = subprocess.run(
            # Force the plugin to be called within Poetry venv to not have it seeking
            # for macOS's default Python.
            ("poetry", "run", "python", bar_plugin.__file__),
            capture_output=True,
            encoding="utf-8",
            env=env_copy(extra_env),
        )

        assert process.returncode == 0
        assert not process.stderr

        checks = checklist + self.common_checklist

        match_counter = Counter()

        for line in process.stdout.splitlines():
            # The line is expected to match at least one regex.
            matches = False
            for index, (regex, _) in enumerate(checks):
                if re.match(regex, line):
                    matches = True
                    match_counter[index] += 1
                    break
            if not matches:
                print(process.stdout)
                raise Exception(f"plugin output line {line!r} did not match any regex.")

        # Check all required regex did match at least once.
        for index, (regex, required) in enumerate(checks):
            if required and not match_counter[index]:
                raise Exception(
                    f"{regex!r} regex did not match any plugin output line."
                )

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @pytest.mark.parametrize("submenu_layout", (True, False, None))
    @pytest.mark.parametrize("table_rendering", (True, False, None))
    def test_rendering(self, submenu_layout, table_rendering):
        extra_checks = []
        if table_rendering is False:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\d+ outdated .+ packages?", True),
                    # Package upgrade line.
                    (
                        r"(--)?\S+ \S+ → \S+ \| shell=\S+( param\d+=\S+)+ "
                        r"refresh=true terminal=(false|true alternate=true)$",
                        True,
                    ),
                )
            )
        # Default case is VAR_TABLE_RENDERING=true.
        else:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\S+ - \d+ packages?\s+\| font=Menlo size=12", True),
                    # Package upgrade line.
                    (
                        r"(--)?\S+\s+\S+ → \S+\s+\| shell=\S+( param\d+=\S+)+ "
                        r"font=Menlo size=12 refresh=true terminal=(false|true alternate=true)?$",
                        True,
                    ),
                )
            )

        extra_env = {}
        if submenu_layout is not None:
            extra_env["VAR_SUBMENU_LAYOUT"] = str(submenu_layout)
        if table_rendering is not None:
            extra_env["VAR_TABLE_RENDERING"] = str(table_rendering)

        self.plugin_output_checks(extra_checks, extra_env=extra_env)

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @pytest.mark.parametrize("shell_args", (None, *_shell_invokation_matrix()))
    def test_plugin_shell_invokation(self, shell_args):
        """Test execution of plugin on different shells.

        Do not execute the complete search for outdated packages, just stop at searching
        for the mpm executable and extract its version.
        """
        process = subprocess.run(
            _subcmd_args(shell_args, bar_plugin.__file__, "--check-mpm"),
            capture_output=True,
            encoding="utf-8",
        )

        assert process.returncode == 0
        assert not process.stderr
        assert re.match(r"^.+ v\d+\.\d+\.\d+$", process.stdout)

    @pytest.mark.parametrize("shell_args", (None, *_shell_invokation_matrix()))
    @pytest.mark.parametrize("python_args", _python_invokation_matrix())
    def test_python_shell_invokation(self, shell_args, python_args):
        """Test any Python shell invokation is properly configured and all are
        compatible with plugin requirements."""
        process = subprocess.run(
            _subcmd_args(shell_args, *python_args, "--version"),
            capture_output=True,
            encoding="utf-8",
        )

        assert process.returncode == 0
        assert process.stdout
        assert not process.stderr

        version = tuple(map(int, process.stdout.split()[1].split(".")))
        assert version >= bar_plugin.python_min_version
