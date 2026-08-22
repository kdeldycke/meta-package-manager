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

"""Capture the SwiftBar/Xbar plugin's menu from a real SwiftBar.

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

    domain: str
    """Preferences domain, where the status item's position is recorded."""

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
    domain="com.ameba.SwiftBar",
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
    domain="com.matryer.xbar",
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

PLUGIN_NAME = "mpm.1h.sh"
"""Filename the plugin is planted under, which is also the name AppKit keys its
status item's remembered position by.
"""

MENU_MARKER = "🎁"
"""Marker the plugin's own status item carries when packages are outdated.

Used to pick our item out of a menu bar that, on a developer's own Mac, holds
whatever other plugins they run.
"""

STATUS_ITEM_POSITION = 700.0
"""Where the plugin's status item is asked to sit, in screen coordinates.

Left of where macOS would otherwise put it, and the reason is Xbar's submenus.
A menu opens under its item unless that would run off the right edge, in which
case it is pushed left until its right edge meets the screen's. From there a
submenu has nowhere to fly but leftwards, back over its own parent. Moving the
item left leaves room for the submenu to open to the right of the parent, which
is both the readable arrangement and the one a user with a fuller menu bar sees.
It also carries the menu clear of the clock, which is the other thing in that
strip nobody wants photographed.

Asked for through `NSStatusItem Preferred Position`, which AppKit maintains
itself for a status item whose owner gave it an autosave name. SwiftBar does,
and the name is the plugin's path, which is what {func}`position_keys` spells:
a machine running SwiftBar `2.1.1` carries both a path-keyed entry and an older
filename-keyed one, and writing the bare filename alone moved nothing (run
32444526285). A host that names its items differently, or not at all, ignores
the write, and the capture still finds the item wherever it landed.
"""

FIRST_ROW = (40, 15)
"""Offset from a menu's top-left corner into its first row.

Reckoned rather than asked for, on the one host whose accessibility tree answers
nothing. A menu's first row is at its top, and this only has to land inside it.
"""

CLOCK_PINNED = False
"""Whether the menu bar clock was made to read the same on every run, and so
whether the captures can reach up to include it.
"""

SYSTEM_ITEMS_EDGE: float | None = None
"""Left edge of the menu bar region macOS keeps for itself.

Measured before either host starts, so everything left of it afterwards is a
plugin's. That is what identifies Xbar's status item, which cannot be asked for
by name: the app answers no accessibility at all.
"""

CLOCK_STAMP: str | None = None
"""The reading the clock is held at, in the form `date` takes.

Computed once, and re-applied before every shot: pinning the clock stops it
being corrected, not being a clock. Left to tick, it drifted from `10:32` on
the first capture to `10:53` on the last, so every image carried a different
menu bar and the whole set churned anyway (run 32573216871).
"""

CLOCK_REPAINT_WAIT = 5
"""Seconds to wait for the menu bar clock to redraw after the time is set.

Long enough to cover the minute boundary {func}`hold_clock` lands just short
of, with the shot then taken well inside the minute that follows.
"""

CLOCK_TIME = (10, 30)
"""Hour and minute the menu bar clock is held at, in 24-hour form.

The same reading the GNOME captures pin their *Last checked* row to, so the two
sets of documentation screenshots agree on what time it is.
"""

DIAGNOSTICS: Path | None = None
"""Where a failed shot leaves its evidence, when a caller asks for any."""

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
    # Every host is quit first. A bar app holding a menu open, or one that
    # answers no accessibility at all, leaves System Events wedged, and this is
    # the one appearance switch the whole shot depends on.
    for host in (SWIFTBAR, XBAR):
        run(
            ("osascript", "-e", f'tell application "{host.name}" to quit'),
            check=False,
        )
    time.sleep(3)
    for attempt in range(1, 4):
        try:
            osascript(
                bounded(f"""
tell application "System Events"
    tell appearance preferences
        set dark mode to {"true" if dark else "false"}
    end tell
end tell
"""),
            )
        except RuntimeError as error:
            print(f"  appearance, attempt {attempt}: {error}")
            time.sleep(5)
            continue
        break
    time.sleep(3)


