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

"""Capture the Xbar/SwiftBar plugin's menu from a real SwiftBar.

The macOS counterpart of `docs/gnome_screenshots_update.py`, and the same
bargain: a real host renders the real plugin, and only the package data is held
still. SwiftBar is installed from a pinned, checksummed release zip, fed a
plugin that prints what {class}`~meta_package_manager.bar_plugin_renderer.BarPluginRenderer`
renders from {data}`FIXTURE`, and its menu is opened and photographed by window
id.

Driven by `.github/workflows/docs-screenshots.yaml`. A local run works the same
way, on any Mac, and leaves the machine's own SwiftBar configuration alone:

```shell-session
$ uv run --frozen -- python docs/bar_screenshots_update.py
```

```{caution}
A status item is opened with a **real mouse event**, not an accessibility press.
`AXPress` and System Events' `click` both leave the item reporting no menu at
all: SwiftBar tells a plain click from an option-click, so it handles `mouseDown`
itself and a synthetic press never reaches that code. `click` is doubly wrong,
its release dismissing the menu the way a second click would.
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from meta_package_manager.bar_plugin_renderer import BarPluginRenderer

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping

PROJECT_ROOT = Path(__file__).parent.parent

FIXTURE = PROJECT_ROOT / "docs" / "outdated-sample.json"
"""The payload the GNOME captures render too, so both frontends document one
inventory and a reader comparing the two pages sees the same packages.
"""

ASSET_DIR = PROJECT_ROOT / "docs" / "assets"


class Host(NamedTuple):
    """One bar app the plugin is photographed inside."""

    name: str
    """Display name, and the process name the accessibility API answers to."""

    url: str
    """Release archive. Both projects publish a plain zip, which is what keeps
    this off a registry with no cooldown knob: a pinned URL and a digest are two
    guarantees a cask offers neither of.
    """

    sha256: str

    bundle: str
    """Basename of the application bundle inside the archive."""

    environment: dict[str, str]
    """What the host sets for its plugins, and what the renderer keys its dialect
    off. SwiftBar announces itself; Xbar says nothing, which is how
    {meth}`~meta_package_manager.bar_plugin.MPMPlugin.is_swiftbar` tells them
    apart.
    """

    chrome_item: str | None
    """Title of the first menu row belonging to the host rather than the plugin,
    or `None` when its rows are worth keeping.

    SwiftBar's footer carries an *Updated N Seconds Ago* clock that would rewrite
    every image on every run, so its captures stop above it. Xbar's footer is a
    single static `xbar` row, which costs nothing to keep.
    """

    plugin_dir: Path | None
    """Where the host reads plugins from, or `None` when it is told at runtime.

    SwiftBar takes a folder from its own preferences, so the captures point it at
    a scratch one and put the developer's back afterwards. Xbar hardcodes
    `~/Library/Application Support/xbar/plugins`, so its plugin is planted there
    and removed again.
    """


SWIFTBAR = Host(
    name="SwiftBar",
    url=(
        "https://github.com/swiftbar/SwiftBar/releases/download/v2.1.1/"
        "SwiftBar.v2.1.1.b597.zip"
    ),
    sha256="fcdec490782d6587046304044951c63de49ac422fc63892a6fab2dd7bc70c0cd",
    bundle="SwiftBar.app",
    environment={"SWIFTBAR": "1", "SWIFTBAR_VERSION": "2.1.1"},
    chrome_item="SwiftBar",
    plugin_dir=None,
)

XBAR = Host(
    name="xbar",
    url=(
        "https://github.com/matryer/xbar/releases/download/v2.1.7-beta/"
        "xbar.v2.1.7-beta.zip"
    ),
    sha256="60e595a2bc15d831a1b118e1940c4f2e91ac4fd0d22039282dc0b6d369e41bbe",
    bundle="xbar.app",
    environment={},
    chrome_item=None,
    plugin_dir=Path.home() / "Library/Application Support/xbar/plugins",
)

SWIFTBAR_DOMAIN = "com.ameba.SwiftBar"

LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks"
    + "/LaunchServices.framework/Support/lsregister"
)
"""Launch Services' own registrar, which has never seen a bundle unpacked a
second ago: without it `open -a <name>` cannot resolve the name.
"""

DISPLAY_MODE = (1600, 1200)
"""Tallest mode the hosted runner's virtual display offers.

