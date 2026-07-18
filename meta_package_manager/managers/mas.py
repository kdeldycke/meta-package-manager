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

from extra_platforms import MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class MAS(PackageManager):
    """``mas`` drives the Mac App Store from the command line.

    Packages are Mac App Store applications, keyed by the numeric adamID Apple
    assigns each title (the ``id`` in an App Store link). mpm reads and writes
    that ID; the display name rides along only as a label.

    Every query reads ``--json`` output, the supported programmatic interface
    since the ``>=7.0.0`` floor added ``--json`` to ``list``, ``outdated`` and
    ``search``. It sidesteps the column-alignment ambiguities of the tabular
    listing, where an app name carrying parentheses or padding whitespace would
    derail a positional parser.

    .. note::

        ``mas`` prints one JSON object per app, concatenated rather than wrapped
        in an array, and leaves control characters (embedded newlines,
        ``U+2028``) unescaped inside name and description strings (`upstream bug
        <https://github.com/mas-cli/mas/issues/1248>`_). mpm decodes the buffer
        one object at a time with ``strict=False`` so each object ends at its own
        closing brace instead of splitting on those bytes.

    .. note::

        ``mas`` self-escalates: it asks for root itself when a store mutation
        needs it, so mpm never wraps ``install``, ``upgrade`` or ``uninstall`` in
        its own ``sudo``.
    """

    name = "Mac App Store"

    homepage_url = "https://github.com/mas-cli/mas"

    brewfile_entry_type = "mas"

    platforms = MACOS

    requirement = ">=7.0.0"
    """`7.0.0 <https://github.com/mas-cli/mas/releases/tag/v7.0.0>`_ introduces
    the ``--json`` flag on ``config``, ``list``, ``lookup``/``info``,
    ``outdated`` & ``search``. Parsing structured JSON output is the supported
    programmatic interface: it sidesteps the column-alignment ambiguities of
    the tabular output (app names containing parentheses or extra whitespace
    would break the previous regex-based parser).
    """

    version_cli_options = ("version",)
    """
    .. code-block:: shell-session

        $ mas version
        7.0.0
    """

    def brewfile_entry(self, package):
        """Brewfile ``mas`` entries take the app's display name as the positional
        argument and the Mac App Store numeric ID as the ``id:`` keyword.

        Returns ``None`` (silently skip) for any package whose ID is not a numeric
        adamID: that shape is impossible to round-trip through ``brew bundle``
        without the ID, and a half-broken ``mas "Name"`` line would error at
        install time.
        """
        try:
            adam_id = int(package.id)
        except (TypeError, ValueError):
            return None
        return package.name or package.id, {"id": adam_id}

    @staticmethod
    def _parse_json_stream(output: str) -> Iterator[dict]:
        """Parse mas ``--json`` output as a stream of concatenated JSON objects,
        one per app.

        .. note::
            ``mas`` emits one JSON object per record but does not escape control
            characters (``U+0000``-``U+001F``, ``U+2028``) inside string fields
            like app names and descriptions, so splitting by lines breaks any
            record whose fields contain a real ``\\n`` or ``U+2028``. Walking
            the buffer with :py:meth:`json.JSONDecoder.raw_decode` instead lets
            each object terminate at its own closing brace, and ``strict=False``
            permits the embedded control characters that the upstream output
            actually contains. Upstream bug:
            https://github.com/mas-cli/mas/issues/1248
        """
        decoder = json.JSONDecoder(strict=False)
        idx = 0
        end = len(output)
        while idx < end:
            while idx < end and output[idx].isspace():
                idx += 1
            if idx >= end:
                break
            obj, idx = decoder.raw_decode(output, idx)
            yield obj

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ mas list --json
            {"adamID":1569813296,"bundleID":"com.1password.1password-safari","name":"1Password for Safari","version":"2.3.5"}
            {"adamID":1295203466,"bundleID":"com.microsoft.rdc.macos","name":"Microsoft Remote Desktop","version":"10.7.6"}
            {"adamID":409183694,"bundleID":"com.apple.iWork.Keynote","name":"Keynote","version":"12.0"}
        """
        output = self.run_cli("list", "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                installed_version=app["version"],
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ mas outdated --json
            {"adamID":409183694,"name":"Keynote","newVersion":"12.0","version":"11.0"}
            {"adamID":1176895641,"name":"Spark","newVersion":"2.11.21","version":"2.11.20"}
        """
        output = self.run_cli("outdated", "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                installed_version=app["version"],
                latest_version=app["newVersion"],
            )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we return the best
            subset of results and let
            :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search` refine
            them.

        .. code-block:: shell-session

            $ mas search python --json
            {"adamID":689176796,"name":"Python Runner","version":"1.3"}
            {"adamID":630736088,"name":"Learning Python","version":"1.0"}
            {"adamID":945397020,"name":"Run Python","version":"1.0"}
            {"adamID":1164498373,"name":"PythonGames","version":"1.0"}
            {"adamID":1400050251,"name":"Pythonic","version":"1.0.0"}
        """
        output = self.run_cli("search", query, "--json")

        for app in self._parse_json_stream(output):
            yield self.package(
                id=str(app["adamID"]),
                name=app["name"],
                latest_version=app["version"],
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ mas install 945397020
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        .. code-block:: shell-session

            $ mas upgrade
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        .. code-block:: shell-session

            $ mas upgrade 945397020
        """
        return self.build_cli("upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ``mas`` 4.1.0+ requests root privileges itself when not already
        running as root, so we don't pre-wrap the call in ``sudo``. This
        matches how ``install`` and ``upgrade`` are already invoked.

        .. code-block:: shell-session

            $ mas uninstall 1494051017
            Password:
            Uninstalled '/Applications/SimpleLogin.app' to '/Users/kde/.Trash/SimpleLogin.app'
        """
        return self.run_cli("uninstall", package_id)
