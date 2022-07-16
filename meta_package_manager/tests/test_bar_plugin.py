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

import pytest
from click_extra.run import env_copy
from click_extra.tests.conftest import unless_macos

from .. import bar_plugin


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
            ("python", bar_plugin.__file__),
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
    @pytest.mark.parametrize(
        "shell_args",
        (
            ("/bin/bash",),
            ("/bin/zsh",),
            ("/usr/bin/env", "bash"),
            ("/usr/bin/env", "zsh"),
        ),
    )
    def test_shells(self, shell_args):
        """Test execution of plugin on different shells.

        See the list of shell supported by SwiftBar at:
        https://github.com/swiftbar/SwiftBar/commit/366695d594884fe141bc1752ab0f25d2c43334fa
        """
        process = subprocess.run((*shell_args, "-c", "-l", bar_plugin.__file__))
        assert process.returncode == 0
        assert not process.stderr

    @pytest.mark.parametrize(
        "shell_args",
        (
            (),
            ("/bin/bash", "-c"),
            ("/bin/zsh", "-c"),
            ("/usr/bin/env",),
            ("/usr/bin/env", "bash", "-c"),
            ("/usr/bin/env", "zsh", "-c"),
        ),
    )
    @pytest.mark.parametrize(
        "python_bin",
        (
            ("python",),
            ("python3",),
            ("/usr/bin/env", "python"),
            ("/usr/bin/env", "python3"),
        ),
    )
    def test_python_shells(self, shell_args, python_bin):
        """Test Python shells are properly configured in system and all are pointing to v3."""
        if "-c" in shell_args:
            args = *shell_args, f"{' '.join(python_bin)} --version"
        else:
            args = *python_bin, "--version"
        process = subprocess.run(args, capture_output=True, encoding="utf-8")
        assert process.returncode == 0
        assert process.stdout
        assert not process.stderr

        version = tuple(map(int, process.stdout.split()[1].split(".")))
        assert version >= bar_plugin.python_min_version