def dismiss_prompts() -> None:
    """Click through whatever consent sheets are currently up.

    Two kinds appear. macOS raises a screen-recording sheet on the first
    capture, and each host raises an automation sheet of its own on launch
    (*"xbar" wants access to control "System Events"*). Both are modal, both
    belong to `UserNotificationCenter` rather than to whatever provoked them,
    and either one left up blocks every click that follows.
    """
    for attempt in range(1, 6):
        try:
            found = osascript(
                bounded("""
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
            )
        except RuntimeError as error:
            # System Events can drop out from under this: Control Center is
            # restarted to hide the clock, and a host holding a menu open blocks
            # it outright. Nothing here is load-bearing enough to fail a shot.
            print(f"  consent sheet, attempt {attempt}: {error}")
            time.sleep(4)
            continue
        print(f"  consent sheet, attempt {attempt}: {found} window(s)")
        if found == "0" and attempt > 1:
            return
        time.sleep(4)


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
    dismiss_prompts()


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

    script = plugins / PLUGIN_NAME
    body = "#!/bin/bash\ncat <<'MENU'\n" + menu.rstrip("\n") + "\nMENU\n"
    script.write_text(body, encoding="UTF-8")
    script.chmod(0o755)


def position_keys(plugins: Path) -> tuple[str, ...]:
    """Every spelling of the autosave name a host may key its item by.

    SwiftBar resolves symlinks before naming a plugin, so the name it files an
    item under is the plugin's real path: a machine whose plugin folder holds a
    symlink into a checkout carries the checkout's path, not the link's. The
    temporary folder these captures plant into is itself reached through one,
    macOS putting `/var` behind `/private/var`, so the raw path and the
    resolved path are two different strings and only one of them matches.
    """
    script = plugins / PLUGIN_NAME
    names = (str(script.resolve()), str(script), PLUGIN_NAME)
    return tuple(
        f"NSStatusItem Preferred Position {name}" for name in dict.fromkeys(names)
    )


def restart(host: Host, plugins: Path) -> None:
    """Bring the host back up on whatever the plugin folder now holds.

    A restart rather than a refresh call, because the two hosts refresh
    differently and one of them has to be restarted anyway for a system
    appearance change to reach its menu.

    Every other host is quit first, not just this one. Two bar apps running at
    once put two plugin items in the menu bar, and since macOS draws them into a
    window of Control Center's rather than one of their own, nothing in that
    window says which item belongs to whom: the click then lands on whichever
    happens to sit leftmost. That is what opened a SwiftBar menu during an Xbar
    shot, and what left the capture looking for a menu Xbar never had.
    """
    for other in (SWIFTBAR, XBAR):
        run(
            ("osascript", "-e", f'tell application "{other.name}" to quit'),
            check=False,
        )
    time.sleep(3)
    if host.plugin_dir is None:
        run(("defaults", "write", host.domain, "PluginDirectory", str(plugins)))
    # While the host is down, since a running app rewrites its preferences from
    # memory when it quits, and AppKit reads this one as it creates the item.
    for key in position_keys(plugins):
        run(
            (
                "defaults", "write", host.domain, key,
                "-float", str(STATUS_ITEM_POSITION),
            ),
            check=False,
        )
    run(("open", str(Path("/Applications") / host.bundle)))
    time.sleep(20)
    # Xbar greets a first run with its plugin browser, which sits in front of
    # the menu bar and leaves the process too busy to answer accessibility.
    # Best-effort, and addressed to the host itself: Xbar answers no
    # accessibility at all, so this times out for it rather than finding no
    # windows. A greeting window left open is survivable; failing the shot over
    # one is not.
    try:
        osascript(
            bounded(f"""
tell application "System Events"
    tell process "{host.name}"
        repeat with theWindow in windows
            try
                click button 1 of theWindow
            end try
        end repeat
    end tell
end tell
""")
        )
    except RuntimeError as error:
        print(f"  {host.name} did not answer a window sweep: {error}")
    time.sleep(3)
    dismiss_prompts()


def owned_windows(host: Host, low: int, high: int) -> list[dict[str, float]]:
    """Bounds of the host's windows within a layer range, from the window server.

    How an open menu is found, for both hosts. A status item is not covered:
    macOS draws those into a window of Control Center's, so neither app owns one.
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

"""macOS 26 groups the third-party status items into one window of its own,
owned by Control Center rather than by the app that drew them, which is why no
window is ever listed for SwiftBar or Xbar. With a single bar app running, that
window holds exactly one item and its centre is where to click. Measured against
accessibility on the host that answers it: SwiftBar's item reports `x=1331`, and
this window spans `1288` to `1374`.
"""


def menu_bar_windows(low: int = 60, high: int = 120) -> list[dict[str, float]]:
    """Menu bar windows whose width falls in a range."""
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
        if (b.Y < 40 && b.Width >= LOW && b.Width <= HIGH) {
            boxes.push({x: b.X, y: b.Y, width: b.Width, height: b.Height});
        }
    }
}
JSON.stringify(boxes);
""".replace("LOW", str(low)).replace("HIGH", str(high)),
        language="JXA",
    )
    boxes: list[dict[str, float]] = json.loads(reply)
    return boxes


def measure_system_items() -> float | None:
    """Where the system's own menu bar items begin, with no plugin running.

    A width band cannot separate the two populations, and every value tried has
    eventually matched the wrong thing: the `31px` search icon from below, the
    clock from above once its date came off and it shrank into the band a
    plugin item sits in, which cost run 32570175632 its Xbar shots. Position
    can, since macOS packs its own items against the right edge and gives an
    app the room to their left.
    """
    boxes = menu_bar_windows(low=20, high=400)
    if not boxes:
        return None
    return min(box["x"] for box in boxes)


def system_items() -> list[dict[str, float]]:
    """Bounds of every status item a plugin drew, newest first.

    Anything at or right of {data}`SYSTEM_ITEMS_EDGE` belongs to macOS. Without
    that measurement the old width band stands in, which is wrong often enough
    to have earned the function above, but is all there is.
    """
    if SYSTEM_ITEMS_EDGE is None:
        return menu_bar_windows()
    return [
        box
        for box in menu_bar_windows(low=20, high=400)
        if box["x"] < SYSTEM_ITEMS_EDGE
    ]


def status_item(host: Host) -> tuple[float, float]:
    """Screen coordinates of the plugin's status item.

    Two routes, because the hosts differ in what they answer. SwiftBar serves an
    accessibility tree, so its item is asked for by name. Xbar serves none at
    all: `count of menu bars` on its process times out with `-1712` however long
    it is given. And a status item is not a window either, the menu bar being
    drawn for an app rather than by it, so the window server cannot stand in.
    What it does list is every menu bar window, and with a single bar app
    running the one item left of {data}`SYSTEM_ITEMS_EDGE` is the plugin's.
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

    for attempt in range(1, 13):
        items = system_items()
        if items:
            anchor = min(items, key=lambda box: box["x"])
            return (
                anchor["x"] + anchor["width"] / 2,
                anchor["y"] + anchor["height"] / 2,
            )
        print(f"  {host.name} status item, attempt {attempt}: not drawn yet")
        time.sleep(5)
    msg = f"{host.name} drew no status item left of the system's own"
    raise RuntimeError(msg)


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


