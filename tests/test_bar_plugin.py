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

import re
import subprocess
from collections import Counter
from itertools import product
from typing import cast

import pytest
from boltons.iterutils import flatten
from click_extra.envvar import TEnvVars, env_copy
from click_extra.testing import args_cleanup
from extra_platforms.pytest import unless_macos  # type: ignore[attr-defined]

from meta_package_manager import bar_plugin
from meta_package_manager.version import parse_version


@pytest.mark.parametrize(
    ("param_string", "results"),
    (
        ("font=Menlo", "font=Menlo"),
        ("font=Menlo size=12", "font=Menlo size=12"),
        ("      font=Menlo      ", "font=Menlo"),
        ("      font   =   Menlo      ", "font=Menlo"),
        ("      font   =   Menlo  Menlo    ", "font=Menlo"),
        ("", ""),
        ("        ", ""),
        ("  font=      ", ""),
        ("  font      ", ""),
        ("   = foo ", ""),
        ("=", ""),
        ("==", ""),
        ("   =  =    ", ""),
        ("random=", ""),
        ("RANDOM=", ""),
        ("Font=", ""),
        ("font=Menlo font=Menlo", "font=Menlo"),
        ("size=10 size=20", "size=20"),
        ("font='Comic Sans MS'", "font='Comic Sans MS'"),
        ('font="Comic Sans MS"', 'font="Comic Sans MS"'),
    ),
)
def test_normalize_params(param_string, results):
    assert bar_plugin.MPMPlugin.normalize_params(param_string) == results


def _invocation_matrix(*iterables):
    """Pre-compute a matrix of all possible options for invocation."""
    for args in product(*iterables):
        yield args_cleanup(args)


def _shell_invocation_matrix():
    """Pre-compute a matrix of all possible options used for shell invocation.

    See the list of shell supported by SwiftBar at:
    https://github.com/swiftbar/SwiftBar/commit/366695d594884fe141bc1752ab0f25d2c43334fa

    Returns
    -------
    .. code-block:: python
        (
            ("bash", "-c"),
            ("bash", "--login", "-c"),
            ("/bin/bash", "-c"),
            ("/bin/bash", "--login", "-c"),
            ("zsh", "-c"),
            ("zsh", "--login", "-c"),
            ("/bin/zsh", "-c"),
            ("/bin/zsh", "--login", "-c"),
            ("/usr/bin/env", "bash", "-c"),
            ("/usr/bin/env", "bash", "--login", "-c"),
            ("/usr/bin/env", "/bin/bash", "-c"),
            ("/usr/bin/env", "/bin/bash", "--login", "-c"),
            ("/usr/bin/env", "zsh", "-c"),
            ("/usr/bin/env", "zsh", "--login", "-c"),
            ("/usr/bin/env", "/bin/zsh", "-c"),
            ("/usr/bin/env", "/bin/zsh", "--login", "-c"),
            None,
        )
    """
    return list(
        _invocation_matrix(
            # Env prefixes.
            (None, "/usr/bin/env"),
            # Naked and full binary paths.
            flatten((bin_id, f"/bin/{bin_id}") for bin_id in ("bash", "zsh")),
            # Options.
            ("-c", ("--login", "-c")),
        )
    ) + [None]


def _python_invocation_matrix():
    """Pre-compute a matrix of all possible options used for python invocation.

    Returns
    -------
    .. code-block:: python
        (
            ("python",),
            ("python3",),
            ("/usr/bin/env", "python"),
            ("/usr/bin/env", "python3"),
        )
    """
    return _invocation_matrix(
        # Env prefixes.
        (None, "/usr/bin/env"),
        # Binary paths
        ("python", "python3"),
    )


shell_args = pytest.mark.parametrize(
    "shell_args",
    tuple(
        pytest.param(p, id=" ".join(args_cleanup(p)))
        for p in _shell_invocation_matrix()
    ),
)


shell_python_args = pytest.mark.parametrize(
    "shell_args,python_args",
    (
        pytest.param(s_args, p_args, id=" ".join(args_cleanup(s_args, p_args)))
        for s_args, p_args in product(
            _shell_invocation_matrix(), _python_invocation_matrix()
        )
    ),
)


