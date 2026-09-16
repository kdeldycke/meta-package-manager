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
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
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

MONITOR = (3840, 3200)
"""Virtual monitor the session renders on, in device pixels.

Sized so that {data}`MONITOR_SCALE` divides it back to a `1920x1600` desktop:
wide enough that no menu reaches an edge, and tall enough to hold the
preferences window grown to {data}`PREFERENCES_PROBE_HEIGHT`. The menu captures
are cropped to the menu, so only the window one depends on this.
"""

PREFERENCES_PROBE_HEIGHT = 1500
"""Logical height the preferences window is grown to before it is measured.

`Adw.PreferencesWindow` opens at a size of its own choosing and scrolls its page,
so a capture at that size documents the first two groups and hides the other
four. The window is grown past the whole page instead, then a strip down its
middle is photographed: the blank band under the last card says how tall the
page really is, and {func}`fit_prefs_window` shrinks the window to that before
the shutter. A fixed height was tuned to the page first, and a row added to
`prefs.js` later pushed the *About* group's last line under the window's edge
([#2086](https://github.com/kdeldycke/meta-package-manager/pull/2086)), which
is the failure a measured height cannot have. This only has to clear the page: a
page taller than it fails the capture, naming the shortfall.
"""

FRAME_TOLERANCE_LEVELS = 2
"""Largest per-channel difference a fresh capture may show against the committed
frame and still count as the same picture.

A live desktop repaints one menu with rounding jitter: two runs of a single
commit differed by one level on eleven pixels along a menu's rounded corners,
and a sync comparing bytes rewrote the file for it
([#2090](https://github.com/kdeldycke/meta-package-manager/pull/2090)). A
change worth committing moves whole rows, which no cap this low lets through.
"""

FRAME_TOLERANCE_SHARE = 0.001
"""Largest share of a frame's pixels allowed to differ within that cap."""

PREFERENCES_FOOT = 32
"""Logical pixels of page kept below the last card, once the window is fitted.

What the fixed height left in the frame it was tuned against, and enough for
the card's shadow to fade into the page instead of being cut by the edge.
"""

PREFERENCES_WIDTH = 720
"""Logical width the preferences window is grown to, beside its height.

`Adw.PreferencesWindow` opens at `640`. This buys the rows very little on its
own, `Adw.PreferencesPage` clamping its content: measured across two captures,
growing the window by 80 logical pixels widened the *About* title's room by 23
and spent the rest on margin. The title that wrapped there was shortened
instead, and this is the margin around that fix rather than the fix itself.
"""

MONITOR_SCALE = 2
"""Logical scale applied to that monitor, which is what makes the captures HiDPI.

Every coordinate the shell reports, and every one `ScreenshotArea` takes, stays
logical; only the framebuffer behind them doubles. So the menu lays out exactly
as it would on a `1920x1200` desktop and comes back drawn at twice the pixels,
which is what a Retina reader needs and what upscaling a `1x` capture cannot
fake. The documentation renders these at `:scale: 50` to land back at their
logical size.
"""

CAPTURE_MARGIN = 24
"""Desktop background kept around the menu, in pixels."""

PINNED_LAST_CHECK = "10:30 AM"
"""Clock the menu's *Last checked* row is pinned to before the shutter.

The row reports when the extension last ran `mpm`, so it reads differently on
every capture and would commit four fresh images per run on its own. Pinned
rather than hidden, and only its time is substituted: the row belongs in the
menu, and its wording belongs to the extension.
"""

BACKGROUND_COLOR = "#2d2364"
"""Flat desktop background behind the menu, the ink of the project's own mark.

A wallpaper would do as well, and would tie the images to whichever
`gnome-backgrounds` release the runner installed.
"""

WAYLAND_DISPLAY = "mpm-capture-0"
"""Name of the Wayland socket the session hosts.

Named rather than discovered so it can be published to the bus below without
first hunting for whichever `wayland-N` mutter settled on.
"""

