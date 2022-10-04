# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import PackageManager
from ..capabilities import version_not_implemented


class SteamCMD(PackageManager):

    """Basic SteamCMD usage.

    SteamCMD doesn't seem to be properly documented and maintained to offer a powerful automated integration.

    Documentation:

    - `list of steamcmd commands <https://github.com/dgibbs64/SteamCMD-Commands-List/blob/master/steamcmd_commands.txt>`_

    .. todo::

        Evaluate `steam-cli <https://github.com/berenm/steam-cli>`_ as an alternative.
    """

    name = "Valve Steam"

    homepage_url = "https://developer.valvesoftware.com/wiki/SteamCMD"

    platforms = frozenset({MACOS, LINUX, WINDOWS})

    requirement = None
    """Accept any SteamCMD version as it seems it is hardly versioned at all."""

    post_args = ("+quit",)

    version_cli_options = ("+quit",)
    version_regex = r"Valve\ Corporation\ -\ version\ (?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► steamcmd +quit
        Redirecting stderr to '~/Library/Application Support/Steam/logs/stderr.txt'
        [  0%] Checking for available updates...
        [----] Verifying installation...
        Steam Console Client (c) Valve Corporation - version 1648077083
        -- type 'quit' to exit --
        Loading Steam API...OK
    """

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► steamcmd +app_update 740 validate +quit
        """
        return self.run_cli("+app_update", package_id, "validate")

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► steamcmd +app_update 740 validate +quit
        """
        return self.build_cli("+app_update", package_id, "validate")
