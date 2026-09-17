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

import logging
import os
import stat
import time

import pytest
from extra_platforms import is_any_windows

from meta_package_manager import shell_env
from meta_package_manager.shell_env import (
    SHELL_ENV_GUARD,
    ShellEnvError,
    import_shell_env,
    read_shell_env,
    shell_argv,
)

pytestmark = pytest.mark.skipif(
    is_any_windows(),
    reason="The import is a no-op on Windows, and the stand-in shells are POSIX "
    "scripts.",
)


def fake_shell(tmp_path, body: str = "") -> str:
    """A stand-in login shell: runs `body`, drops `-i -l` and hands `-c` to
    `/bin/sh`.

    A real login shell would read the developer's own profile and change `PATH`
    in ways no assertion can predict. `body` is where a test exports what its
    shell answers with.
    """
    script = tmp_path / "fakesh"
    script.write_text(
        f'#!/bin/sh\n{body}\nshift 2\nexec /bin/sh "$@"\n', encoding="UTF-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def bare_environ(tmp_path, shell: str | None) -> dict[str, str]:
    """The environment a desktop session hands a process: a bare `PATH`."""
    environ = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if shell:
        environ["SHELL"] = shell
    return environ


@pytest.mark.parametrize(
    ("shell", "flags"),
    [
        pytest.param("/bin/zsh", ("-i", "-l", "-c"), id="zsh"),
        pytest.param("/opt/homebrew/bin/fish", ("-i", "-l", "-c"), id="fish"),
        pytest.param("/bin/tcsh", ("-ic",), id="tcsh"),
        pytest.param("/usr/local/bin/pwsh", ("-Login", "-Command"), id="pwsh"),
    ],
)
def test_shell_argv(shell, flags):
    argv = shell_argv(shell, "MARK")
    assert argv[0] == shell
    assert argv[1:-1] == flags
    assert argv[-1].count("MARK") == 2
    assert "/usr/bin/env -0" in argv[-1]


def test_read_shell_env_returns_the_exports(tmp_path):
    shell = fake_shell(
        tmp_path,
        'export FRUIT=apple\nexport PATH="/orchard/bin:$PATH"\n'
        'export RECIPE="two\nlines"\necho greeting from the rc file',
    )
    answer = read_shell_env(shell, bare_environ(tmp_path, shell))
    assert answer["FRUIT"] == "apple"
    assert answer["PATH"] == "/orchard/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # `env -0` keeps a value holding a newline in one piece.
    assert answer["RECIPE"] == "two\nlines"
    # The child sees the guard.
    assert answer[SHELL_ENV_GUARD] == "1"


def test_read_shell_env_rejects_a_failing_shell(tmp_path):
    shell = fake_shell(tmp_path, "exit 3")
    with pytest.raises(ShellEnvError, match="exited with code 3"):
        read_shell_env(shell, bare_environ(tmp_path, shell))


def test_read_shell_env_rejects_a_silent_shell(tmp_path):
    shell = fake_shell(tmp_path, "exit 0")
    with pytest.raises(ShellEnvError, match="printed no environment"):
        read_shell_env(shell, bare_environ(tmp_path, shell))


def test_read_shell_env_rejects_a_missing_shell(tmp_path):
    shell = str(tmp_path / "nonexistent-shell")
    with pytest.raises(ShellEnvError, match="cannot start"):
        read_shell_env(shell, bare_environ(tmp_path, shell))


def test_read_shell_env_times_out(tmp_path):
    shell = fake_shell(tmp_path, "sleep 30")
    start = time.monotonic()
    with pytest.raises(ShellEnvError, match=r"did not answer within 0\.5 seconds"):
        read_shell_env(shell, bare_environ(tmp_path, shell), timeout=0.5)
    # The shell and its process group were killed rather than waited for.
    assert time.monotonic() - start < 10


def test_import_shell_env_adopts_the_answer(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    shell = fake_shell(
        tmp_path,
        'export FRUIT=apple\nexport PATH="/orchard/bin:$PATH"\n'
        "export SHLVL=42\nexport OLDPWD=/elsewhere",
    )
    environ = bare_environ(tmp_path, shell)

    changes = import_shell_env(environ)

    assert changes is not None
    assert changes["FRUIT"] == "apple"
    assert environ["FRUIT"] == "apple"
    assert environ["PATH"] == "/orchard/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    # The shell's own bookkeeping, and the guard, stay out.
    for name in ("PWD", "OLDPWD", "SHLVL", "_", SHELL_ENV_GUARD):
        assert name not in changes
        assert name not in environ
    assert f"Imported {len(changes)} variables from the login shell {shell}" in (
        caplog.text
    )
    assert "PATH gained /orchard/bin." in caplog.text
    assert "FRUIT" in caplog.text


def test_import_shell_env_reports_an_unchanged_path(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    shell = fake_shell(tmp_path, "export FRUIT=apple")
    environ = bare_environ(tmp_path, shell)
    assert import_shell_env(environ) == {"FRUIT": "apple"}
    assert "PATH is unchanged." in caplog.text


def test_import_shell_env_skips_inside_a_probe(tmp_path):
    """The guard stops a shell configuration running `mpm --shell-env` from
    spawning a shell from within the shell."""
    sentinel = tmp_path / "spawned"
    shell = fake_shell(tmp_path, f"touch {sentinel}")
    environ = bare_environ(tmp_path, shell)
    environ[SHELL_ENV_GUARD] = "1"
    assert import_shell_env(environ) is None
    assert not sentinel.exists()
    assert "PATH" in environ


def test_import_shell_env_warns_on_a_failing_shell(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    shell = fake_shell(tmp_path, "exit 3")
    environ = bare_environ(tmp_path, shell)
    assert import_shell_env(environ) is None
    assert environ == bare_environ(tmp_path, shell)
    assert (
        f"Could not import the login shell environment: {shell} exited with code 3."
    ) in caplog.text


def test_import_shell_env_needs_a_shell(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(shell_env, "_login_shell", lambda: None)
    environ = bare_environ(tmp_path, None)
    assert import_shell_env(environ) is None
    assert "no shell is known for this user" in caplog.text


def test_import_shell_env_falls_back_to_the_passwd_shell(tmp_path, monkeypatch):
    shell = fake_shell(tmp_path, "export FRUIT=apple")
    monkeypatch.setattr(shell_env, "_login_shell", lambda: shell)
    environ = bare_environ(tmp_path, None)
    assert import_shell_env(environ) == {"FRUIT": "apple"}


def test_import_shell_env_is_ignored_on_windows(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(shell_env, "is_any_windows", lambda: True)
    sentinel = tmp_path / "spawned"
    shell = fake_shell(tmp_path, f"touch {sentinel}")
    assert import_shell_env(bare_environ(tmp_path, shell)) is None
    assert not sentinel.exists()
    assert "Ignoring --shell-env" in caplog.text


def test_cli_shell_env_option(invoke, fake_pool, monkeypatch, tmp_path):
    """`--shell-env` adopts the shell's answer into the process environment
    before the managers are selected, and narrates it at `INFO`."""
    shell = fake_shell(tmp_path, "export MPM_TEST_FRUIT=apple")
    monkeypatch.setenv("SHELL", shell)
    # Registered with monkeypatch first, so its teardown restores the variable
    # the import below writes straight into the process environment.
    monkeypatch.setenv("MPM_TEST_FRUIT", "pear")
    monkeypatch.setenv("PATH", os.environ["PATH"])

    result = invoke("--shell-env", "--verbosity", "INFO", "managers")

    assert result.exit_code == 0
    assert os.environ["MPM_TEST_FRUIT"] == "apple"
    assert f"Imported 1 variables from the login shell {shell}" in result.stderr


def test_cli_shell_env_is_off_by_default(invoke, fake_pool, monkeypatch, tmp_path):
    sentinel = tmp_path / "spawned"
    monkeypatch.setenv("SHELL", fake_shell(tmp_path, f"touch {sentinel}"))
    result = invoke("--verbosity", "INFO", "managers")
    assert result.exit_code == 0
    assert not sentinel.exists()
    assert "login shell" not in result.stderr