ACTIVATION_ENVIRONMENT = (
    "ADW_DEBUG_COLOR_SCHEME",
    "GDK_BACKEND",
    "GSETTINGS_BACKEND",
    "WAYLAND_DISPLAY",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_CURRENT_DESKTOP",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME",
)
"""What a D-Bus-activated service has to be told about this session.

An activated process inherits the environment the *bus* was started with, not
the one its caller holds, and this bus predates the compositor: without this
publication the preferences window host launches with no `WAYLAND_DISPLAY` to
connect to and dies before it can map a window, which the shell forwards on as
an unhandled promise rejection and nothing else reports.
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
    """One captured image: a file stem and the state that shapes it."""

    stem: str
    dark: bool
    group_by_manager: bool = False
    align_columns: bool = True
    preferences: bool = False
    """Photograph the preferences window instead of the indicator menu."""

    @property
    def path(self) -> Path:
        """Destination of the capture, under `docs/assets/`."""
        return ASSET_DIR / f"{self.stem}.png"


SHOTS = (
    *(
        Shot(
            "-".join(
                (
                    "gnome-shell",
                    "grouped" if grouped else "flat",
                    "table" if aligned else "standard",
                    "rendering",
                    "dark" if dark else "light",
                )
            ),
            dark=dark,
            group_by_manager=grouped,
            align_columns=aligned,
        )
        for grouped in (False, True)
        for aligned in (False, True)
        for dark in (False, True)
    ),
    Shot("gnome-shell-preferences-light", dark=False, preferences=True),
    Shot("gnome-shell-preferences-dark", dark=True, preferences=True),
)
"""Everything the extension's page illustrates: the two layout switches the menu
exposes, in every combination, and the preferences window, each in both shell
appearances. The stems spell the layout the way the SwiftBar and Xbar captures
do, so the two pages line up frame for frame.

Each shot gets a session of its own. The layout and the appearance are both
applied live by a running shell, so one session could serve several, but a fresh
one costs seconds and buys independence: a shot cannot inherit a previous shot's
leftover state, a failure names the shot that caused it, and the preferences
window needs a settings profile the menu shots deliberately do not have.
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

_UUID = repr(EXTENSION_UUID)
"""The UUID as a JS string literal. Python's `repr` is one too."""

_INDICATOR = f"Main.panel.statusArea[{EXTENSION_UUID!r}]"
"""How the shell's own JS reaches our indicator. Python's `repr` of the UUID is
also a valid JS string literal, so the snippets below stay copy-pasteable into
Looking Glass.
"""

DISPLAY_CONFIG_NAME = "org.gnome.Mutter.DisplayConfig"
"""Bus name owning the monitor layout, exported by the shell beside its own."""

DISPLAY_CONFIG_PATH = "/org/gnome/Mutter/DisplayConfig"

_EVAL_REPLY = re.compile(r"\((true|false), (.*)\)\s*", re.DOTALL)
"""`gdbus` renders the `(bs)` reply of `Eval` as a GVariant tuple literal."""


def js(snippet: str) -> str:
    """Resolve the `INDICATOR` placeholder of a JS snippet.

    A plain substitution rather than a format string: these snippets are all
    braces, and `{}` means blocks and objects here, not fields.

    ```{caution}
    No snippet may carry a backslash. `gdbus` parses each argument as a
    GVariant literal, which consumes escape sequences before the shell ever
    sees them, so a `\\d` in a regex arrives as a literal `d` and the pattern
    quietly stops matching instead of failing. Character classes say the same
    thing and survive the trip. Raised here rather than documented in a
    comment, because the failure has no symptom of its own.
    ```
    """
    if "\\" in snippet:
        msg = f"Backslash in a JS snippet, gdbus will eat it: {snippet!r}"
        raise ValueError(msg)
    return snippet.replace("INDICATOR", _INDICATOR).replace("UUID", _UUID)


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

PIN_LAST_CHECK = js("""(() => {
    const label = INDICATOR._lastCheckedItem.label;
    label.text = label.text.replace(
        /[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AP]M)?/, 'PINNED');
    return label.text;
})()""").replace("PINNED", PINNED_LAST_CHECK)

EXTENSION_LOADED = js("""(() => {
    const extension = Main.extensionManager.lookup(UUID);
    if (!extension)
        return null;
    return {state: extension.state, hasPrefs: !!extension.hasPrefs};
})()""")
"""What the shell knows about the extension, `hasPrefs` above all.

That flag is the gate on opening a preferences window, and the only thing that
reports it: the `gnome-extensions prefs` CLI answers a bare exit code 2 whether
the extension is unknown, carries no preferences, or the window host failed to
activate.
"""