Every mode it advertises has a backing store equal to its logical size, so a
HiDPI capture is not available and these images are `1x` where the GNOME ones
are `2x`. Height is what a menu runs out of, so the tallest mode is the one
worth having.
"""

MENU_MARKER = "🎁"
"""Marker the plugin's own status item carries when packages are outdated.

Used to pick our item out of a menu bar that, on a developer's own Mac, holds
whatever other plugins they run.
"""

FIRST_ROW = (40, 15)
"""Offset from a menu's top-left corner into its first row.

Reckoned rather than asked for, on the one host whose accessibility tree answers
nothing. A menu's first row is at its top, and this only has to land inside it.
"""

MENU_TIMEOUT = 60
"""Seconds allowed for SwiftBar to render a plugin and open its menu."""


class Shot(NamedTuple):
    """One captured image: a host, the two plugin variables, and an appearance."""

    host: Host
    submenu_layout: bool
    table_rendering: bool
    dark: bool

    @property
    def stem(self) -> str:
        """File stem, naming every axis that shapes the image."""
        return "-".join((
            self.host.name.lower(),
            "submenu" if self.submenu_layout else "flatmenu",
            "table" if self.table_rendering else "standard",
            "rendering",
            "dark" if self.dark else "light",
        ))

    @property
    def path(self) -> Path:
        """Destination of the capture, under `docs/assets/`."""
        return ASSET_DIR / f"{self.stem}.png"

    @property
    def environment(self) -> dict[str, str]:
        """What the host would set for the plugin producing this menu.

        `OS_APPEARANCE` is set here rather than inherited because the menu is
        rendered ahead of time: SwiftBar passes it to a plugin it runs itself,
        and the renderer picks its version-diff colors from it.
        """
        return {
            **self.host.environment,
            "VAR_SUBMENU_LAYOUT": str(self.submenu_layout).lower(),
            "VAR_TABLE_RENDERING": str(self.table_rendering).lower(),
            "OS_APPEARANCE": "Dark" if self.dark else "Light",
        }


SHOTS = tuple(
    Shot(host, submenu, table, dark)
    for host in (SWIFTBAR, XBAR)
    for submenu in (False, True)
    for table in (False, True)
    for dark in (False, True)
)
"""Every combination the plugin's page documents.

Both hosts, both layout switches, and both system appearances: the appearance is
worth an axis of its own because the version diff has to stay legible on each,
which is what {meth}`~meta_package_manager.bar_plugin_renderer.BarPluginRenderer.menu_diff_colors`
picks its palette for.
"""


def run(
    argv: tuple[str, ...],
    *,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing its output as text.

    A failure carries the message the command printed to explain it, which the
    default {exc}`~subprocess.CalledProcessError` drops.
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


def bounded(script: str, seconds: int = 15) -> str:
    """Wrap an AppleScript body in an AppleEvent timeout.

    The default is a minute of silence before `-1712`, which is a long time to
    spend discovering that a host is not answering yet.
    """
    return f"with timeout of {seconds} seconds\n{script}\nend timeout"


def describe(host: Host) -> str:
    """What System Events can see of a host, for a failure worth diagnosing."""
    return osascript(
        bounded(f"""
tell application "System Events"
    try
        tell process "{host.name}"
            return "menu bars: " & (count of menu bars) & ¬
                ", windows: " & (count of windows)
        end tell
    on error message
        return "unreachable: " & message
    end try
