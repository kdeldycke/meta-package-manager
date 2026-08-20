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

SWIFTBAR_URL = (
    "https://github.com/swiftbar/SwiftBar/releases/download/v2.1.1/"
    "SwiftBar.v2.1.1.b597.zip"
)
"""SwiftBar publishes a plain zip, which is what keeps this off a registry with
no cooldown knob: a pinned URL and a digest are both guarantees a cask is not.
"""

SWIFTBAR_SHA256 = "fcdec490782d6587046304044951c63de49ac422fc63892a6fab2dd7bc70c0cd"

SWIFTBAR_DOMAIN = "com.ameba.SwiftBar"

LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Frameworks"
    + "/LaunchServices.framework/Support/lsregister"
)
"""Launch Services' own registrar, which has never seen a bundle unpacked a
second ago: without it `open -a SwiftBar` cannot resolve the name.
"""

DISPLAY_MODE = (1600, 1200)
"""Tallest mode the hosted runner's virtual display offers.

Every mode it advertises has a backing store equal to its logical size, so a
HiDPI capture is not available and these images are `1x` where the GNOME ones
are `2x`. Height is what a menu runs out of, so the tallest mode is the one
worth having.
"""

MENU_TIMEOUT = 60
"""Seconds allowed for SwiftBar to render a plugin and open its menu."""


class Shot(NamedTuple):
    """One captured image: a file stem and the two variables that shape it."""

    stem: str
    submenu_layout: bool
    table_rendering: bool

    @property
    def path(self) -> Path:
        """Destination of the capture, under `docs/assets/`."""
        return ASSET_DIR / f"{self.stem}.png"

    @property
    def variables(self) -> dict[str, str]:
        """The plugin variables this shot documents, as the host passes them."""
        return {
            "VAR_SUBMENU_LAYOUT": str(self.submenu_layout).lower(),
            "VAR_TABLE_RENDERING": str(self.table_rendering).lower(),
        }


SHOTS = (
    Shot("swiftbar-flatmenu-standard-rendering", False, False),
    Shot("swiftbar-flatmenu-table-rendering", False, True),
    Shot("swiftbar-submenu-standard-rendering", True, False),
    Shot("swiftbar-submenu-table-rendering", True, True),
)
"""The matrix the plugin's page documents: both layout switches, in both states.

The two `standard-rendering` stems drop the `strandard` typo the hand-made
screenshots carried.
"""

CHROME_ITEM = "SwiftBar"
"""Title of the first menu row belonging to the host rather than to the plugin.

Everything from it down is SwiftBar's own chrome, including an *Updated N
Seconds Ago* line that would rewrite every image on every run. The captures are
cropped above it, which drops a per-run clock and leaves the subject the menu
the plugin actually produced.
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


def install_swiftbar() -> Path:
    """Fetch, verify and unpack SwiftBar into `/Applications`.

    Registered with Launch Services on the way past: a bundle that appeared
    seconds ago is unknown to it, so `open -a SwiftBar` cannot resolve the name.
    """
    app = Path("/Applications/SwiftBar.app")
    if app.exists():
        return app
    with TemporaryDirectory(prefix="mpm-swiftbar-") as name:
        archive = Path(name) / "swiftbar.zip"
        with urllib.request.urlopen(SWIFTBAR_URL) as response:
            archive.write_bytes(response.read())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != SWIFTBAR_SHA256:
            msg = f"SwiftBar digest is {digest}, expected {SWIFTBAR_SHA256}"
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
    """Render this shot's menu and plant it as the plugin SwiftBar runs.

    The plugin prints a payload rendered ahead of time rather than calling `mpm`:
    the subject is the menu, and a plugin that shells out would photograph
    whatever the runner happened to have outdated.
    """
    payload = json.loads(FIXTURE.read_text(encoding="UTF-8"))
    environment = dict(os.environ)
    environment.update(shot.variables)
    # The plugin runs under SwiftBar, so the renderer has to believe it does too.
    environment["SWIFTBAR"] = "1"
    environment["SWIFTBAR_VERSION"] = "2.1.1"
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment)
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


def refresh_plugins() -> None:
    """Ask SwiftBar to re-run every plugin, through its own URL scheme."""
    run(("open", "-g", "swiftbar://refreshallplugins"), check=False)


def status_item_centre() -> tuple[float, float]:
    """Screen coordinates of SwiftBar's status item.

    `menu bar 1`, not 2: an agent app has no app menu, so its status bar is the
    only menu bar it owns.
    """
    reply = osascript("""
tell application "System Events"
    tell process "SwiftBar"
        set theItem to menu bar item 1 of menu bar 1
        set {itemX, itemY} to position of theItem
        set {itemW, itemH} to size of theItem
        return ((itemX + itemW / 2) as string) & " " & ((itemY + itemH / 2) as string)
    end tell
