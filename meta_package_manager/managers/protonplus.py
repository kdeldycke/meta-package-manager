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

import json
import logging
import os
from pathlib import Path
from typing import ClassVar

from extra_platforms import LINUX_LIKE

from ..capabilities import version_not_implemented
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package

MARKER = ".protonplus"
"""The record ProtonPlus writes into the directory of every release it installs.

A JSON object naming the launcher, the runner and the release tag. ProtonPlus
builds its own inventory from these files (`src/utils/metadata.vala`), and
defaults a missing field to an empty string.
"""

GROUP_DIRECTORIES = (
    "compatibilitytools.d",
    "dxvk",
    "runners",
    "runners/wine",
    "runtime/dxvk",
    "runtime/vkd3d",
    "Runners",
    "tools/proton",
    "tools/wine",
)
"""Where a launcher keeps its runners, relative to the launcher's own directory.

Mirrors `get_group_directory()` in `src/models/launcher.vala` of ProtonPlus
`0.6.8`: `compatibilitytools.d` for Steam and Faugus Launcher, `runners/wine`,
`runtime/dxvk` and `runtime/vkd3d` for Lutris, `tools/proton` and `tools/wine`
for Heroic Games Launcher, `runners` and `dxvk` for Bottles, and `Runners` for
WineZGUI.
"""


def _launcher_directories() -> tuple[Path, ...]:
    """Every directory ProtonPlus looks for a launcher in.

    Mirrors the launcher definitions under `src/models/launchers/` of ProtonPlus
    `0.6.8`, native, Flatpak and Snap installations alike, with the XDG base
    directories resolved the way GLib resolves them. A launcher ProtonPlus
    learns later stays out of the inventory until this list learns it too.
    """
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    state = Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state")
    flatpak = home / ".var" / "app"
    faugus = flatpak / "io.github.Faugus.faugus-launcher"
    return (
        # Steam.
        data / "Steam",
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".steam" / "debian-installation",
        flatpak / "com.valvesoftware.Steam" / "data" / "Steam",
        home / "snap" / "steam" / "common" / ".steam" / "root",
        # Lutris.
        data / "lutris",
        home / ".local" / "share" / "lutris",
        flatpak / "net.lutris.Lutris" / "data" / "lutris",
        # Heroic Games Launcher.
        config / "heroic",
        home / ".config" / "heroic",
        flatpak / "com.heroicgameslauncher.hgl" / "config" / "heroic",
        # Bottles.
        data / "bottles",
        home / ".local" / "share" / "bottles",
        flatpak / "com.usebottles.bottles" / "data" / "bottles",
        # Faugus Launcher.
        config / "faugus-launcher",
        data / "faugus-launcher",
        state / "faugus-launcher",
        home / ".config" / "faugus-launcher",
        home / ".local" / "share" / "faugus-launcher",
        faugus / "config" / "faugus-launcher",
        faugus / "data" / "faugus-launcher",
        # WineZGUI.
        data / "winezgui",
        home / ".local" / "share" / "winezgui",
        flatpak / "io.github.fastrizwaan.WineZGUI" / "data" / "winezgui",
    )


