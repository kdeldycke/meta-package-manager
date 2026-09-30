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

import re
from typing import ClassVar

from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Whalebrew(PackageManager):
    """Whalebrew, installing Docker images as commands.

    A package is a Docker image, identified as the listing prints it:
    `whalebrew/wget`, or `hello-world:linux` where a tag was given. Whalebrew
    writes one small YAML file per image into its install directory, named after
    the command the image provides, and runs the image through `docker run` each
    time that command is called. The command is reported as the package name.

    `install` needs a running Docker daemon the user can reach, and refuses an
    image that declares no `ENTRYPOINT`. `mpm install` looks the image up through
    `search` first, which only reaches the registries Whalebrew searches: install
    an image from anywhere else with `whalebrew install` itself, and the listing
    reports it like any other.

    Packages go to `/usr/local/bin` by default, which a regular user cannot write
    to on Linux. Point `WHALEBREW_INSTALL_PATH`, or `install_path` in
    `~/.whalebrew/config.yaml`, at a directory of your own, like
    `~/.whalebrew/bin`.
    """

    # Whalebrew keys its two mutating verbs on different things: `install` takes an
    # image, while `uninstall` finds the package by its command or its image and
    # then deletes a file named after its argument, so an image fails with "no such
    # file or directory". The fix, whalebrew/whalebrew#323, has waited since
    # 2025-03. Packages are keyed on the image, the one identifier `search`,
    # `install` and the listing share, and `remove` looks the command up first.
    #
    # `outdated` and `upgrade`: the README upgrades a package by pulling its image
    # with `docker pull`, a Docker verb rather than a Whalebrew one, and nothing
    # reports a newer image without pulling it.

    operation_notes: ClassVar = {
        "outdated": "Nothing reports a newer image without pulling it.",
        "upgrade": "Upgrading is pulling the image with Docker, not a Whalebrew verb.",
        "upgrade_all": "Upgrading is pulling each image with Docker.",
    }

    name = "Whalebrew"

    repository_url = "https://github.com/whalebrew/whalebrew"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=0.4.1"
    """The release restoring `search` after Docker Hub changed its API.

    The official `0.5.0` binary reports itself as a `0.4.1` build, having been
    compiled from a tree `git describe` places 38 commits past that tag, so a
    higher floor would reject it.
    """

    version_cli_options = ("version",)

    version_regexes = (r"^Whalebrew[ \t]+(?P<version>\d+\.\d+\.\d+)",)
    """Keep the release part of the version string.

    ```{code-block} shell-session

    $ whalebrew version
    Whalebrew 0.4.1-38-g79b8605-dirty+2024-08-02.79b860575946278fd3215e68677d7439424d1cd1
    ```
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<command>\S+)[ \t]+(?P<package_id>\S+)$")
    """One package per line: the command, then the image it runs."""

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ whalebrew list --no-headers
        hello-world  hello-world:linux
        ```
        """
        output = self.run_cli("list", "--no-headers")
        for match in map(self._INSTALLED_REGEXP.match, output.splitlines()):
            if match:
                yield self.package(
                    id=match.group("package_id"),
                    name=match.group("command"),
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Queries the registries Whalebrew is configured with, Docker Hub's
        `whalebrew` organization by default, for images carrying the labels a
        Whalebrew package declares. The term is matched against the image name
        within each registry, so `whalebrew/wget` finds nothing where `wget`
        finds it: the namespace and tag of the query are dropped before sending.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ whalebrew search wget
        whalebrew/wget
        ```
        """
        term = query.rsplit("/", 1)[-1].split(":", 1)[0]
        output = self.run_cli("search", term)
        for line in output.splitlines():
            image = line.strip()
            if image:
                yield self.package(id=image)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        `--assume-yes` accepts the ports, volumes and environment an image asks
        for, which Whalebrew otherwise confirms on the terminal.

        ```{code-block} shell-session

        $ whalebrew install --assume-yes whalebrew/wget
        ```
        """
        return self.run_cli("install", "--assume-yes", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        Whalebrew deletes the file named after its argument, so the image is
        swapped for the command the listing pairs it with.

        ```{code-block} shell-session

        $ whalebrew uninstall --assume-yes wget
        ```
        """
        with self.acting_as("installed"):
            command = next(
                (
                    package.name
                    for package in self.installed
                    if package.id == package_id and package.name
                ),
                package_id,
            )
        return self.run_cli("uninstall", "--assume-yes", command)
