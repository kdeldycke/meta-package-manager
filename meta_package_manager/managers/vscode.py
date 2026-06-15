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

from typing import ClassVar

from extra_platforms import ALL_PLATFORMS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class VSCode(PackageManager):
    name = "Visual Studio Code"

    homepage_url = "https://code.visualstudio.com"

    platforms = ALL_PLATFORMS

    requirement = ">=1.60.0"

    cli_names = ("code",)

    # Explicit annotation widens the inferred ``str`` literal so the
    # :py:class:`VSCodium` subclass below can opt out by re-setting to ``None``.
    brewfile_entry_type: ClassVar[str | None] = "vscode"
    """
    .. code-block:: shell-session

        $ code --version
        1.60.2
        7f6ab5485bbc008386c4386d08766667e155244e
        x64
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ code --list-extensions --show-versions
            ms-python.python@2021.9.1246542782
            ms-python.vscode-pylance@2021.9.3
            ms-toolsai.jupyter@2021.8.2041215044
            ms-toolsai.jupyter-keymap@1.0.0
            samuelcolvin.jinjahtml@0.16.0
            tamasfe.even-better-toml@0.14.2
            trond-snekvik.simple-rst@1.5.0
        """
        output = self.run_cli("--list-extensions", "--show-versions")

        for package in output.splitlines():
            package_id, installed_version = package.split("@")
            yield self.package(id=package_id, installed_version=installed_version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ code --install-extension tamasfe.even-better-toml
        """
        return self.run_cli("--install-extension", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ code --uninstall-extension tamasfe.even-better-toml
        """
        return self.run_cli("--uninstall-extension", package_id)


class VSCodium(VSCode):
    homepage_url = "https://vscodium.com"
    cli_names = ("codium",)

    # Brewfile's `vscode` extension installs to VS Code only. Emitting VSCodium
    # extensions under that entry type would silently misroute them; skip and
    # warn the user via :py:attr:`brewfile_skip_warning`.
    brewfile_entry_type = None
    brewfile_skip_warning = (
        "Skipping {count} VSCodium extension(s) in Brewfile output: brew "
        "bundle has no `vscodium` entry type, and emitting them as `vscode` "
        "would install them to VS Code instead of VSCodium."
    )