end tell
""")
    left, top = reply.split()
    return float(left), float(top)


def click(left: float, top: float) -> None:
    """Post a real left click at a screen position."""
    print(
        swift(
            """
        import CoreGraphics
        import Foundation
        let point = CGPoint(x: Double(CommandLine.arguments[1]) ?? 0,
                            y: Double(CommandLine.arguments[2]) ?? 0)
        let source = CGEventSource(stateID: .hidSystemState)
        let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown,
                           mouseCursorPosition: point, mouseButton: .left)
        let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp,
                         mouseCursorPosition: point, mouseButton: .left)
        down?.post(tap: .cghidEventTap)
        usleep(120000)
        up?.post(tap: .cghidEventTap)
        print("clicked \\(point.x),\\(point.y)")
        """,
            str(left),
            str(top),
        )
    )


def menu_window() -> dict[str, float] | None:
    """The open menu's window id and bounds, or `None` while none is open.

    A menu is a window of the app that owns it, on the pop-up layer.
    """
    reply = osascript(
        """
ObjC.import("CoreGraphics");
ObjC.import("Foundation");
const raw = $.CGWindowListCopyWindowInfo(17, 0);
const list = ObjC.castRefToObject(raw);
for (let i = 0; i < list.count; i++) {
    const w = list.objectAtIndex(i);
    const owner = ObjC.unwrap(w.objectForKey("kCGWindowOwnerName"));
    const layer = ObjC.unwrap(w.objectForKey("kCGWindowLayer"));
    if (owner === "SwiftBar" && layer >= 101) {
        const bounds = ObjC.deepUnwrap(w.objectForKey("kCGWindowBounds"));
        JSON.stringify({
            id: ObjC.unwrap(w.objectForKey("kCGWindowNumber")),
            x: bounds.X, y: bounds.Y, width: bounds.Width, height: bounds.Height,
        });
        break;
    }
}
""",
        language="JXA",
    )
    return json.loads(reply) if reply.startswith("{") else None


def chrome_top() -> float | None:
    """Vertical position of the first row belonging to SwiftBar, not the plugin.

    Read from the accessibility tree rather than measured off the image, so a
    menu of any length crops at the right place.
    """
    reply = osascript(f"""
tell application "System Events"
    tell process "SwiftBar"
        set theMenu to menu 1 of menu bar item 1 of menu bar 1
        repeat with theRow in menu items of theMenu
            try
                if (name of theRow) is "{CHROME_ITEM}" then
                    set {{rowX, rowY}} to position of theRow
                    return rowY as string
                end if
            end try
        end repeat
        return "none"
    end tell
end tell
""")
    return None if reply == "none" else float(reply)


def capture(shot: Shot, plugins: Path) -> None:
    """Render one shot's menu, open it, and photograph the plugin's half."""
    print(f"Capturing {shot.path.name}")
    write_plugin(plugins, shot)
    refresh_plugins()
    time.sleep(6)

    left, top = status_item_centre()
    click(left, top)

    deadline = time.monotonic() + MENU_TIMEOUT
    window = None
    while time.monotonic() < deadline:
        window = menu_window()
        if window is not None:
            break
        time.sleep(0.5)
    if window is None:
        msg = f"{shot.stem}: no menu window opened"
        raise RuntimeError(msg)

    # Crop above SwiftBar's own rows: they carry an *Updated N Seconds Ago*
    # clock, and an image that changes every run opens a pull request every run.
    height = window["height"]
    chrome = chrome_top()
    if chrome is not None:
        height = max(1.0, chrome - window["y"] - 1)
    rect = f"{window['x']},{window['y']},{window['width']},{height}"
    run(("screencapture", "-x", "-o", "-t", "png", "-R", rect, str(shot.path)))

    # Dismiss the menu so the next shot starts from a bare desktop.
    osascript('tell application "System Events" to key code 53')
    time.sleep(1)
    print(f"  {shot.path.name}: {png_size(shot.path)}")


def capture_all() -> None:
    """Install SwiftBar, point it at a scratch plugin folder, and shoot."""
    if sys.platform != "darwin":
        sys.exit("These captures need macOS, and a SwiftBar to drive.")
    install_swiftbar()
    raise_display()

    with TemporaryDirectory(prefix="mpm-bar-capture-") as name:
        plugins = Path(name) / "plugins"
        plugins.mkdir(parents=True)
        # Remembered so a local run gives the developer their own plugins back.
        previous = run(
            ("defaults", "read", SWIFTBAR_DOMAIN, "PluginDirectory"),
            check=False,
        ).stdout.strip()
        run(("defaults", "write", SWIFTBAR_DOMAIN, "PluginDirectory", str(plugins)))
        try:
            write_plugin(plugins, SHOTS[0])
            run(("open", "/Applications/SwiftBar.app"))
            time.sleep(20)
            spend_consent_prompt()

            ASSET_DIR.mkdir(parents=True, exist_ok=True)
            digests: dict[str, Shot] = {}
            for shot in SHOTS:
                capture(shot, plugins)
                digest = hashlib.sha256(shot.path.read_bytes()).hexdigest()
                twin = digests.get(digest)
                if twin is not None:
                    msg = f"{shot.stem} and {twin.stem} came out byte-identical"
                    raise RuntimeError(msg)
                digests[digest] = shot
        finally:
            run(("osascript", "-e", 'tell application "SwiftBar" to quit'), check=False)
            if previous:
                run(
                    ("defaults", "write", SWIFTBAR_DOMAIN, "PluginDirectory", previous),
                    check=False,
                )
            else:
                run(
                    ("defaults", "delete", SWIFTBAR_DOMAIN, "PluginDirectory"),
                    check=False,
                )


def main() -> None:
    """Capture every shot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    capture_all()


if __name__ == "__main__":
    main()
