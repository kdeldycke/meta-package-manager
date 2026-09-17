"""TEMPORARY probe, deleted with `.github/workflows/status-item-probe.yaml`.

Where SwiftBar's status item lands under each value of the
`NSStatusItem Preferred Position` key the capture driver writes, and what
AppKit stores back under that key, which is what settles how the value is read.
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

VARIANTS = (
    ("no key", None),
    ("key 700, as the driver writes it", 700),
    ("key 300", 300),
    ("key 1000", 1000),
    ("key 1300", 1300),
)


def quit_host() -> None:
    driver.run(
        ("osascript", "-e", f'tell application "{HOST.name}" to quit'), check=False
    )
    time.sleep(3)


def stored_keys() -> list[str]:
    """Every `NSStatusItem` entry of the host's defaults, as AppKit wrote them."""
    reply = driver.run(("defaults", "read", HOST.domain), check=False).stdout
    return [line.strip() for line in reply.splitlines() if "NSStatusItem" in line]


def launch(label: str, plugins: Path, hint: float | None) -> None:
    quit_host()
    driver.run(("defaults", "delete", HOST.domain), check=False)
    driver.run(("defaults", "write", HOST.domain, "PluginDirectory", str(plugins)))
    if hint is not None:
        for key in driver.position_keys(plugins):
            driver.run(("defaults", "write", HOST.domain, key, "-float", str(hint)))
    driver.run(("open", str(Path("/Applications") / HOST.bundle)))
    time.sleep(20)
    boxes = sorted(driver.menu_bar_windows(low=1, high=10_000), key=lambda b: b["x"])
    print(f"## {label}")
    for box in boxes:
        print(f"  x={box['x']:>6} w={box['width']:>5}")
    print("  stored while running:")
    for entry in stored_keys():
        print(f"    {entry}")
    quit_host()
    print("  stored after quit:")
    for entry in stored_keys():
        print(f"    {entry}")


def main() -> None:
    driver.require_macos()
    driver.install(HOST)
    with TemporaryDirectory(prefix="mpm-status-item-") as name:
        plugins = Path(name) / "plugins"
        plugins.mkdir()
        plugin = plugins / driver.PLUGIN_NAME
        plugin.write_text("#!/bin/bash\necho '🎁 probe'\n", encoding="UTF-8")
        plugin.chmod(0o755)
        spacer = plugins / driver.SPACER_NAME
        spacer.write_text(
            "#!/bin/bash\necho '" + " " * driver.SPACER_WIDTH + "| trim=false'\n",
            encoding="UTF-8",
        )
        spacer.chmod(0o755)
        print("keys the driver writes:", *driver.position_keys(plugins), sep="\n  ")
        for label, hint in VARIANTS:
            launch(label, plugins, hint)


if __name__ == "__main__":
    main()
