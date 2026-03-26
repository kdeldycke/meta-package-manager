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

from extra_platforms import ALL_WINDOWS, LINUX_LIKE, MACOS

from ..base import PackageManager
from ..capabilities import version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class Stew(PackageManager):
    """Stew installs pre-compiled binaries from GitHub Releases.

    .. caution::
        ``stew search`` launches an interactive terminal UI and cannot be used
        programmatically. Search is not supported.

    .. note::
        Stew identifies packages by binary name for upgrade and uninstall, but
        uses ``owner/repo`` format for install.
    """

    homepage_url = "https://github.com/marwanhawari/stew"

    platforms = LINUX_LIKE, MACOS, ALL_WINDOWS

    requirement = ">=0.3.0"

    version_regexes = (r"stew version v(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ stew --version
        stew version v0.6.0
    """

    # Matches GitHub-sourced packages: binary:owner/repo@tag
    _INSTALLED_GITHUB_REGEXP = re.compile(
        r"^(?P<package_id>\S+?):(?P<owner>\S+?)/(?P<repo>\S+?)@(?P<version>\S+)$",
    )

    # Matches URL-sourced packages: binary:url (no @tag).
    _INSTALLED_URL_REGEXP = re.compile(
        r"^(?P<package_id>\S+?):\S+$",
    )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ stew list --tags
            gh:cli/cli@v2.4.0
            fzf:junegunn/fzf@0.29.0
            hyperfine:https://github.com/.../hyperfine-v1.12.0-x86_64-apple-darwin.tar.gz
            rg:BurntSushi/ripgrep@13.0.0
        """
        output = self.run_cli("list", "--tags")

        for line in output.splitlines():
            match = self._INSTALLED_GITHUB_REGEXP.match(line)
            if match:
                package_id = match.group("package_id")
                # Strip leading "v" from tags like "v2.4.0".
                version = match.group("version").removeprefix("v")
                yield self.package(id=package_id, installed_version=version)
                continue

            # URL-sourced packages have no version tag.
            match = self._INSTALLED_URL_REGEXP.match(line)
            if match:
                yield self.package(id=match.group("package_id"))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ stew install junegunn/fzf
            junegunn/fzf
            ⬇️  Downloading asset: ...
            ✨ Successfully installed the fzf binary
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Upgrade all packages.

        .. code-block:: shell-session

            $ stew upgrade --all
        """
        return self.build_cli("upgrade", "--all")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Upgrade one package.

        .. code-block:: shell-session

            $ stew upgrade fzf
            fzf
            ⬇️  Downloading asset: ...
            ✨ Successfully upgraded the fzf binary from 0.29.0 to 0.30.0
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ stew uninstall fzf
            📄 Updated Stewfile.lock.json
            ✨ Successfully uninstalled the fzf binary
        """
        return self.run_cli("uninstall", package_id)