OPEN_MENU = js("""(() => {
    INDICATOR.menu.open(false);
    return true;
})()""")

EXPAND_FIRST_SECTION = js("""(() => {
    const first = INDICATOR._reportSection._getMenuItems().find(item => item.menu);
    if (!first)
        return false;
    first.menu.open(false);
    return true;
})()""")
"""Unfold the first manager section of a grouped menu.

Without it the two grouped captures of an appearance come out byte-identical:
everything `align-columns` decides sits inside a section, and the top level
shows nothing but manager rows. Opened without animation, like the menu itself.
"""

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
    """Run a command, capturing its output as text.

    Output is captured, so a failure has to carry its own diagnosis: the default
    {exc}`~subprocess.CalledProcessError` reports the exit code and drops the
    message the command printed to explain it.
    """
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="UTF-8",
        check=False,
        env=dict(env) if env is not None else None,
        timeout=timeout,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        msg = f"{argv[0]} exited {result.returncode}: {detail}"
        raise RuntimeError(msg)
    return result


def gdbus_call(
    object_path: str,
    method: str,
    *args: str,
    dest: str = "org.gnome.Shell",
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Call one method on a service the shell exports.

    Two bus names are in play: the shell's own, and the `org.gnome.Mutter.*`
    family it also owns, which is where the monitor layout lives.
    """
    argv = (
        "gdbus",
        "call",
        "--session",
        "--dest",
        dest,
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


def publish_activation_environment() -> None:
    """Hand {data}`ACTIVATION_ENVIRONMENT` to the session bus."""
    pairs = ", ".join(
        f"{name!r}: {os.environ[name]!r}"
        for name in ACTIVATION_ENVIRONMENT
        if name in os.environ
    )
    gdbus_call(
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus.UpdateActivationEnvironment",
        "{" + pairs + "}",
        dest="org.freedesktop.DBus",
    )


def apply_monitor_scale() -> None:
    """Put the virtual monitor on a logical scale of {data}`MONITOR_SCALE`.

    Mutter takes the scale from a monitor configuration rather than from the
    `--virtual-monitor` argument, so it can only be set once the session is up.
    `ApplyMonitorsConfig` is the call the Display panel makes, and its
    `temporary` method leaves nothing on disk for a later run to inherit.
    """
    state = gdbus_call(
        DISPLAY_CONFIG_PATH,
        f"{DISPLAY_CONFIG_NAME}.GetCurrentState",
        dest=DISPLAY_CONFIG_NAME,
    ).stdout
    # The reply opens on its serial, then on the monitor array, whose first
    # entry pairs a connector tuple with the modes it advertises.
    serial = re.match(r"\((?:uint32 )?(\d+),", state)
    monitor = re.search(r"\(\('([^']+)',", state)
    if serial is None or monitor is None:
        msg = f"Unreadable monitor state: {state!r}"
        raise RuntimeError(msg)
    mode = re.search(r"\[\('([^']+)',", state[monitor.end() :])
    if mode is None:
        msg = f"Monitor {monitor[1]!r} advertises no mode: {state!r}"
        raise RuntimeError(msg)
    layout = (
        f"[(0, 0, {float(MONITOR_SCALE)}, 0, true, "
        f"[('{monitor[1]}', '{mode[1]}', {{}})])]"
    )
    # Method 1 is `temporary`: applied to the running session only.
    gdbus_call(
        DISPLAY_CONFIG_PATH,
        f"{DISPLAY_CONFIG_NAME}.ApplyMonitorsConfig",
        serial[1],
        "1",
        layout,
        "{}",
        dest=DISPLAY_CONFIG_NAME,
    )


FOCUSED_TITLE = js("""(() => {
    const window = global.display.focus_window;
    return window ? window.get_title() || '' : null;
})()""")
"""Title of the window holding focus, which is the one the shutter will take.

`ScreenshotWindow` photographs the focused window and answers a bare `false`
when nothing holds focus, so activating a window is not enough: the activation
has to be observed to land before the shutter, and a fixed sleep only guesses.
"""


def grow_prefs_window(height: int) -> str:
    """JS asking the preferences window to take a height, at the width captured.

    The frame keeps the `x` it opened at, as the capture crops to the window
    and a centered one would look no different.
    """
    return (
        js("""(() => {
    const windows = global.display.list_all_windows();
    const match = windows.find(w => (w.get_title() || '').includes(NAME));
    if (!match)
        return false;
    const frame = match.get_frame_rect();
    match.move_resize_frame(false, frame.x, 0, WIDTH, HEIGHT);
    return true;
})()""")
        .replace("NAME", repr(extension_name()))
        .replace("HEIGHT", str(height))
        .replace("WIDTH", str(PREFERENCES_WIDTH))
    )


def prefs_frame() -> str:
    """JS reporting the preferences window's frame, once it has one.

    Read in a turn of its own rather than after the resize that asks for it: a
    resize is a request to the client, answered whenever GTK gets to it, so the
    frame read back in the same turn is the one before the request (or zero,
    for a window still being mapped).
    """
    return js("""(() => {
    const windows = global.display.list_all_windows();
    const match = windows.find(w => (w.get_title() || '').includes(NAME));
    if (!match)
        return null;
    const frame = match.get_frame_rect();
    return {x: frame.x, y: frame.y, width: frame.width, height: frame.height};
})()""").replace("NAME", repr(extension_name()))


def grow_prefs_to(height: int) -> dict[str, int]:
    """Resize the preferences window to `height`, and return its frame once there.

    Asked on every turn of the poll rather than once: a request sent to a
    window still being mapped is simply dropped, and the client answers
    whenever GTK gets to it. The observed height rides in the failure, so a
    window that will not move says how far it got.
    """
    grow = grow_prefs_window(height)
    frame = prefs_frame()
    seen: object = None
    deadline = time.monotonic() + REPORT_TIMEOUT
    while time.monotonic() < deadline:
        shell_eval(grow)
        seen = shell_eval(frame)
        if isinstance(seen, dict) and abs(int(seen["height"]) - height) <= 1:
            return {key: int(seen[key]) for key in ("x", "y", "width", "height")}
        time.sleep(0.5)
    msg = f"The preferences window stopped at {seen!r}, short of {height}px."
    raise RuntimeError(msg)


class Frame(NamedTuple):
    """A decoded PNG: its geometry and its rows of pixel bytes."""

    width: int
    channels: int
    rows: list[bytes]


def png_rows(target: Path) -> Frame:
    """Decode a PNG into its rows of pixel bytes.

    Enough of a decoder for what this driver reads back: 8-bit RGB or RGBA,
    not interlaced. Every filter type is unwound, any of the five being free to
    open any row, and the loop is per byte: a second or so for a full frame,
    nothing for the strip {func}`fit_prefs_window` photographs.
    """
    data = target.read_bytes()
    width, height = png_size(target)
    depth, color, interlace = data[24], data[25], data[28]
    if depth != 8 or color not in (2, 6) or interlace:
        msg = f"{target} is not an 8-bit RGB or RGBA non-interlaced PNG"
        raise ValueError(msg)
    channels = 4 if color == 6 else 3
    stride = width * channels
    compressed = b""
    position = 8
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        if kind == b"IDAT":
            compressed += data[position + 8 : position + 8 + length]
        position += 12 + length
    raw = zlib.decompress(compressed)
    rows: list[bytes] = []
    above = bytearray(stride)
    for index in range(height):
        start = index * (stride + 1)
        kind_byte = raw[start]
        line = bytearray(raw[start + 1 : start + 1 + stride])
        for offset in range(stride):
            left = line[offset - channels] if offset >= channels else 0
            up = above[offset]
            corner = above[offset - channels] if offset >= channels else 0
            if kind_byte == 1:
                line[offset] = (line[offset] + left) & 0xFF
            elif kind_byte == 2:
                line[offset] = (line[offset] + up) & 0xFF
            elif kind_byte == 3:
                line[offset] = (line[offset] + (left + up) // 2) & 0xFF
            elif kind_byte == 4:
                estimate = left + up - corner
                distances = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - corner),
                )
                nearest = (left, up, corner)[distances.index(min(distances))]
                line[offset] = (line[offset] + nearest) & 0xFF
        rows.append(bytes(line))
        above = line
    return Frame(width, channels, rows)


def settle_frame(fresh: Path, target: Path) -> None:
    """Put a fresh capture in place of the committed frame, unless it is the same picture.

    Kept when the capture differs from the frame by no more than
    {data}`FRAME_TOLERANCE_LEVELS` on fewer than {data}`FRAME_TOLERANCE_SHARE`
    of its pixels, and replaced otherwise. A frame with no committed version, or
    one of another size, is always written. Compared on the color channels: the
    optimizer that stored the committed frame drops an alpha channel that is
    opaque throughout, and a capture carries one.
    """
    if not target.exists() or png_size(fresh) != png_size(target):
        shutil.move(fresh, target)
        print(f"  {target.name}: written")
        return
    old, new = png_rows(target), png_rows(fresh)
    differing = 0
    worst = 0
    for row_old, row_new in zip(old.rows, new.rows, strict=True):
        planes_old = [row_old[channel :: old.channels] for channel in range(3)]
        planes_new = [row_new[channel :: new.channels] for channel in range(3)]
        if planes_old == planes_new:
            continue
        for x in range(old.width):
            deltas = [abs(planes_old[c][x] - planes_new[c][x]) for c in range(3)]
            if any(deltas):
                differing += 1
                worst = max(worst, *deltas)
    share = differing / (old.width * len(old.rows))
    levels = "level" if worst == 1 else "levels"
    verdict = (
        f"differs from the committed frame on {differing} pixels, "
        f"by at most {worst} {levels}"
    )
    if worst <= FRAME_TOLERANCE_LEVELS and share <= FRAME_TOLERANCE_SHARE:
        fresh.unlink()
        print(f"  {target.name}: kept, the capture {verdict}")
        return
    shutil.move(fresh, target)
    print(f"  {target.name}: replaced, the capture {verdict}")


def measure_page_foot(strip: Path) -> int:
    """Device rows of bare page under the last card, read off a strip of window.

    The page background is sampled a few rows above the window's bottom edge,
    clear of the border the edge itself draws, and followed upwards until the
    last card's shadow breaks it. A page that overflows the window has a card
    there instead of the page, and the band comes back too short to fit.
    """
    rows = png_rows(strip).rows
    index = len(rows) - 1 - 4 * MONITOR_SCALE
    background = rows[index]
    while index > 0 and rows[index] == background:
        index -= 1
    return len(rows) - 1 - index


def fit_prefs_window(scratch: Path, frame: dict[str, int]) -> int:
    """Height the window needs for its page plus {data}`PREFERENCES_FOOT` below it.

    Measured on the window as grown to {data}`PREFERENCES_PROBE_HEIGHT`: a
    one-pixel-wide strip down its middle is photographed, and the blank band
    under the last card is what the probe height exceeds the page by.
    """
    strip = scratch / "preferences-strip.png"
    screenshot_area(
        frame["x"] + frame["width"] // 2,
        frame["y"],
        1,
        frame["height"],
        strip,
    )
    foot = measure_page_foot(strip)
    wanted = PREFERENCES_FOOT * MONITOR_SCALE
    if foot < wanted:
        msg = (
            f"The preferences page overflows the {frame['height']}px window: "
            f"{foot} device rows of bare page at its foot, {wanted} wanted. "
            "Raise PREFERENCES_PROBE_HEIGHT."
        )
        raise RuntimeError(msg)
    return frame["height"] - (foot - wanted) // MONITOR_SCALE


def prefs_window_probe() -> str:
    """JS locating the preferences window, focusing it, and measuring it.

    Searches every window rather than reading the focused one: a freshly mapped
    window on a session nobody is driving does not reliably take focus, and
    `ScreenshotWindow` photographs whichever window holds it. Matching on the
    title first and activating it second makes the shutter's subject explicit
    instead of assumed.
    """
    return js("""(() => {
    const windows = global.display.list_all_windows();
    const match = windows.find(w => (w.get_title() || '').includes(NAME));
    if (!match)
        return null;
    match.activate(global.get_current_time());
    const frame = match.get_frame_rect();
    return {title: match.get_title(), width: frame.width, height: frame.height};
})()""").replace("NAME", repr(extension_name()))


def extension_name() -> str:
    """The extension's display name, which is what titles its window."""
    metadata = json.loads(
        (EXTENSION_DIR / "metadata.json").read_text(encoding="UTF-8"),
    )
    return str(metadata["name"])


def screenshot_window(target: Path) -> None:
    """Capture the focused window through the shell's screenshot service."""
    reply = gdbus_call(
        "/org/gnome/Shell/Screenshot",
        "org.gnome.Shell.Screenshot.ScreenshotWindow",
        "true",
        "false",
        "false",
        str(target),
    )
    if not reply.stdout.startswith("(true,"):
        focused = shell_eval(FOCUSED_TITLE)
        msg = (
            f"Window screenshot refused: {reply.stdout.strip()}, "
            f"with {focused!r} holding focus"
        )
        raise RuntimeError(msg)


def png_size(target: Path) -> tuple[int, int]:
    """Read a PNG's pixel dimensions straight out of its header."""
    header = target.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        msg = f"Not a PNG: {target}"
        raise ValueError(msg)
    width, height = struct.unpack(">II", header[16:24])
    return width, height


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
        "--wayland-display",
        WAYLAND_DISPLAY,
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
            publish_activation_environment()
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


def capture(shot: Shot, scratch: Path, schema_dir: Path) -> None:
    """Boot a session shaped by one shot and photograph its subject."""
    print(f"Capturing {shot.path.name}")
    gsettings(
        "org.gnome.desktop.interface",
        "color-scheme",
        gvariant("prefer-dark" if shot.dark else "prefer-light"),
    )
    if shot.preferences:
        capture_preferences(shot, scratch, schema_dir)
    else:
        capture_menu(shot, scratch, schema_dir)


def capture_preferences(shot: Shot, scratch: Path, schema_dir: Path) -> None:
    """Photograph the preferences window, on the schema's own defaults.

    The window renders the settings themselves, so it cannot open on the values
    the menu shots set for their own convenience: a `boot-wait` dropped to its
    floor and a `check-interval` pushed to its ceiling would be published as the
    defaults they are not.
    """
    run(
        ("gsettings", "reset-recursively", SCHEMA_ID),
        env=os.environ | {"GSETTINGS_SCHEMA_DIR": str(schema_dir)},
    )
    # The window is a libadwaita process of its own, and the shell's appearance
    # reaches such a process through the settings portal, which a session this
    # bare does not run: without this it renders light whatever the desktop
    # says, and the two captures come back byte-identical.
    os.environ["ADW_DEBUG_COLOR_SCHEME"] = (
        "prefer-dark" if shot.dark else "prefer-light"
    )
    with shell_session(scratch / f"{shot.stem}.log"):
        apply_monitor_scale()
        # The shell claims its bus name before it has finished loading
        # extensions, and asking for the preferences of one it does not know yet
        # is indistinguishable from one that has none.
        wait_until(
            lambda: shell_eval(EXTENSION_LOADED) is not None,
            REPORT_TIMEOUT,
            "the shell to load the extension",
        )
        loaded = shell_eval(EXTENSION_LOADED)
        if not isinstance(loaded, dict) or not loaded["hasPrefs"]:
            msg = f"The shell reports no preferences for {EXTENSION_UUID}: {loaded}"
            raise RuntimeError(msg)

        # The call the menu's own Settings row makes, rather than the CLI
        # wrapping it: the shell forwards this to the window host, and a failure
        # comes back as a D-Bus error naming its cause instead of an exit code.
        gdbus_call(
            "/org/gnome/Shell",
            "org.gnome.Shell.Extensions.OpenExtensionPrefs",
            EXTENSION_UUID,
            "",
            "{}",
        )
        probe = prefs_window_probe()
        wait_until(
            lambda: shell_eval(probe) is not None,
            REPORT_TIMEOUT,
            "the preferences window to appear",
        )
        window = grow_prefs_to(PREFERENCES_PROBE_HEIGHT)

        # Mapped and activated is not yet focused: a window found the instant it
        # appears takes a moment to receive focus, and the shutter needs it.
        name = extension_name()
        wait_until(
            lambda: name in str(shell_eval(FOCUSED_TITLE) or ""),
            REPORT_TIMEOUT,
            "the preferences window to take focus",
        )
        # Focused, but its first frame still has to land.
        time.sleep(1)
        # Taller than the page by a margin, then fitted to it: the page's own
        # height is what the frame should show, and only a capture can tell it.
        window = grow_prefs_to(fit_prefs_window(scratch, window))
        # Shrunk, and the page has to lay itself out again in the new height.
        time.sleep(1)
        fresh = scratch / f"{shot.stem}.capture.png"
        screenshot_window(fresh)

        # The HiDPI guard of the menu shots, as a floor rather than an equality:
        # what a window capture includes and what `get_frame_rect` reports need
        # not agree to the pixel, but a session that lost its scale cannot clear
        # the floor.
        captured = png_size(fresh)
        if captured[0] < window["width"] * MONITOR_SCALE:
            msg = f"{shot.path.name} came out {captured}, below {MONITOR_SCALE}x"
            raise RuntimeError(msg)
        settle_frame(fresh, shot.path)


def capture_menu(shot: Shot, scratch: Path, schema_dir: Path) -> None:
    """Photograph the indicator menu, in the layout the shot asks for."""
    marker = scratch / "outdated-served"
    marker.unlink(missing_ok=True)
    gsettings(
        SCHEMA_ID,
        "group-by-manager",
        "true" if shot.group_by_manager else "false",
        schema_dir=schema_dir,
    )
    gsettings(
        SCHEMA_ID,
        "align-columns",
        "true" if shot.align_columns else "false",
        schema_dir=schema_dir,
    )

    with shell_session(scratch / f"{shot.stem}.log"):
        apply_monitor_scale()
        wait_until(marker.exists, REPORT_TIMEOUT, "the extension's first check")
        # The report lands one turn of the loop after the payload is served.
        wait_until(
            lambda: bool(shell_eval(REPORT_ITEM_COUNT)),
            REPORT_TIMEOUT,
            "the menu to be populated",
        )
        shell_eval(HIDE_CLOCK)
        pinned = shell_eval(PIN_LAST_CHECK)
        if PINNED_LAST_CHECK not in str(pinned):
            msg = f"Last-checked row not pinned, it reads {pinned!r}"
            raise RuntimeError(msg)
        shell_eval(OPEN_MENU)
        # The menu opens unanimated, but still needs a frame to lay out.
        time.sleep(1)
        if shot.group_by_manager:
            if not shell_eval(EXPAND_FIRST_SECTION):
                msg = f"{shot.stem}: the grouped menu holds no section to unfold"
                raise RuntimeError(msg)
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
        fresh = scratch / f"{shot.stem}.capture.png"
        screenshot_area(left, 0, right - left, bottom, fresh)

        # The area is requested in logical pixels and must come back drawn in
        # device ones. A capture that matches the request one for one means the
        # session lost its scale, and the images would silently go back to 1x.
        expected = ((right - left) * MONITOR_SCALE, bottom * MONITOR_SCALE)
        captured = png_size(fresh)
        if captured != expected:
            msg = f"{shot.path.name} came out {captured}, expected {expected}"
            raise RuntimeError(msg)
        settle_frame(fresh, shot.path)


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
            # Claimed here rather than read back off the session: the shell is
            # told to host this socket name, so both halves agree by construction.
            "WAYLAND_DISPLAY": WAYLAND_DISPLAY,
            "GDK_BACKEND": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
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

        # A shot that differs in its settings has to differ in its pixels. Two
        # identical files mean a setting never reached its subject, which is
        # silent by construction: the preferences window rendered light in both
        # appearances that way, and only the file sizes gave it away.
        digests: dict[str, Shot] = {}
        for shot in SHOTS:
            print(
                f"{shot.path.relative_to(PROJECT_ROOT)}: "
                f"{shot.path.stat().st_size} bytes"
            )
            digest = hashlib.sha256(shot.path.read_bytes()).hexdigest()
            twin = digests.get(digest)
            if twin is not None:
                msg = f"{shot.stem} and {twin.stem} came out byte-identical"
                raise RuntimeError(msg)
            digests[digest] = shot


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
