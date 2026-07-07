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

from extra_platforms import CLEARLINUX

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Swupd(PackageManager):
    """Clear Linux's software updater.

    Documentation:
    - https://github.com/clearlinux/swupd-client
    - https://www.clearlinux.org/

    swupd manages *bundles* (collections of files), not individually-versioned
    packages: bundles carry no version of their own and follow the single
    whole-system OS version.

    .. note::
        ``--quiet`` is swupd's blessed machine channel: data flows through its
        ``print()`` helper while decorations (headers, ``-`` prefixes, ``Total:``
        footers) flow through ``info()``, which ``--quiet`` drops. Every query below
        relies on it.

    .. note::
        Two operations are deliberately not implemented:

        - ``outdated``: ``swupd check-update`` reports a single whole-OS version
          delta through its *exit code* (``0`` when an update exists), not a
          per-bundle listing.
        - ``upgrade <bundle>``: bundles cannot be upgraded individually, only the
          whole OS via ``swupd update``.
    """

    name = "Clear Linux Software Updater"

    homepage_url = "https://github.com/clearlinux/swupd-client"

    platforms = CLEARLINUX

    default_sudo = True

    version_regexes = (r"swupd (?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ swupd --version
        swupd 7.0.0
           Copyright (C) 2012-2025 Intel Corporation
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed bundles.

        Bundles have no version, so packages are yielded without an
        ``installed_version``.

        .. code-block:: shell-session

            $ swupd bundle-list --quiet
            editors
            os-core
            os-core-update
        """
        output = self.run_cli("bundle-list", "--quiet")

        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching bundles.

        swupd has no bundle-name search: ``swupd search`` locates the bundle
        providing a *binary or library* (and needs the external ``swupd-search``
        tool), while ``search-file`` matches file paths. So the whole available
        bundle catalog is returned and
        :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`
        narrows it against the query.

        .. code-block:: shell-session

            $ swupd bundle-list --all --quiet
            curl
            editors
            os-core
        """
        output = self.run_cli("bundle-list", "--all", "--quiet")

        for line in output.splitlines():
            package_id = line.strip()
            if package_id:
                yield self.package(id=package_id)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one bundle.

        .. code-block:: shell-session

            $ sudo swupd bundle-add --assume=yes curl
        """
        return self.run_cli("bundle-add", "--assume=yes", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to update the whole OS to the latest version.

        .. code-block:: shell-session

            $ sudo swupd update --assume=yes
        """
        return self.build_cli("update", "--assume=yes", sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one bundle.

        .. code-block:: shell-session

            $ sudo swupd bundle-remove --assume=yes curl
        """
        return self.run_cli("bundle-remove", "--assume=yes", package_id, sudo=True)

    def cleanup(self) -> None:
        """Remove cached content used for updates from the state directory.

        .. code-block:: shell-session

            $ sudo swupd clean
            31 files removed
            1.5 MB freed
        """
        self.run_cli("clean", sudo=True)