end tell
""")
    )


def osascript(source: str, *, language: str = "AppleScript") -> str:
    """Run a script through `osascript`, from a file rather than `-e`.

    A continuation backslash inside a quoted `-e` argument reaches osascript
    verbatim and kills the whole script, so every snippet here travels as a file.
    """
    with TemporaryDirectory(prefix="mpm-osascript-") as name:
        script = Path(name) / "snippet"
        script.write_text(source, encoding="UTF-8")
        argv = ("osascript", *(("-l", "JavaScript") if language == "JXA" else ()))
        return run((*argv, str(script))).stdout.strip()


def swift(source: str, *args: str) -> str:
    """Compile and run a Swift snippet, for the CoreGraphics calls."""
    with TemporaryDirectory(prefix="mpm-swift-") as name:
        script = Path(name) / "snippet.swift"
        script.write_text(source, encoding="UTF-8")
        return run(("swift", str(script), *args)).stdout.strip()


def png_size(target: Path) -> tuple[int, int]:
    """Read a PNG's pixel dimensions straight out of its header."""
    header = target.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        msg = f"Not a PNG: {target}"
        raise ValueError(msg)
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def install(host: Host) -> Path:
    """Fetch, verify and unpack a host into `/Applications`.

    Registered with Launch Services on the way past: a bundle that appeared
    seconds ago is unknown to it, so `open -a <name>` cannot resolve the name.
    """
    app = Path("/Applications") / host.bundle
    if app.exists():
        return app
    with TemporaryDirectory(prefix="mpm-host-") as name:
        archive = Path(name) / "host.zip"
        with urllib.request.urlopen(host.url) as response:
            archive.write_bytes(response.read())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != host.sha256:
            msg = f"{host.name} digest is {digest}, expected {host.sha256}"
            raise RuntimeError(msg)
        run(("ditto", "-x", "-k", str(archive), "/Applications"))
    run(("xattr", "-dr", "com.apple.quarantine", str(app)), check=False)
    run((LSREGISTER, "-f", str(app)), check=False)
    return app


def raise_display() -> None:
    """Switch the main display to {data}`DISPLAY_MODE`."""
    print(
        swift(
            """
        import CoreGraphics
        let display = CGMainDisplayID()
        let modes = CGDisplayCopyAllDisplayModes(display, nil) as? [CGDisplayMode]
        let wanted = (modes ?? []).first {
            $0.width == Int(CommandLine.arguments[1])!
                && $0.height == Int(CommandLine.arguments[2])!
        }
        guard let mode = wanted else { exit(2) }
        var config: CGDisplayConfigRef?
        CGBeginDisplayConfiguration(&config)
        CGConfigureDisplayWithDisplayMode(config, display, mode, nil)
        CGCompleteDisplayConfiguration(config, .permanently)
        print("display set to \\(mode.width)x\\(mode.height)")
        """,
            str(DISPLAY_MODE[0]),
            str(DISPLAY_MODE[1]),
        )
    )


def set_appearance(*, dark: bool) -> None:
    """Put the whole system into light or dark mode.

    The menu itself is drawn by the host, so its background, separators and
    label colors come from the system appearance rather than from anything the
    plugin emits. Only the version diff is ours, and it keys off `OS_APPEARANCE`.
    """
    osascript(f"""
tell application "System Events"
    tell appearance preferences
        set dark mode to {"true" if dark else "false"}
    end tell
end tell
""")
    time.sleep(3)


def spend_consent_prompt() -> None:
    """Trigger macOS's screen-recording consent sheet, then dismiss it.

    It is raised by the *first* capture, belongs to `UserNotificationCenter`
    rather than to whatever triggered it, and arrives a few seconds later. Left
    up it sits over everything, landing in the frame and swallowing clicks.
    """
    with TemporaryDirectory(prefix="mpm-consent-") as name:
        run(
            ("screencapture", "-x", "-t", "png", str(Path(name) / "warmup.png")),
            check=False,
        )
    for attempt in range(1, 6):
        found = osascript("""
tell application "System Events"
    set theCount to 0
    try
        tell process "UserNotificationCenter"
            set theCount to count of windows
            repeat with theWindow in windows
                try
                    click button "Allow" of theWindow
                end try
            end repeat
        end tell
    end try
    return theCount
end tell
""")
        print(f"consent sheet, attempt {attempt}: {found} window(s)")
        time.sleep(4)