def pin_clock() -> bool:
    """Hold the menu bar clock still, and report whether it stayed.

    The captures reach up to the top of the screen so the status item the menu
    hangs off is in frame, the way the GNOME ones include the top bar. The clock
    sits in that strip and reads differently every minute, so left alone it
    rewrites all sixteen images on every run: its window measured 146, 154 and
    160 pixels wide across three of them.

    Taking it out was tried first and cannot be done. macOS `26` offers no
    supported way to remove the clock from the menu bar, and neither preference
    that looks like one moves it: `Clock` in Control Center's per-host domain,
    which that release does not define, nor `NSStatusItem Visible Clock` in its
    plain domain, which does hide a module like `Battery` and leaves the clock
    alone (run 32444526285, run 32447506267, run 32474473540).

    So the clock stays and is made deterministic instead. The date and the day
    cannot be pinned, so they are switched off, leaving a reading that repeats
    every day. Then the time itself is pinned, and network time with it, since
    macOS would otherwise correct the clock partway through the run.
    """
    for key, kind, value in (
        ("ShowDate", "-int", "2"),
        ("ShowDayOfWeek", "-bool", "false"),
        ("ShowSeconds", "-bool", "false"),
        ("Show24Hour", "-bool", "true"),
    ):
        run(
            ("defaults", "write", "com.apple.menuextra.clock", key, kind, value),
            check=False,
        )
    run(("killall", "ControlCenter"), check=False)

    # Backwards, never forwards. GitHub enforces a job's `timeout-minutes`
    # against the wall clock, so a jump ahead can retire a job that has barely
    # started, where a jump back only makes it look younger than it is. So the
    # target is the most recent time the clock read this, which is today's if
    # it has already passed and yesterday's otherwise.
    hour, minute = CLOCK_TIME
    now = time.time()
    target = time.localtime(now)
    pinned = time.mktime(target[:3] + (hour, minute, 0) + target[6:])
    if pinned > now:
        pinned -= 24 * 60 * 60
    global CLOCK_STAMP
    CLOCK_STAMP = time.strftime(
        "%m%d%H%M.%S", time.localtime(pinned - CLOCK_REPAINT_WAIT + 2)
    )
    run(("sudo", "systemsetup", "-setusingnetworktime", "off"), check=False)
    hold_clock()

    # Two things have to hold, and each fails silently on its own. The clock
    # has to read the pinned time, which `date` answers for. And the date has
    # to be off the menu bar, which only its width shows: 154 pixels with the
    # date, about a third of that without. The band is the one that isolates
    # the clock from a status item below it and from the menu bar's own
    # backdrop above it, both of which this probe has matched by accident
    # before (run 32444526285, run 32447506267).
    reading = run(("date", "+%H:%M"), check=False).stdout.strip()
    if reading != f"{hour:02}:{minute:02}":
        print(f"  the clock reads {reading!r}, not the pinned time")
        return False
    wide = menu_bar_windows(low=121, high=400)
    if wide:
        print(f"  the clock still carries its date ({wide}), keeping it out of frame")
        return False
    print(f"  the clock reads {reading}")
    return True