class ProtonPlus(PackageManager):
    """ProtonPlus, installing Proton, Wine, DXVK and VKD3D builds into game launchers.

    A package is one runner on one launcher, identified as
    `<launcher_id>/<runner_id>`: `lutris-system/dxvk-doitsujin` is DXVK
    (doitsujin) as the natively installed Lutris sees it. `protonplus list` names
    the launchers ProtonPlus detects. ProtonPlus has no catalog command, but
    `protonplus install <launcher_id> <runner_id>` answers an unknown runner ID
    with the list of the ones that launcher accepts.

    The inventory reads the `.protonplus` record ProtonPlus writes into every
    release it installs, which is also what ProtonPlus builds its own listing
    from. `protonplus list <launcher_id>` prints directory names only, with
    neither runner nor version, and mixes in the launcher's own directories. The
    records are looked for in the launcher directories ProtonPlus checks as of
    `0.6.8`, which is an implementation detail rather than a documented contract:
    a release missing from the inventory after a ProtonPlus upgrade points there
    first. A runner kept at several releases is listed once, at its newest.

    `install` fetches the newest release into a rolling `<runner title> Latest`
    directory, the one release that `upgrade` moves forward. A release installed
    at a chosen version from ProtonPlus itself is listed too, but `upgrade --all`
    passes it over, and upgrading a runner that holds no rolling release fails
    with ProtonPlus's own `This compatibility tool is not installed.` error: run
    `mpm install` on it first. `remove` deletes every release of the runner on
    that launcher.

    `mpm` runs the `protonplus` command. The AppImage build carries a longer file
    name: link it as `protonplus` into a directory on `PATH`.
    """

    # `outdated`: ProtonPlus compares releases only inside `update`, which applies
    # the newer one at once. `search`: the only runner listing is the error an
    # unknown runner ID triggers, not a command to build an operation on.

    operation_notes: ClassVar = {
        "outdated": "ProtonPlus compares releases only while `update` applies them.",
        "search": "ProtonPlus has no catalog, only an error listing the runner IDs.",
    }

    name = "ProtonPlus"

    repository_url = "https://github.com/Vysp3r/ProtonPlus"

    platforms = LINUX_LIKE

    requirement = ">=0.6.0"
    """The first release writing `.protonplus` records that name the launcher and the
    runner, and taking the `latest` and `all` arguments of `install`, `uninstall`
    and `update`."""

    version_cli_options = ("version",)

    version_regexes = (r"ProtonPlus\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session
    $ protonplus version
    ProtonPlus 0.6.8
    ```
    """

    @staticmethod
    def _split(package_id: str) -> tuple[str, str]:
        """Split a package ID into the launcher and runner IDs ProtonPlus takes."""
        launcher_id, _, runner_id = package_id.partition("/")
        return launcher_id, runner_id

    @staticmethod
    def _records() -> Iterator[dict[str, str]]:
        """Yield every `.protonplus` record naming both its launcher and runner.

        A launcher reached through a symlink, like `~/.steam/root` pointing into
        `~/.local/share/Steam`, is read once.
        """
        seen: set[Path] = set()
        for base in _launcher_directories():
            for group in GROUP_DIRECTORIES:
                for marker in sorted((base / group).glob(f"*/{MARKER}")):
                    resolved = marker.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    try:
                        record = json.loads(marker.read_text(encoding="UTF-8"))
                    except (OSError, ValueError) as ex:
                        logging.debug(f"Skip unreadable {marker}: {ex}")
                        continue
                    if not (
                        isinstance(record, dict)
                        and record.get("launcher_id")
                        and record.get("provider_id")
                    ):
                        logging.debug(f"Skip {marker}: it names no launcher or runner.")
                        continue
                    yield record

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Each release carries its record, like this one ProtonPlus wrote for the
        rolling DXVK release of Lutris, in
        `~/.local/share/lutris/runtime/dxvk/DXVK (doitsujin) Latest/.protonplus`:

        ```{code-block} json
        {"runner_endpoint":"https://api.github.com/repos/doitsujin/dxvk/releases","runner_title":"DXVK (doitsujin)","tag":"v3.1.1","provider_id":"dxvk-doitsujin","tool_id":"lutris-system/dxvk/dxvk-doitsujin","launcher_id":"lutris-system","variant_id":"standard","release_id":"381956359"}
        ```

        A record naming no launcher or no runner is skipped, since no command
        could address its release.

        ```{todo}
        Read the inventory from `protonplus list` and drop the record scan, with
        {data}`GROUP_DIRECTORIES` and the launcher directory table, once
        [Vysp3r/ProtonPlus#1313](https://github.com/Vysp3r/ProtonPlus/issues/1313)
        makes `list` print the runner ID and tag of each release.
        ```
        """
        tags: dict[str, list[str]] = {}
        for record in self._records():
            package_id = f"{record['launcher_id']}/{record['provider_id']}"
            found = tags.setdefault(package_id, [])
            if record.get("tag"):
                found.append(record["tag"])
        for package_id, found in sorted(tags.items()):
            newest = max(found, key=parse_version) if found else None
            yield self.package(id=package_id, installed_version=newest)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `latest` fetches the newest release into the rolling `<runner title>
        Latest` directory. Without it ProtonPlus lists the releases and waits for
        a number on its standard input, so a pinned version is not supported.

        The block below illustrates rather than captures: the package ID splits
        into two arguments, so the corpus cannot rebuild this command from a
        stand-in package id.

        ```{code-block} console
        $ protonplus install lutris-system dxvk-doitsujin latest
        ```
        """
        launcher_id, runner_id = self._split(package_id)
        return self.run_cli("install", launcher_id, runner_id, "latest")

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generate the CLI to upgrade the rolling release of every runner.

        ```{code-block} shell-session
        $ protonplus update all
        ```
        """
        return self.build_cli("update", "all")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generate the CLI to upgrade the rolling release of one runner.

        The block below illustrates rather than captures: the package ID splits
        into two arguments, so the corpus cannot rebuild this command from a
        stand-in package id.

        ```{code-block} console
        $ protonplus update lutris-system dxvk-doitsujin
        ```
        """
        launcher_id, runner_id = self._split(package_id)
        return self.build_cli("update", launcher_id, runner_id)

    def remove(self, package_id: str) -> str:
        """Remove every release of one runner from its launcher.

        The block below illustrates rather than captures: the package ID splits
        into two arguments, so the corpus cannot rebuild this command from a
        stand-in package id.

        ```{code-block} console
        $ protonplus uninstall lutris-system dxvk-doitsujin all
        ```
        """
        launcher_id, runner_id = self._split(package_id)
        return self.run_cli("uninstall", launcher_id, runner_id, "all")