def write_plugin(plugins: Path, shot: Shot) -> None:
    """Render this shot's menu and plant it as the plugin the host runs.

    The plugin prints a payload rendered ahead of time rather than calling `mpm`:
    the subject is the menu, and a plugin that shells out would photograph
    whatever the runner happened to have outdated.
    """
    payload = json.loads(FIXTURE.read_text(encoding="UTF-8"))
    previous = dict(os.environ)
    os.environ.update(shot.environment)
    # SwiftBar announces itself through the environment; Xbar says nothing, so
    # anything left over from a SwiftBar shot would put the renderer in the
    # wrong dialect.
    if not shot.host.environment:
        for key in ("SWIFTBAR", "SWIFTBAR_VERSION"):
            os.environ.pop(key, None)
    try:
        renderer = BarPluginRenderer()
        # A recorded `mpm outdated` payload carries no upgrade commands: those
        # are the plugin dialect's own, derived per manager from what it
        # implements, and `mpm outdated --plugin-output` adds them on the way
        # out. Rendering without them raises `KeyError: 'upgrade_cli'`.
        menu = renderer.render(renderer.add_upgrade_cli(payload))
    finally:
        os.environ.clear()
        os.environ.update(previous)

    script = plugins / "mpm.1h.sh"
    body = "#!/bin/bash\ncat <<'MENU'\n" + menu.rstrip("\n") + "\nMENU\n"
    script.write_text(body, encoding="UTF-8")
    script.chmod(0o755)


def restart(host: Host, plugins: Path) -> None:
    """Bring the host back up on whatever the plugin folder now holds.

    A restart rather than a refresh call, because the two hosts refresh
    differently and one of them has to be restarted anyway for a system
    appearance change to reach its menu.
    """
    run(("osascript", "-e", f'tell application "{host.name}" to quit'), check=False)
    time.sleep(3)
    if host.plugin_dir is None:
        run(("defaults", "write", SWIFTBAR_DOMAIN, "PluginDirectory", str(plugins)))
    run(("open", str(Path("/Applications") / host.bundle)))
    time.sleep(20)
    # Xbar greets a first run with its plugin browser, which sits in front of
    # the menu bar and leaves the process too busy to answer accessibility.
    osascript(
        bounded(f"""
tell application "System Events"
    try
        tell process "{host.name}"
            repeat with theWindow in windows
                try
                    click button 1 of theWindow
                end try
            end repeat
        end tell
    end try
end tell
""")
    )
    time.sleep(3)


def owned_windows(host: Host, low: int, high: int) -> list[dict[str, float]]:
    """Bounds of the host's windows within a layer range, from the window server.

    The one interface both hosts answer. Xbar serves no accessibility tree at
    all: `count of menu bars` on its process times out with `-1712`, not with an
    empty answer, however long it is given and however many times it is asked.
    Its status item and its menus are windows all the same, and windows are
    something the window server will happily describe.
    """
    reply = osascript(
        """
ObjC.import("CoreGraphics");
ObjC.import("Foundation");
const raw = $.CGWindowListCopyWindowInfo(17, 0);
const list = ObjC.castRefToObject(raw);
const boxes = [];
for (let i = 0; i < list.count; i++) {
    const w = list.objectAtIndex(i);
    const owner = ObjC.unwrap(w.objectForKey("kCGWindowOwnerName"));
    const layer = ObjC.unwrap(w.objectForKey("kCGWindowLayer"));
    if (owner === "HOST" && layer >= LOW && layer <= HIGH) {
        const b = ObjC.deepUnwrap(w.objectForKey("kCGWindowBounds"));
        boxes.push({x: b.X, y: b.Y, width: b.Width, height: b.Height});
    }
}
JSON.stringify(boxes);
"""
        .replace("HOST", host.name)
        .replace("LOW", str(low))
        .replace("HIGH", str(high)),
        language="JXA",
    )
    boxes: list[dict[str, float]] = json.loads(reply)
    return boxes


