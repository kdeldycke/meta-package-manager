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
"""Import of the login shell environment into a run started outside a terminal.

A process started by a desktop host or a scheduler inherits the environment of
that host, not the one a terminal builds. `launchd` hands a macOS application
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, the systemd user session behind GNOME Shell
never reads `.bashrc` or `.zshrc`, and `cron` gives its jobs `/usr/bin:/bin`. A
manager installed under the home directory (`~/.cargo/bin`, `~/.local/bin`,
`~/Library/pnpm/bin`) is then invisible to the pool, and pnpm refuses every
`--global` command until its bin directory is on `PATH`. The menu bar plugin and
the GNOME Shell extension both start `mpm` that way.

The `--shell-env` option answers this the way VS Code and Emacs do: run the
user's login shell once, as an interactive login shell so both the profile and
the rc file are read, ask it for its exported environment, and adopt that
environment before any manager is probed. The shell's own bookkeeping variables
are left alone (see {data}`SHELL_ENV_KEPT`), and the shell has
{data}`SHELL_ENV_TIMEOUT` seconds to answer before the run continues with the
environment it started with.

```{note}
Windows never needs this: a program started from the desktop there already gets
the user's `PATH` from the registry. The option is accepted and ignored.
```

```{caution}
A login shell exports tokens and secrets like any other variable. The answer is
read with `/usr/bin/env -0`, kept in memory, and never logged: only the names of
the variables that changed are narrated, at `DEBUG`.
```
"""

from __future__ import annotations

import logging
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path
from typing import Final

from extra_platforms import C_SHELLS, WINDOWS_SHELLS, is_any_windows

# Windows has no passwd database, and never reaches the lookup either.
if sys.platform != "win32":
    import pwd

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping


SHELL_ENV_GUARD: Final = "MPM_RESOLVING_SHELL_ENV"
"""Set to `1` in the environment of the shell answering the probe.

A shell configuration can read it to skip a slow or interactive step, the way
`VSCODE_RESOLVING_ENVIRONMENT` serves VS Code. It is also the recursion guard: a
configuration that itself runs `mpm --shell-env` would spawn a shell from within
the shell, so {func}`import_shell_env` returns at once when it finds the
variable already set.
"""

SHELL_ENV_KEPT: Final[frozenset[str]] = frozenset({
    "_",
    "OLDPWD",
    "PWD",
    "SHLVL",
    SHELL_ENV_GUARD,
})
"""Variables the shell's answer never overwrites.

`PWD`, `OLDPWD`, `SHLVL` and `_` describe the shell that answered, not the run
that asked: adopting them would place `mpm` in a directory it is not in. The
guard is kept out so it does not stick to the run once the probe is over.
"""

SHELL_ENV_TIMEOUT: Final = 10
"""Seconds the login shell gets to answer, VS Code's own budget.

An interactive shell runs the whole rc file, plugin managers and prompt
included: half a second is typical, a plugin manager installing itself on first
run is not. Past the budget the shell is killed with its process group and the
run keeps the environment it started with.
"""

_ENV_DUMP: Final = "printf '%s' {mark}; /usr/bin/env -0; printf '%s' {mark}"
"""Command the shell runs, once the marker is spliced in.

Three external commands and two `;`, which every shell {func}`shell_argv` knows
parses the same way. The markers bracket the answer, so whatever the rc file
prints (a greeting, a prompt, a warning) is discarded, and `env -0` separates the
entries with `NUL`, so a value holding a newline survives.
"""


class ShellEnvError(Exception):
    """The login shell gave no usable answer."""


def shell_argv(shell: str, mark: str) -> tuple[str, ...]:
    """Argv running `shell` as an interactive login shell around the dump command.

    Follows VS Code's `shellEnv.ts`: `-i -l -c` for every Bourne-family shell,
    fish and nushell included, `-ic` for the C shells, whose `-l` has to be the
    only flag, and `-Login -Command` for PowerShell. The family is read off
    extra-platforms' shell catalog, keyed by the file name of the resolved path,
    so `/bin/sh` linking to `bash` is treated as `bash`.

    ```{todo}
    Match the file name through `extra_platforms.shell_from_path()` and drop the
    `pwsh` special case once the floor reaches the extra-platforms release
    carrying [kdeldycke/extra-platforms@9a9393d](https://github.com/kdeldycke/extra-platforms/commit/9a9393d28a643a79043249247582bece80bb1fff):
    the catalog keys PowerShell by `powershell`, where its binary is `pwsh` on
    every platform since `6.0`.
    ```
    """
    command = _ENV_DUMP.format(mark=mark)
    stem = Path(shell).resolve().stem.lower()
    if stem in C_SHELLS:
        return (shell, "-ic", command)
    if stem in WINDOWS_SHELLS or stem == "pwsh":
        return (shell, "-Login", "-Command", command)
    return (shell, "-i", "-l", "-c", command)


