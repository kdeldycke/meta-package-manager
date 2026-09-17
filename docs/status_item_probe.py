"""TEMPORARY probe, deleted with `.github/workflows/status-item-probe.yaml`.

Where SwiftBar's status item lands under each value of the
`NSStatusItem Preferred Position` key the capture driver writes, what AppKit
stores back under that key, and which spacer name puts the spacer to the right
of the plugin's item: SwiftBar creates its items in directory-enumeration
order, and AppKit gives each new item the leftmost slot among the app's own.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from tempfile import TemporaryDirectory

spec = importlib.util.spec_from_file_location(
    "bar_screenshots_update", Path(__file__).with_name("bar_screenshots_update.py")
)
driver = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(driver)  # type: ignore[union-attr]

HOST = driver.SWIFTBAR
SPACER = "#!/bin/bash\necho '" + " " * driver.SPACER_WIDTH + "| trim=false'\n"

# Label, key value (None deletes the keys), spacer filename (None plants none).
VARIANTS = (
    ("key 700, as the driver writes it", 700, driver.SPACER_NAME),
    ("no key", None, driver.SPACER_NAME),
    ("key 100", 100, driver.SPACER_NAME),
    ("key 900", 900, driver.SPACER_NAME),
    ("no key, spacer zzz-spacer.1h.sh", None, "zzz-spacer.1h.sh"),
    ("no key, spacer 0-spacer.1h.sh", None, "0-spacer.1h.sh"),
    ("no key, spacer spacer.1h.sh", None, "spacer.1h.sh"),
    ("no key, spacer room.1h.sh", None, "room.1h.sh"),
    ("no key, no spacer", None, None),
)

SYSTEM_EDGE = 0.0


def running() -> bool:
    return driver.run(("pgrep", "-x", HOST.name), check=False).returncode == 0


def quit_host() -> None:
    if not running():
        return
    driver.run(
        ("osascript", "-e", f'tell application "{HOST.name}" to quit'), check=False
    )
    for _ in range(30):
        if not running():
            break
        time.sleep(1)
    time.sleep(2)


def stored_keys() -> list[str]:
    """Every `NSStatusItem` entry of the host's defaults, as AppKit wrote them."""
    reply = driver.run(("defaults", "read", HOST.domain), check=False).stdout
    return [line.strip() for line in reply.splitlines() if "NSStatusItem" in line]


def app_items() -> list[str]:
    """The app's own menu bar items, left to right, as `x:width`."""
    boxes = driver.menu_bar_windows(low=20, high=10_000)
    return [
        f"{box['x']:.0f}:{box['width']:.0f}"
        for box in sorted(boxes, key=lambda box: box["x"])
        if box["x"] < SYSTEM_EDGE
    ]


def dismiss_windows() -> None:
    """The driver's own best-effort click on whatever the host greets a run with."""
    try:
        driver.osascript(
            driver.bounded(f"""
tell application "System Events"
    tell process "{HOST.name}"
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
        print(f"  dismissing windows: {error}")


def launch(label: str, plugins: Path, hint: float | None, spacer: str | None) -> None:
    quit_host()
    for stale in plugins.glob("*.1h.sh"):
        stale.unlink()
    if spacer is not None:
        (plugins / spacer).write_text(SPACER, encoding="UTF-8")
        (plugins / spacer).chmod(0o755)
    keys = driver.position_keys(plugins)
    for key in keys:
        driver.run(("defaults", "delete", HOST.domain, key), check=False)
    if hint is not None:
        for key in keys:
            driver.run(("defaults", "write", HOST.domain, key, "-float", str(hint)))
    driver.run(("open", str(Path("/Applications") / HOST.bundle)))
    print(f"## {label}")
    expected = 1 if spacer is None else 2
    previous: list[str] = []
    settled = 0
    for elapsed in range(5, 125, 5):
        time.sleep(5)
        if elapsed == 20:
            dismiss_windows()
        items = app_items()
        if items != previous:
            print(f"  {elapsed:>3}s running={running()} items={items}")
            previous = items
            settled = 0
        elif len(items) >= expected:
            settled += 1
            if settled >= 2:
                break
    print(f"  final: {app_items()}")
    print("  stored while running:")
    for entry in stored_keys():
        print(f"    {entry}")
    quit_host()
    print("  stored after quit:")
    for entry in stored_keys():
        print(f"    {entry}")


def main() -> None:
    global SYSTEM_EDGE
    driver.require_macos()
    driver.install(HOST)
    # The runner's screen comes up 1024 wide, and macOS hides the status items
    # that do not fit beside the front app's menus: the 665-pixel spacer never
    # showed on it, and took the plugin's item down with it.
    driver.raise_display()
    quit_host()
    edge = driver.measure_system_items()
    if edge is None:
        msg = "No system menu bar items measured."
        raise RuntimeError(msg)
    SYSTEM_EDGE = edge
    print(f"system items start at {SYSTEM_EDGE}")
    with TemporaryDirectory(prefix="mpm-status-item-") as name:
        plugins = Path(name) / "plugins"
        plugins.mkdir()
        plugin = plugins / driver.PLUGIN_NAME
        plugin.write_text("#!/bin/bash\necho '🎁 probe'\n", encoding="UTF-8")
        plugin.chmod(0o755)
        driver.run(("defaults", "write", HOST.domain, "PluginDirectory", str(plugins)))
        print("keys the driver writes:", *driver.position_keys(plugins), sep="\n  ")
        for label, hint, spacer in VARIANTS:
            launch(label, plugins, hint, spacer)
        print("## every key of the domain, at the end")
        print(driver.run(("defaults", "read", HOST.domain), check=False).stdout)


if __name__ == "__main__":
    main()