def hold_clock() -> None:
    """Put the clock back, landing a few seconds short of the pinned reading.

    Setting the time does not repaint the menu bar, and a shot taken before it
    repaints carries whatever the clock last said: one did, two minutes stale,
    while `date` answered the pinned time throughout (run 32582726726).
    Landing just short of the minute makes the clock repaint itself, since it
    always holds a timer for the next boundary, and crossing one is the only
    thing that reliably brings the drawn clock and the system clock together.

    Photographing the clock to check instead was tried and cost more than it
    caught: `screencapture` lights macOS's screen-recording indicator, which
    the shot taken a second later then carries, in a menu bar that is supposed
    to look the same every run (run 32591406062).

    {data}`CLOCK_STAMP` is never recomputed: by the second call the machine
    already believes it is `10:30`, so asking for the most recent past `10:30`
    would answer yesterday and walk the date back a day per shot.
    """
    if CLOCK_STAMP is not None:
        run(("sudo", "date", CLOCK_STAMP), check=False)
        time.sleep(CLOCK_REPAINT_WAIT)


def unpin_clock() -> None:
    """Hand the clock back to the network, on the way out of a local run."""
    run(("sudo", "systemsetup", "-setusingnetworktime", "on"), check=False)
    for key in ("ShowDate", "ShowDayOfWeek", "ShowSeconds", "Show24Hour"):
        run(("defaults", "delete", "com.apple.menuextra.clock", key), check=False)
    run(("killall", "ControlCenter"), check=False)