def read_shell_env(
    shell: str,
    environ: Mapping[str, str],
    timeout: float = SHELL_ENV_TIMEOUT,
) -> dict[str, str]:
    """Run `shell` and return the environment it exports.

    The shell starts with `environ` plus {data}`SHELL_ENV_GUARD`, in a session
    of its own: an interactive shell would otherwise claim the terminal `mpm`
    runs in, and a timeout has to reap whatever the rc file left running.

    :raises ShellEnvError: when the shell cannot start, exits with an error, does
        not answer within `timeout` seconds, or prints no environment between the
        markers.
    """
    mark = f"mpm-shell-env-{secrets.token_hex(8)}"
    argv = shell_argv(shell, mark)
    try:
        process = subprocess.Popen(
            argv,
            env={**environ, SHELL_ENV_GUARD: "1"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as ex:
        raise ShellEnvError(f"cannot start {shell}: {ex.strerror}") from ex
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ShellEnvError(
            f"{shell} did not answer within {timeout} seconds"
        ) from None
    if stderr:
        # The rc file's own noise, useful when the answer is not what the user
        # expected: a plugin manager complaining, a profile printing a warning.
        logging.debug(f"{shell} printed on <stderr>:\n{os.fsdecode(stderr).rstrip()}")
    if process.returncode:
        raise ShellEnvError(f"{shell} exited with code {process.returncode}")

    marker = mark.encode()
    _, opening, rest = stdout.partition(marker)
    body, closing, _ = rest.partition(marker)
    if not opening or not closing:
        raise ShellEnvError(f"{shell} printed no environment")
    shell_env = {}
    for entry in body.split(b"\0"):
        name, equal, value = entry.partition(b"=")
        if name and equal:
            shell_env[os.fsdecode(name)] = os.fsdecode(value)
    if not shell_env:
        raise ShellEnvError(f"{shell} printed an empty environment")
    return shell_env


def _login_shell() -> str | None:
    """The user's shell from the passwd database, for a run started with no `SHELL`.

    `cron` is the usual case: it sets `SHELL=/bin/sh`, but a job that unsets it
    still has an owner with a login shell.
    """
    if sys.platform == "win32":
        return None
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or None
    except KeyError:
        return None


def import_shell_env(
    environ: MutableMapping[str, str] | None = None,
    timeout: float = SHELL_ENV_TIMEOUT,
) -> dict[str, str] | None:
    """Adopt the login shell's exported environment into `environ`.

    `environ` defaults to {data}`os.environ`, which every later `PATH` lookup
    and subprocess reads. The shell is the one `SHELL` names, else the user's
    login shell from the passwd database.

    Returns the variables that changed, or `None` when nothing was imported: on
    Windows, inside the shell answering a probe, when no shell is known, or when
    the shell gave no usable answer. Each case is narrated, the last two as a
    warning, since the user asked for the import and did not get it.
    """
    if environ is None:
        environ = os.environ
    if is_any_windows():
        logging.info(
            "Ignoring --shell-env: a desktop program already gets the user's PATH "
            "on Windows."
        )
        return None
    if environ.get(SHELL_ENV_GUARD):
        logging.debug("Skipping the login shell probe: already running inside one.")
        return None
    shell = environ.get("SHELL") or _login_shell()
    if not shell:
        logging.warning(
            "Could not import the login shell environment: no shell is known for "
            "this user."
        )
        return None
    try:
        shell_env = read_shell_env(shell, environ, timeout)
    except ShellEnvError as ex:
        logging.warning(f"Could not import the login shell environment: {ex}.")
        return None

    changes = {
        name: value
        for name, value in shell_env.items()
        if name not in SHELL_ENV_KEPT and environ.get(name) != value
    }
    previous_path = environ.get("PATH", "").split(os.pathsep)
    environ.update(changes)
    gained = [
        folder
        for folder in environ.get("PATH", "").split(os.pathsep)
        if folder and folder not in previous_path
    ]
    logging.info(
        f"Imported {len(changes)} variables from the login shell {shell}; "
        + (f"PATH gained {', '.join(gained)}." if gained else "PATH is unchanged.")
    )
    logging.debug(
        "Variables imported from the login shell: " + ", ".join(sorted(changes))
        if changes
        else "The login shell exports nothing the run did not already have."
    )
    return changes