def _subcmd_args(
    invoke_args: tuple[str, ...] | None, *subcmd_args: str
) -> tuple[str, ...]:
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
        # Upgrade all line.
        # XXX Upgrade all line is not required, as it may be skipped in the
        # final rendering of the plugin if no outdated packages are found:
        #     📦✓ ⚠️1 | dropdown=false
        #     ---
        #     brew - 0 package | font=Menlo size=12
        #     ---
        #     cask - 0 package | font=Menlo size=12
        #     ...
        (
            r"(--)?🆙 Upgrade all \S+ packages? \| shell=\S+( param\d+=\S+)+ "
            r"refresh=true terminal=(false|true alternate=true)$",
            False,
        ),
        # Error line. Optional.
        (
            r"(--)?.+ \| font=Menlo size=10 color=red trim=false "
            r"ansi=false emojize=false( symbolize=false)?$",
            False,
        ),
    ]

    def _plugin_output_checks(self, checklist, extra_env: TEnvVars | None = None):
        """Run the plugin script and check its output against the checklist."""
        process = subprocess.run(
            bar_plugin.__file__,
            capture_output=True,
            encoding="utf-8",
            env=cast("subprocess._ENV", env_copy(extra_env)),
        )

        assert not process.stderr
        assert process.returncode == 0

        checks = checklist + self.common_checklist

        match_counter = Counter()  # type: ignore[var-annotated]

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
                msg = f"plugin output line {line!r} did not match any regex."
                raise Exception(msg)

        # Check all required regex did match at least once.
        for index, (regex, required) in enumerate(checks):
            if required and not match_counter[index]:
                print(process.stdout)
                msg = f"{regex!r} regex did not match any plugin output line."
                raise Exception(msg)

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @pytest.mark.parametrize("submenu_layout", (True, False, None))
    @pytest.mark.parametrize("table_rendering", (True, False, None))
    def test_rendering(self, submenu_layout, table_rendering):
        extra_checks = []
        # XXX Package upgrade line is not required, as it may be skipped in the
        # final rendering of the plugin if no outdated packages are found:
        #     📦✓ ⚠️1 | dropdown=false
        #     ---
        #     brew - 0 package | font=Menlo size=12
        #     ---
        #     cask - 0 package | font=Menlo size=12
        #     ...
        if table_rendering is False:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\d+ outdated .+ packages?", True),
                    # Package upgrade line.
                    (
                        r"(--)?[\S ]+ \S+ → \S+ \| shell=\S+( param\d+=\S+)+ "
                        r"refresh=true terminal=(false|true alternate=true)$",
                        False,
                    ),
                ),
            )
        # Default case is VAR_TABLE_RENDERING=true.
        else:
            extra_checks.extend(
                (
                    # Package manager section header.
                    (r"(⚠️ )?\S+ - \d+ packages?\s+\| font=Menlo size=12", True),
                    # Package upgrade line.
                    (
                        r"(--)?[\S ]+\s+\S+ → \S+\s+\| shell=\S+( param\d+=\S+)+ "
                        r"font=Menlo size=12 refresh=true "
                        r"terminal=(false|true alternate=true)?$",
                        False,
                    ),
                ),
            )

        extra_env = {}
        if submenu_layout is not None:
            extra_env["VAR_SUBMENU_LAYOUT"] = str(submenu_layout)
        if table_rendering is not None:
            extra_env["VAR_TABLE_RENDERING"] = str(table_rendering)

        self._plugin_output_checks(extra_checks, extra_env=extra_env)

    @pytest.mark.xdist_group(name="avoid_concurrent_plugin_runs")
    @shell_args
    def test_plugin_shell_invocation(self, shell_args):
        """Test execution of plugin on different shells.

        Do not execute the complete search for outdated packages, just stop at searching
        for the mpm executable and extract its version.
        """
        process = subprocess.run(
            _subcmd_args(shell_args, bar_plugin.__file__, "--search-mpm"),
            capture_output=True,
            encoding="utf-8",
        )

        assert not process.stderr
        assert process.returncode == 0
        assert process.stdout
        for line in process.stdout.splitlines():
            assert re.match(
                r"^.+ \| runnable: \S+ \| up to date: \S+"
                r" \| version: .+ \| error: .*$",
                line,
            )

    @shell_python_args
    def test_python_shell_invocation(self, shell_args, python_args):
        """Test any Python shell invocation is properly configured and all are
        compatible with plugin requirements."""
        process = subprocess.run(
            _subcmd_args(shell_args, *python_args, "--version"),
            capture_output=True,
            encoding="utf-8",
        )

        assert not process.stderr
        assert process.stdout
        assert process.returncode == 0

        # We need to parse the version to account for alpha release,
        # like Python `3.12.0a4`.
        python_version = process.stdout.split()[1]
        assert parse_version(python_version) >= parse_version(
            ".".join(str(i) for i in bar_plugin.PYTHON_MIN_VERSION),
        ), f"{python_version} >= {bar_plugin.PYTHON_MIN_VERSION}"
