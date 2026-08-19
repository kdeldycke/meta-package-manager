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

"""Capture the GNOME Shell extension's menu from a real, headless GNOME session.

Boots `gnome-shell` on a virtual monitor, loads the extension against the
recorded payload of {data}`FIXTURE`, opens the indicator menu and screenshots it
through the shell's own `org.gnome.Shell.Screenshot` D-Bus interface. The result
is a genuine capture of the widget rather than a drawing of one: the shell, the
theme, the fonts and the extension are all real, and only the package data is
held still.

Driven by `.github/workflows/docs-screenshots.yaml`, which is where it belongs:
the capture needs a Linux host with GNOME installed, and a session bus of its
own. A local run is the same command:

```shell-session
$ dbus-run-session -- python3 docs/gnome_screenshots_update.py
```

Every XDG directory is repointed into a scratch tree first, so a local run leaves
the developer's own GNOME settings, extensions and wallpaper untouched.

```{note}
Exactly two things are stubbed. `mpm` is replaced by {data}`FAKE_MPM_SOURCE`,
which serves the recorded payload so the menu is identical on every run instead
of tracking whatever the runner happens to have outdated. And the panel clock is
hidden before the shutter, being the one pixel that changes between two runs of
an otherwise byte-identical image: left in, it would commit a new screenshot on
every single run.
```

```{caution}
The shell is launched with `--unsafe-mode`, which is what unlocks the
`org.gnome.Shell.Eval` method used to open the menu and measure it. That is a
debug channel, fine for a throwaway session on a runner and never something to
enable on a desktop.
```
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

PROJECT_ROOT = Path(__file__).parent.parent

EXTENSION_UUID = "mpm@kdeldycke.github.io"

EXTENSION_DIR = PROJECT_ROOT / "gnome-shell" / EXTENSION_UUID

SCHEMA_ID = "org.gnome.shell.extensions.mpm"

FIXTURE = PROJECT_ROOT / "docs" / "outdated-sample.json"
"""Recorded `mpm --table-format json outdated` payload every capture renders.

Committed rather than produced live: a capture driven by the runner's own
outdated packages would redraw the images on every run, and apt alone changes
daily. Refresh it from a real system with `--record`.
"""

ASSET_DIR = PROJECT_ROOT / "docs" / "assets"

MONITOR = (1920, 1200)
"""Virtual monitor the session renders on, wide and tall enough that no menu
reaches an edge. The captures are cropped to the menu, so this only has to be
generous, never exact.
"""

CAPTURE_MARGIN = 24
"""Desktop background kept around the menu, in pixels."""

BACKGROUND_COLOR = "#2d2364"
"""Flat desktop background behind the menu, the ink of the project's own mark.

A wallpaper would do as well, and would tie the images to whichever
`gnome-backgrounds` release the runner installed.
"""

SHELL_BOOT_TIMEOUT = 90
"""Seconds allowed for the shell to claim its bus name. Software rendering on a
cold runner is slow, and a shell that never comes up fails on the poll below
rather than on this ceiling.
"""

REPORT_TIMEOUT = 60
"""Seconds allowed for the extension to run its first check once the shell is up.
Bounded by the `boot-wait` grace period, which the capture drops to its floor.
"""


class Shot(NamedTuple):
    """One captured image: a file stem and the two settings that shape it."""

    stem: str
    submenu_layout: bool
    dark: bool

    @property
    def path(self) -> Path:
        """Destination of the capture, under `docs/assets/`."""
        return ASSET_DIR / f"{self.stem}.png"


SHOTS = (
    Shot("gnome-shell-flatmenu-light", submenu_layout=False, dark=False),
    Shot("gnome-shell-flatmenu-dark", submenu_layout=False, dark=True),
    Shot("gnome-shell-submenu-light", submenu_layout=True, dark=False),
    Shot("gnome-shell-submenu-dark", submenu_layout=True, dark=True),
)
"""The matrix documented on the extension's page: the one layout switch the
extension exposes, in both shell appearances.

Each shot gets a session of its own. Both settings are applied live by a running
shell, so one session could serve all four, but a fresh one costs seconds and
buys independence: a shot cannot inherit a previous shot's leftover state, and a
failure names the shot that caused it.
"""

FAKE_MPM_SOURCE = '''#!/usr/bin/env python3
"""Stand-in for the `mpm` CLI, serving a recorded payload to the extension.