_STATUS_ITEM = """
tell application "System Events"
    tell process "HOST"
        set theBar to menu bar (count of menu bars)
        repeat with theItem in menu bar items of theBar
            try
                if (name of theItem) contains "MARKER" then
                    set {itemX, itemY} to position of theItem
                    set {itemW, itemH} to size of theItem
                    return ((itemX + itemW / 2) as string) & " " & ((itemY + itemH / 2) as string)
                end if
            end try
        end repeat
        return "none"
    end tell
end tell
"""
"""Locates the plugin's own status item and returns its centre.

Matched on the title rather than taken as item 1: a developer running this
locally has other plugins, and each of them owns a status item too. The last
menu bar is the status bar, an agent app having no app menu of its own.
"""

STATUS_ITEM_INSET = 30
"""Pixels left of the leftmost system status item to aim at.

Half the width of the plugin's own item, near enough. Only Xbar needs it: with
one bar app running, its item is the first thing to the left of the system ones.
"""


def system_items() -> list[dict[str, float]]:
    """Bounds of the status items macOS draws for itself."""
    reply = osascript(
        """
ObjC.import("CoreGraphics");
ObjC.import("Foundation");
const raw = $.CGWindowListCopyWindowInfo(17, 0);
const list = ObjC.castRefToObject(raw);
const boxes = [];
for (let i = 0; i < list.count; i++) {
    const w = list.objectAtIndex(i);
    const layer = ObjC.unwrap(w.objectForKey("kCGWindowLayer"));
    if (layer >= 20 && layer <= 30) {
        const b = ObjC.deepUnwrap(w.objectForKey("kCGWindowBounds"));
        if (b.Y < 40) {
            boxes.push({x: b.X, y: b.Y, width: b.Width, height: b.Height});
        }
    }
}
JSON.stringify(boxes);
""",
        language="JXA",
    )
    boxes: list[dict[str, float]] = json.loads(reply)
    return boxes


def status_item(host: Host) -> tuple[float, float]:
    """Screen coordinates of the plugin's status item.

    Two routes, because the hosts differ in what they answer. SwiftBar serves an
    accessibility tree, so its item is asked for by name. Xbar serves none at
    all: `count of menu bars` on its process times out with `-1712` however long
    it is given. And a status item is not a window either, the menu bar being
    drawn for an app rather than by it, so the window server cannot stand in.
    What it does list is the system's own items, and with a single bar app
    running the plugin's item is the first slot to their left.
    """
    if host is SWIFTBAR:
        script = bounded(
            _STATUS_ITEM.replace("HOST", host.name).replace("MARKER", MENU_MARKER),
        )
        for attempt in range(1, 13):
            reply = "none"
            try:
                reply = osascript(script)
            except RuntimeError as error:
                print(f"  {host.name} status item, attempt {attempt}: {error}")
            if reply != "none":
                left, top = reply.split()
                return float(left), float(top)
            time.sleep(5)
        msg = f"{host.name} shows no status item titled with {MENU_MARKER!r}"
        raise RuntimeError(msg)

    items = system_items()
    if not items:
        msg = "The menu bar lists no system status item to anchor on"
        raise RuntimeError(msg)
    anchor = min(items, key=lambda box: box["x"])
    return anchor["x"] - STATUS_ITEM_INSET, anchor["y"] + anchor["height"] / 2


