"""TEMPORARY probe, deleted with `.github/workflows/status-item-probe.yaml`.

Where SwiftBar's status item lands under each value of the
`NSStatusItem Preferred Position` key the capture driver writes, and what
AppKit stores back under that key, which is what settles how the value is read.
Every launch goes through the driver's own {func}`restart`, so the only thing
that varies between variants is the key, or the spacer's name.
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

# Label, key value (None deletes the keys), spacer filename.
VARIANTS = (
    ("key 700, as the driver writes it", 700, driver.SPACER_NAME),
    ("no key", None, driver.SPACER_NAME),
    ("key 100", 100, driver.SPACER_NAME),
    ("key 400", 400, driver.SPACER_NAME),
    ("key 900", 900, driver.SPACER_NAME),
    ("no key, spacer sorting after the plugin", None, "zzz-spacer.1h.sh"),
    ("key 700, spacer sorting after the plugin", 700, "zzz-spacer.1h.sh"),
    ("no key, no spacer", None, None),
)


def stored_keys() -> list[str]:
    """Every `NSStatusItem` entry of the host's defaults, as AppKit wrote them."""
    reply = driver.run(("defaults", "read", HOST.domain), check=False).stdout
    return [line.strip() for line in reply.splitlines() if "NSStatusItem" in line]


def plant_spacer(plugins: Path, name: str | None) -> None:
    for stale in plugins.glob("*spacer*"):
        stale.unlink()
    if name is None:
        return
    spacer = plugins / name
    spacer.write_text(
        "#!/bin/bash\necho '" + " " * driver.SPACER_WIDTH + "| trim=false'\n",
        encoding="UTF-8",
    )
    spacer.chmod(0o755)


def launch(label: str, plugins: Path, hint: float | None, spacer: str | None) -> None:
    plant_spacer(plugins, spacer)
    keys = driver.position_keys(plugins)
    for key in keys:
        driver.run(("defaults", "delete", HOST.domain, key), check=False)
    # The driver writes the keys inside `restart`, from these two names.
    driver.STATUS_ITEM_POSITION = hint
    driver.position_keys = (
        (lambda plugins: ()) if hint is None else lambda plugins: keys
    )
    driver.restart(HOST, plugins)
    time.sleep(5)
    print(f"## {label}")
    driver.report_windows(label)
    print("  stored while running:")
    for entry in stored_keys():
        print(f"    {entry}")
    driver.run(
        ("osascript", "-e", f'tell application "{HOST.name}" to quit'), check=False
    )
    time.sleep(3)
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
        print("keys the driver writes:", *driver.position_keys(plugins), sep="\n  ")
        for label, hint, spacer in VARIANTS:
            launch(label, plugins, hint, spacer)
        print("## every key of the domain, at the end")
        print(driver.run(("defaults", "read", HOST.domain), check=False).stdout)


if __name__ == "__main__":
    main()