Answers the three invocations `mpm.js` builds: the `--version` probe, the
best-effort `sync`, and the `outdated` query whose JSON the menu is built from.
Everything it needs arrives through the environment, so this file is a constant.
"""

import os
import pathlib
import sys

if "--version" in sys.argv:
    print(f"mpm, version {os.environ['MPM_FAKE_VERSION']}")

elif "outdated" in sys.argv:
    sys.stdout.write(
        pathlib.Path(os.environ["MPM_FAKE_FIXTURE"]).read_text(encoding="UTF-8")
    )
    # Tells the capture driver the menu is about to be rebuilt.
    pathlib.Path(os.environ["MPM_FAKE_MARKER"]).touch()
'''
"""Written to the scratch tree and pointed at by the `mpm-command` setting, which
is parsed with shell syntax and exists precisely to override the lookup.
"""

_INDICATOR = f"Main.panel.statusArea[{EXTENSION_UUID!r}]"
"""How the shell's own JS reaches our indicator. Python's `repr` of the UUID is
also a valid JS string literal, so the snippets below stay copy-pasteable into
Looking Glass.
"""

_EVAL_REPLY = re.compile(r"\((true|false), (.*)\)\s*", re.DOTALL)
"""`gdbus` renders the `(bs)` reply of `Eval` as a GVariant tuple literal."""


def js(snippet: str) -> str:
    """Resolve the `INDICATOR` placeholder of a JS snippet.

    A plain substitution rather than a format string: these snippets are all
    braces, and `{}` means blocks and objects here, not fields.
    """
    return snippet.replace("INDICATOR", _INDICATOR)


HIDE_CLOCK = js("""(() => {
    Main.panel.statusArea.dateMenu.container.hide();
    return true;
})()""")

REPORT_ITEM_COUNT = js(
    "(() => INDICATOR?._reportSection?._getMenuItems().length ?? 0)()"
)
"""Sanity gate on the capture: an empty report means the extension rendered an
error state (no `mpm`, a version refusal, a parse failure) and the image would
document that instead of the menu. Reaches into the indicator's own private
section deliberately: nothing public reports it, and this file and the extension
ship together.
"""

OPEN_MENU = js("""(() => {
    INDICATOR.menu.open(false);
    return true;
})()""")

MENU_GEOMETRY = js("""(() => {
    const menu = INDICATOR.menu;
    const actor = menu.actor ?? menu.box;
    const [x, y] = actor.get_transformed_position();
    const [width, height] = actor.get_transformed_size();
    const monitor = Main.layoutManager.primaryMonitor;
    return {
        x, y, width, height,
        monitorWidth: monitor.width,
        monitorHeight: monitor.height,
    };
})()""")


def run(
    argv: tuple[str, ...],
    *,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing its output as text."""
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=check,
        env=dict(env) if env is not None else None,
        timeout=timeout,
    )