def mouse(kind: str, left: float, top: float) -> None:
    """Post a real mouse event at a screen position.

    Real, not synthetic: a status item that tells a plain click from an
    option-click handles `mouseDown` itself, and an accessibility press never
    reaches that code.
    """
    print(
        swift(
            """
        import CoreGraphics
        import Foundation
        let kind = CommandLine.arguments[1]
        let point = CGPoint(x: Double(CommandLine.arguments[2]) ?? 0,
                            y: Double(CommandLine.arguments[3]) ?? 0)
        let source = CGEventSource(stateID: .hidSystemState)
        if kind == "move" {
            CGEvent(mouseEventSource: source, mouseType: .mouseMoved,
                    mouseCursorPosition: point, mouseButton: .left)?
                .post(tap: .cghidEventTap)
        } else {
            CGEvent(mouseEventSource: source, mouseType: .leftMouseDown,
                    mouseCursorPosition: point, mouseButton: .left)?
                .post(tap: .cghidEventTap)
            usleep(120000)
            CGEvent(mouseEventSource: source, mouseType: .leftMouseUp,
                    mouseCursorPosition: point, mouseButton: .left)?
                .post(tap: .cghidEventTap)
        }
        print("\\(kind) \\(point.x),\\(point.y)")
        """,
            kind,
            str(left),
            str(top),
        )
    )


def menu_bounds(host: Host) -> dict[str, float] | None:
    """Box enclosing every menu the host currently has open.

    A submenu is a window of its own, so a grouped layout with one group opened
    spans two: the union is what the capture has to cover.
    """
    boxes = owned_windows(host, 101, 10_000)
    if not boxes:
        return None
    return {
        "x": min(box["x"] for box in boxes),
        "y": min(box["y"] for box in boxes),
        "right": max(box["x"] + box["width"] for box in boxes),
        "bottom": max(box["y"] + box["height"] for box in boxes),
    }


def chrome_top(host: Host) -> float | None:
    """Vertical position of the first row belonging to the host, not the plugin.

    Read from the accessibility tree rather than measured off the image, so a
    menu of any length crops at the right place.
    """
    if host.chrome_item is None:
        return None
    reply = osascript(f"""
tell application "System Events"
    tell process "{host.name}"
        set theBar to menu bar (count of menu bars)
        repeat with theItem in menu bar items of theBar
            try
                repeat with theRow in menu items of menu 1 of theItem
                    try
                        if (name of theRow) is "{host.chrome_item}" then
                            set {{rowX, rowY}} to position of theRow
                            return rowY as string
                        end if
                    end try
                end repeat
            end try
        end repeat
        return "none"
    end tell
end tell
""")
    return None if reply == "none" else float(reply)


def expand_first_section(host: Host, bounds: dict[str, float]) -> None:
    """Open the first group of a grouped menu, however this host opens one.

    Without it the two grouped captures of a host come out byte-identical:
    everything `VAR_TABLE_RENDERING` decides sits inside a group, and the top
    level shows nothing but manager rows. SwiftBar `2.1` folds them into inline
    accordions a click expands in place; Xbar builds real submenus, which open
    on hover.

    SwiftBar's row is asked for by name; Xbar's is reckoned from the top-left of
    its menu, that being where a first row is and its accessibility tree
    answering nothing.
    """
    if host is SWIFTBAR:
        reply = osascript(
            bounded(f"""
tell application "System Events"
    tell process "{host.name}"
        set theBar to menu bar (count of menu bars)
        repeat with theItem in menu bar items of theBar
            try
                set theRow to menu item 1 of menu 1 of theItem
                set {{rowX, rowY}} to position of theRow
                set {{rowW, rowH}} to size of theRow
                return ((rowX + rowW / 2) as string) & " " & ((rowY + rowH / 2) as string)
            end try
        end repeat
        return "none"
    end tell
end tell
""")
        )
        if reply == "none":
            return
        left, top = (float(value) for value in reply.split())
        mouse("click", left, top)
    else:
        mouse("move", bounds["x"] + FIRST_ROW[0], bounds["y"] + FIRST_ROW[1])
    time.sleep(3)


