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

from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class ASDF(PackageManager):
    """asdf manages parallel versions of multiple developer tools (Node.js,
    Ruby, Python, Erlang, ...) through a plugin ecosystem, exposing all of
    them behind a single CLI.

    .. note::
        asdf is plugin-driven: every tool the user can install is gated
        behind a plugin (``asdf plugin add nodejs``). ``mpm install`` does
        not auto-add plugins; the user is expected to register them first
        with ``asdf plugin add``.

    .. note::
        Each ``(plugin, installed_version)`` pair is reported as a
        distinct package, so a tool installed at multiple versions yields
        multiple entries sharing the same ID.

    .. caution::
        ``mpm outdated`` only reports tools that have a currently-active
        version (marked with ``*`` in ``asdf list``) different from their
        latest stable release. A tool installed without being activated
        through a ``.tool-versions`` file does not surface as outdated.
    """

    name = "asdf"

    homepage_url = "https://asdf-vm.com"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=0.16.0"
    """The Go rewrite shipped in ``0.16.0`` on 2025-01-30 replaced the
    hyphenated subcommands (``asdf list-all``, ``asdf plugin-add``, ...)
    with their space-separated equivalents this wrapper depends on
    (``asdf list all``, ``asdf plugin add``, ...). Older Bash-based
    releases are not supported.
    """

    version_cli_options = ("version",)

    version_regexes = (r"v?(?P<version>\d+\.\d+\.\d+)",)
    """
    .. code-block:: shell-session

        $ asdf version
        v0.19.0-83adfe6
    """

    _LATEST_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+(?P<latest_version>\S+)\s+(installed|missing)\s*$",
        re.MULTILINE,
    )

    _PLUGIN_LIST_ALL_REGEXP = re.compile(
        r"^(?P<package_id>\S+)(?:\s+(?P<description>.+?))?\s*$",
        re.MULTILINE,
    )

    def _parse_list(self) -> Iterator[tuple[str, str, bool]]:
        """Parse ``asdf list`` output into ``(plugin, version, is_current)``
        tuples.

        Non-indented lines are plugin headers. Lines that start with two
        spaces are installed-but-not-current versions; lines that start
        with a space and ``*`` are the active version.
        """
        output = self.run_cli("list")
        current_plugin: str | None = None
        for line in output.splitlines():
            if not line:
                continue
            if not line.startswith(" "):
                current_plugin = line.strip()
                continue
            if current_plugin is None:
                continue
            is_current = line.startswith(" *")
            version = line.lstrip(" *").strip()
            if version:
                yield current_plugin, version, is_current

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Emits one :py:class:`meta_package_manager.package.Package` per
        ``(plugin, installed_version)`` pair, so a tool installed at
        multiple versions yields multiple entries sharing the same ID.

        .. code-block:: shell-session

            $ asdf list
            nodejs
              18.20.4
             *20.10.0
            ruby
             *3.2.0
        """
        for plugin, version, _ in self._parse_list():
            yield self.package(id=plugin, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Cross-references the currently-active version per plugin (the
        entry marked with ``*`` in ``asdf list``) with the latest stable
        version (``asdf latest --all``). Only plugins whose active
        version differs from the latest are yielded.

        .. code-block:: shell-session

            $ asdf latest --all
            nodejs    20.10.0    missing
            ruby      3.3.0      missing
        """
        current_versions: dict[str, str] = {
            plugin: version
            for plugin, version, is_current in self._parse_list()
            if is_current
        }

        latest_output = self.run_cli("latest", "--all")
        for match in self._LATEST_REGEXP.finditer(latest_output):
            plugin = match.group("package_id")
            latest = match.group("latest_version")
            installed = current_versions.get(plugin)
            if installed and installed != latest:
                yield self.package(
                    id=plugin,
                    installed_version=installed,
                    latest_version=latest,
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ``asdf plugin list all`` enumerates the entire short-name plugin
        catalogue. The framework's
        :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`
        narrows the listing down to entries that contain the query.

        .. code-block:: shell-session

            $ asdf plugin list all
            1password-cli   https://github.com/NeoHsu/asdf-1password-cli.git
            act             https://github.com/grimoh/asdf-act.git
            nodejs          https://github.com/asdf-vm/asdf-nodejs.git
        """
        output = self.run_cli("plugin", "list", "all")
        for match in self._PLUGIN_LIST_ALL_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                description=match.group("description"),
            )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ``asdf install <plugin>`` requires the plugin to have been added
        beforehand with ``asdf plugin add <plugin>``. This wrapper does
        not auto-add plugins.

        .. code-block:: shell-session

            $ asdf install nodejs 20.10.0
        """
        return self.run_cli("install", package_id, version or "latest")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        asdf has no native upgrade verb: installing the ``latest`` alias
        downloads the newest stable release alongside any older versions
        already on disk. The user is responsible for switching the
        active version with ``asdf set`` if desired.

        .. code-block:: shell-session

            $ asdf install nodejs latest
        """
        return self.build_cli("install", package_id, "latest")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ``asdf plugin remove`` deletes the plugin and every version of
        the tool installed through it, which matches ``mpm``'s
        "remove this package" contract more cleanly than iterating
        ``asdf uninstall`` per installed version.

        .. code-block:: shell-session

            $ asdf plugin remove nodejs
        """
        return self.run_cli("plugin", "remove", package_id)

    def sync(self) -> None:
        """Refresh plugin metadata.

        .. code-block:: shell-session

            $ asdf plugin update --all
        """
        self.run_cli("plugin", "update", "--all")