def press_escape() -> None:
    """Close whatever menu is open, with a real key event.

    Not through System Events: an open menu is a modal tracking loop, and a host
    that answers no accessibility at all leaves AppleScript waiting on it until
    the event times out. A key posted to the HID tap needs nothing of the app.
    """
    print(
        swift("""
        import CoreGraphics
        let source = CGEventSource(stateID: .hidSystemState)
        CGEvent(keyboardEventSource: source, virtualKey: 53, keyDown: true)?
            .post(tap: .cghidEventTap)
        usleep(80000)
        CGEvent(keyboardEventSource: source, virtualKey: 53, keyDown: false)?
            .post(tap: .cghidEventTap)
        print("escape")
        """)
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
    # Anchored at the top of the screen when the clock could be hidden, so the
    # status item the menu hangs off is in frame the way the GNOME captures
    # include the top bar. Otherwise the frame starts at the menu.
    top = 0.0 if CLOCK_PINNED else bounds["y"]
    # As late as it can be: the strip is in the frame from here on, and the
    # clock has been ticking since the last shot.
    if CLOCK_PINNED:
        hold_clock()
    rect = f"{bounds['x']},{top},{bounds['right'] - bounds['x']},{bottom - top}"
    run(("screencapture", "-x", "-o", "-t", "png", "-R", rect, str(shot.path)))

    # Dismiss the menu so the next shot starts from a bare desktop.
    press_escape()
    time.sleep(1)
    print(f"  {shot.path.name}: {png_size(shot.path)}")


def diagnose(label: str, host: Host) -> None:
    """Photograph the whole screen and dump what the window server lists.

    Reached when a shot fails. Everything else here reports what a host was
    asked and answered; this reports what was actually on screen, which is the
    only thing that settles a host inferred at second hand.
    """
    if DIAGNOSTICS is None:
        return
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    run(
        ("screencapture", "-x", "-t", "png", str(DIAGNOSTICS / f"{label}.png")),
        check=False,
    )
    windows = osascript(
        """
ObjC.import("CoreGraphics");
ObjC.import("Foundation");
const raw = $.CGWindowListCopyWindowInfo(17, 0);
const list = ObjC.castRefToObject(raw);
const rows = [];
for (let i = 0; i < list.count; i++) {
    const w = list.objectAtIndex(i);
    rows.push({
        owner: ObjC.unwrap(w.objectForKey("kCGWindowOwnerName")),
        layer: ObjC.unwrap(w.objectForKey("kCGWindowLayer")),
        bounds: ObjC.deepUnwrap(w.objectForKey("kCGWindowBounds")),
    });
}
JSON.stringify(rows, null, 2);
""",
        language="JXA",
    )
    (DIAGNOSTICS / f"{label}-windows.json").write_text(windows, encoding="UTF-8")
    print(f"  diagnostics for {host.name} written to {DIAGNOSTICS}")


def capture_all() -> None:
    """Install both hosts, then walk every shot."""
    if sys.platform != "darwin":
        sys.exit("These captures need macOS, and a bar app to drive.")
    for host in (SWIFTBAR, XBAR):
        install(host)
    raise_display()
    spend_consent_prompt()
    global CLOCK_PINNED, SYSTEM_ITEMS_EDGE
    CLOCK_PINNED = pin_clock()
    # After the clock is pinned, since pinning changes its width, and before
    # either host starts, since the point is a menu bar holding nothing of ours.
    SYSTEM_ITEMS_EDGE = measure_system_items()
    print(f"the system's menu bar items start at {SYSTEM_ITEMS_EDGE}")

    with TemporaryDirectory(prefix="mpm-bar-capture-") as name:
        scratch = Path(name) / "plugins"
        scratch.mkdir(parents=True)
        # Remembered so a local run gives the developer their own plugins back.
        swiftbar_folder = run(
            ("defaults", "read", SWIFTBAR.domain, "PluginDirectory"),
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
                    planted.append(plugins / PLUGIN_NAME)
                try:
                    capture(shot, plugins)
                except Exception:
                    diagnose(shot.stem, shot.host)
                    raise

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
            # Written per shot against a folder that is gone by now, so a
            # developer running this locally keeps the menu bar they arranged.
            for host in (SWIFTBAR, XBAR):
                folder = host.plugin_dir or scratch
                for key in position_keys(folder):
                    run(("defaults", "delete", host.domain, key), check=False)
            unpin_clock()
            for leftover in planted:
                leftover.unlink(missing_ok=True)
            if swiftbar_folder:
                run(
                    (
                        "defaults",
                        "write",
                        SWIFTBAR.domain,
                        "PluginDirectory",
                        swiftbar_folder,
                    ),
                    check=False,
                )
            else:
                run(
                    ("defaults", "delete", SWIFTBAR.domain, "PluginDirectory"),
                    check=False,
                )
            set_appearance(dark=False)
            run(
                (
                    "defaults",
                    "-currentHost",
                    "delete",
                    "com.apple.controlcenter.plist",
                    "Clock",
                ),
                check=False,
            )
            run(("killall", "ControlCenter"), check=False)


def main() -> None:
    """Capture every shot."""
    global DIAGNOSTICS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--diagnostics",
        type=Path,
        help="Folder for a screenshot and window dump of any shot that fails.",
    )
    DIAGNOSTICS = parser.parse_args().diagnostics
    capture_all()


if __name__ == "__main__":
    main()