def capture(shot: Shot, plugins: Path) -> None:
    """Render one shot's menu, open it, and photograph it."""
    print(f"Capturing {shot.path.name}")
    write_plugin(plugins, shot)
    restart(shot.host, plugins)

    mouse("click", *status_item(shot.host))
    deadline = time.monotonic() + MENU_TIMEOUT
    bounds = None
    while time.monotonic() < deadline:
        bounds = menu_bounds(shot.host)
        if bounds is not None:
            break
        time.sleep(0.5)
    if bounds is None:
        msg = f"{shot.stem}: no menu opened"
        raise RuntimeError(msg)

    if shot.submenu_layout:
        expand_first_section(shot.host, bounds)
        bounds = menu_bounds(shot.host)
        if bounds is None:
            msg = f"{shot.stem}: the menu closed while opening a group"
            raise RuntimeError(msg)

    bottom = bounds["bottom"]
    chrome = chrome_top(shot.host)
    if chrome is not None:
        bottom = min(bottom, chrome - 1)
    rect = (
        f"{bounds['x']},{bounds['y']},"
        f"{bounds['right'] - bounds['x']},{bottom - bounds['y']}"
    )
    run(("screencapture", "-x", "-o", "-t", "png", "-R", rect, str(shot.path)))

    # Dismiss the menu so the next shot starts from a bare desktop.
    osascript('tell application "System Events" to key code 53')
    time.sleep(1)
    print(f"  {shot.path.name}: {png_size(shot.path)}")


def capture_all() -> None:
    """Install both hosts, then walk every shot."""
    if sys.platform != "darwin":
        sys.exit("These captures need macOS, and a bar app to drive.")
    for host in (SWIFTBAR, XBAR):
        install(host)
    raise_display()
    spend_consent_prompt()

    with TemporaryDirectory(prefix="mpm-bar-capture-") as name:
        scratch = Path(name) / "plugins"
        scratch.mkdir(parents=True)
        # Remembered so a local run gives the developer their own plugins back.
        swiftbar_folder = run(
            ("defaults", "read", SWIFTBAR_DOMAIN, "PluginDirectory"),
            check=False,
        ).stdout.strip()
        planted: list[Path] = []
        appearance: bool | None = None
        try:
            ASSET_DIR.mkdir(parents=True, exist_ok=True)
            digests: dict[str, Shot] = {}
            for shot in SHOTS:
                if shot.dark != appearance:
                    set_appearance(dark=shot.dark)
                    appearance = shot.dark
                # Xbar hardcodes its folder, so its plugin is planted in the
                # real one and taken out again below.
                plugins = shot.host.plugin_dir or scratch
                plugins.mkdir(parents=True, exist_ok=True)
                if shot.host.plugin_dir is not None:
                    planted.append(plugins / "mpm.1h.sh")
                capture(shot, plugins)

                digest = hashlib.sha256(shot.path.read_bytes()).hexdigest()
                twin = digests.get(digest)
                if twin is not None:
                    msg = f"{shot.stem} and {twin.stem} came out byte-identical"
                    raise RuntimeError(msg)
                digests[digest] = shot
        finally:
            for host in (SWIFTBAR, XBAR):
                run(
                    ("osascript", "-e", f'tell application "{host.name}" to quit'),
                    check=False,
                )
            for leftover in planted:
                leftover.unlink(missing_ok=True)
            if swiftbar_folder:
                run(
                    (
                        "defaults",
                        "write",
                        SWIFTBAR_DOMAIN,
                        "PluginDirectory",
                        swiftbar_folder,
                    ),
                    check=False,
                )
            else:
                run(
                    ("defaults", "delete", SWIFTBAR_DOMAIN, "PluginDirectory"),
                    check=False,
                )
            set_appearance(dark=False)


def main() -> None:
    """Capture every shot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    capture_all()


if __name__ == "__main__":
    main()