def gdbus_call(
    object_path: str,
    method: str,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Call one method of the session's `org.gnome.Shell` service."""
    argv = (
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        object_path,
        "--method",
        method,
        *args,
    )
    return run(argv, check=check, timeout=60)


def gvariant(value: str) -> str:
    """Quote a Python string as the GVariant literal `gsettings set` expects."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def gsettings(
    schema: str,
    key: str,
    value: str,
    *,
    schema_dir: Path | None = None,
) -> None:
    """Write one GSettings key, optionally from an out-of-tree schema."""
    env = None
    if schema_dir is not None:
        env = os.environ | {"GSETTINGS_SCHEMA_DIR": str(schema_dir)}
    run(("gsettings", "set", schema, key, value), env=env)


def shell_eval(script: str) -> object:
    """Evaluate a JS snippet inside the running shell and decode its result.

    `Eval` answers `(success, JSON.stringify(result))`, so every snippet here
    returns a value and every reply comes back through `json.loads`.
    """
    reply = gdbus_call("/org/gnome/Shell", "org.gnome.Shell.Eval", script)
    match = _EVAL_REPLY.fullmatch(reply.stdout)
    if match is None:
        msg = f"Unparsable Eval reply: {reply.stdout!r}"
        raise RuntimeError(msg)
    payload = ast.literal_eval(match[2])
    if match[1] != "true":
        msg = f"Eval failed: {payload}\nScript: {script}"
        raise RuntimeError(msg)
    return json.loads(payload) if payload else None


def screenshot_area(x: int, y: int, width: int, height: int, target: Path) -> None:
    """Capture a screen rectangle through the shell's own screenshot service."""
    reply = gdbus_call(
        "/org/gnome/Shell/Screenshot",
        "org.gnome.Shell.Screenshot.ScreenshotArea",
        str(x),
        str(y),
        str(width),
        str(height),
        "false",
        str(target),
    )
    if not reply.stdout.startswith("(true,"):
        msg = f"Screenshot refused: {reply.stdout.strip()}"
        raise RuntimeError(msg)


def wait_until(probe: Callable[[], bool], timeout: int, description: str) -> None:
    """Poll until `probe` answers true, or give up with a named failure."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe():
            return
        time.sleep(0.25)
    msg = f"Timed out after {timeout}s waiting for {description}."
    raise RuntimeError(msg)


def shell_is_up() -> bool:
    """Whether the shell has claimed its name and answers a property read."""
    reply = gdbus_call(
        "/org/gnome/Shell",
        "org.freedesktop.DBus.Properties.Get",
        "org.gnome.Shell",
        "ShellVersion",
        check=False,
    )
    return reply.returncode == 0


def isolate_environment(root: Path) -> None:
    """Repoint every XDG directory into a scratch tree, dconf included.

    Both halves matter: it keeps a local run from rewriting the developer's own
    GNOME settings, extensions and wallpaper, and it guarantees the capture
    starts from a clean profile instead of inheriting one.

    ```{caution}
    The GSettings backend has to move with them. dconf writes through a
    D-Bus-activated service, which inherits the environment the bus was started
    with rather than this process's, so a repointed `XDG_CONFIG_HOME` would
    leave `gsettings` writing to the real user database while the shell read the
    empty scratch one, and the extension would never come up enabled. The
    keyfile backend has no service behind it: writer and reader both resolve the
    same file out of their own environment.
    ```
    """
    os.environ["GSETTINGS_BACKEND"] = "keyfile"
    for variable, name in (
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "runtime"),
        ("XDG_STATE_HOME", "state"),
    ):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        os.environ[variable] = str(path)


def project_version() -> str:
    """Read `__version__` off the package without importing it.

    The capture runs on a bare interpreter, with no project install to import
    from, and the version only ever reaches the fake CLI's `--version` line.
    """
    source = (PROJECT_ROOT / "meta_package_manager" / "__init__.py").read_text(
        encoding="UTF-8",
    )
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if match is None:
        msg = "Cannot find __version__ in meta_package_manager/__init__.py."
        raise RuntimeError(msg)
    return match[1]


def install_extension() -> Path:
    """Copy the extension into the scratch profile and compile its schema.

    Mirrors the source-checkout install documented on the extension's page, with
    a copy instead of a symlink so `glib-compile-schemas` writes its output into
    the scratch tree rather than into the working copy.
    """
    target = (
        Path(os.environ["XDG_DATA_HOME"])
        / "gnome-shell"
        / "extensions"
        / EXTENSION_UUID
    )
    shutil.copytree(EXTENSION_DIR, target, dirs_exist_ok=True)
    run(("glib-compile-schemas", "--strict", str(target / "schemas")))
    return target


def write_fake_mpm(root: Path) -> Path:
    """Materialize the stand-in CLI and make it executable."""
    path = root / "fake-mpm"
    path.write_text(FAKE_MPM_SOURCE, encoding="UTF-8")
    path.chmod(0o755)
    return path


@contextmanager
def shell_session(log: Path) -> Iterator[None]:
    """Run a headless `gnome-shell` for the duration of the block."""
    argv = (
        "gnome-shell",
        "--headless",
        "--no-x11",
        "--virtual-monitor",
        "{}x{}".format(*MONITOR),
        # Unlocks org.gnome.Shell.Eval, the only way in to open the menu.
        "--unsafe-mode",
    )
    with log.open("w", encoding="UTF-8") as stream:
        process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT)
        try:

            def up() -> bool:
                if process.poll() is not None:
                    msg = (
                        f"gnome-shell exited with {process.returncode} before "
                        f"claiming its bus name. Log: {log}"
                    )
                    raise RuntimeError(msg)
                return shell_is_up()

            wait_until(up, SHELL_BOOT_TIMEOUT, "gnome-shell to claim its bus name")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


def capture(shot: Shot, scratch: Path, schema_dir: Path) -> None:
    """Boot a session shaped by one shot's settings and photograph its menu."""
    print(f"Capturing {shot.path.name}")
    marker = scratch / "outdated-served"
    marker.unlink(missing_ok=True)

    gsettings(
        SCHEMA_ID,
        "submenu-layout",
        "true" if shot.submenu_layout else "false",
        schema_dir=schema_dir,
    )
    gsettings(
        "org.gnome.desktop.interface",
        "color-scheme",
        gvariant("prefer-dark" if shot.dark else "prefer-light"),
    )

    with shell_session(scratch / f"{shot.stem}.log"):
        wait_until(marker.exists, REPORT_TIMEOUT, "the extension's first check")
        # The report lands one turn of the loop after the payload is served.
        wait_until(
            lambda: bool(shell_eval(REPORT_ITEM_COUNT)),
            REPORT_TIMEOUT,
            "the menu to be populated",
        )
        shell_eval(HIDE_CLOCK)
        shell_eval(OPEN_MENU)
        # The menu opens unanimated, but still needs a frame to lay out.
        time.sleep(1)

        geometry = shell_eval(MENU_GEOMETRY)
        if not isinstance(geometry, dict):
            msg = f"Unexpected menu geometry: {geometry!r}"
            raise TypeError(msg)
        left = max(0, math.floor(geometry["x"]) - CAPTURE_MARGIN)
        right = min(
            geometry["monitorWidth"],
            math.ceil(geometry["x"] + geometry["width"]) + CAPTURE_MARGIN,
        )
        bottom = min(
            geometry["monitorHeight"],
            math.ceil(geometry["y"] + geometry["height"]) + CAPTURE_MARGIN,
        )
        # Anchored at the top of the screen: the top bar is part of the subject,
        # the indicator icon and its outdated count being what the menu hangs off.
        screenshot_area(left, 0, right - left, bottom, shot.path)


def capture_all(workspace: Path | None = None) -> None:
    """Set the session up once, then capture each shot in its own shell.

    A `workspace` outlives the run and keeps the per-shot shell logs, which is
    what CI uploads when a capture fails. Without one the whole scratch tree is
    a temporary directory that takes the logs with it.
    """
    with TemporaryDirectory(prefix="mpm-gnome-capture-") as name:
        scratch = workspace if workspace is not None else Path(name)
        scratch.mkdir(parents=True, exist_ok=True)
        isolate_environment(scratch)
        schema_dir = install_extension() / "schemas"
        fake_mpm = write_fake_mpm(scratch)

        os.environ |= {
            "MPM_FAKE_FIXTURE": str(FIXTURE),
            "MPM_FAKE_MARKER": str(scratch / "outdated-served"),
            "MPM_FAKE_VERSION": project_version(),
            # Nothing on a runner accelerates GL, and mutter is quicker to say so
            # than to discover it.
            "LIBGL_ALWAYS_SOFTWARE": "1",
            # No accessibility bus in a throwaway session; skip the warning.
            "NO_AT_BRIDGE": "1",
        }

        gsettings("org.gnome.shell", "disable-user-extensions", "false")
        gsettings(
            "org.gnome.shell",
            "enabled-extensions",
            f"[{gvariant(EXTENSION_UUID)}]",
        )
        # A flat background, and the GNOME UI font rather than whichever default
        # the runner's fontconfig lands on.
        gsettings("org.gnome.desktop.background", "picture-options", gvariant("none"))
        gsettings("org.gnome.desktop.background", "picture-uri", gvariant(""))
        gsettings("org.gnome.desktop.background", "picture-uri-dark", gvariant(""))
        gsettings(
            "org.gnome.desktop.background", "primary-color", gvariant(BACKGROUND_COLOR)
        )
        gsettings("org.gnome.desktop.interface", "font-name", gvariant("Cantarell 11"))

        gsettings(SCHEMA_ID, "always-visible", "true", schema_dir=schema_dir)
        gsettings(SCHEMA_ID, "boot-wait", "5", schema_dir=schema_dir)
        # Far enough out that no second check can fire mid-capture.
        gsettings(SCHEMA_ID, "check-interval", "20000", schema_dir=schema_dir)
        gsettings(
            SCHEMA_ID, "mpm-command", gvariant(str(fake_mpm)), schema_dir=schema_dir
        )
        gsettings(SCHEMA_ID, "notify", "false", schema_dir=schema_dir)
        gsettings(SCHEMA_ID, "show-count", "true", schema_dir=schema_dir)

        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        for shot in SHOTS:
            capture(shot, scratch, schema_dir)

        for shot in SHOTS:
            print(
                f"{shot.path.relative_to(PROJECT_ROOT)}: "
                f"{shot.path.stat().st_size} bytes"
            )


def record() -> None:
    """Re-record the fixture from a real `mpm` run on the current system."""
    mpm = shutil.which("mpm")
    if mpm is None:
        sys.exit("No mpm on PATH: install it, or run this from an activated venv.")
    reply = run(
        (
            mpm,
            "--no-color",
            "--verbosity",
            "CRITICAL",
            "--table-format",
            "json",
            "outdated",
        ),
    )
    payload = json.loads(reply.stdout)
    if not payload:
        sys.exit("mpm reports nothing outdated: nothing to record.")
    FIXTURE.write_text(
        json.dumps(payload, indent="\t", sort_keys=True) + "\n",
        encoding="UTF-8",
    )
    print(
        f"Recorded {sum(len(m['packages']) for m in payload.values())} packages "
        f"from {len(payload)} managers into {FIXTURE.relative_to(PROJECT_ROOT)}."
    )


def main() -> None:
    """Capture by default; recording the fixture is the deliberate exception."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--record",
        action="store_true",
        help="Refresh the committed payload from a real mpm run, and capture nothing.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Scratch tree to run in, kept on exit so the shell logs survive.",
    )
    options = parser.parse_args()
    if options.record:
        record()
    else:
        capture_all(options.workspace)


if __name__ == "__main__":
    main()
