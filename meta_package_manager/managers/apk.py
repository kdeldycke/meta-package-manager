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
import re

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..version import VersionRange

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class APK(PackageManager):
    """Alpine Package Keeper (`apk`) used by Alpine Linux.

    Documentation: [Alpine Package Keeper](https://wiki.alpinelinux.org/wiki/Alpine_Package_Keeper).

    ```{note}
    The version floor is `2.10.0`, the release introducing the `list` applet
    that {meth}`outdated` parses and {meth}`installed` falls back on. Where
    {attr}`query_requirement` is met, `installed` reads the structured `query`
    applet instead. Progress output is disabled on every call to keep the
    parsed lines stable.
    ```

    ```{caution}
    `outdated` reads the local repository cache rather than the remote, so
    `sync` must run first for an accurate upgrade list.
    ```

    ```{warning}
    `orphans` is deliberately not implemented, and `apk query --orphaned` must
    not be mapped onto it. The two words name different sets: mpm's orphan is a
    package installed as a dependency that nothing requires any more, where
    apk's is one no configured repository provides any more. Measured on Alpine
    `3.24.1` with apk-tools `3.0.8`: pointing apk at no repository
    (`--repositories-file /dev/null`) reports all 86 installed packages as
    orphaned, and the stock repositories report none, while a package dropped
    from `apk-world(5)` and required by nothing is never reported at all.
    Wiring that selector to `cleanup --orphans` would delete a working system
    whenever its mirrors were unreachable.
    ```
    """

    name = "Alpine apk"

    homepage_url = "https://gitlab.alpinelinux.org/alpine/apk-tools"
    logo = "alpinelinux"

    keywords = ("alpine", "alpine linux")

    platforms = LINUX_LIKE

    default_sudo = True

    requirement = ">=2.10.0"
    """The `list` applet, used by {meth}`installed` and {meth}`outdated`,
    was introduced in version `2.10.0`.
    """

    query_requirement = ">=3.0.0"
    """Minimum apk version answering the `query` applet.

    `apk-tools` 3 added `query`, which reports the same inventory as `list` does
    but in `json` or `yaml`, so {meth}`installed` reads names and versions
    outright instead of recovering them from a line's shape.

    Kept apart from {attr}`requirement` (`>=2.10.0`), following
    {attr}`Yay.cooldown_requirement
    <meta_package_manager.managers.pacman.Yay.cooldown_requirement>`, so an
    `apk-tools` 2 host keeps every operation through the `list` applet. Alpine
    `3.22` and older still ship `2.14`, and their support windows run into 2027.
    """

    pre_args = ("--no-progress",)
    """Suppress progress indicators so log lines are stable when parsing.

    Source: `apk(8)` global options.
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<pkgver>\S+)\s.+\[installed\]\s*$",
        re.MULTILINE,
    )
    """Match installed entries from `apk list --installed` output.

    Each line has the format
    ``<pkgver> <arch> {<origin>} (<license>) [installed]``.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<pkgver>\S+)\s.+\[upgradable from:\s+(?P<from_pkgver>\S+)\]\s*$",
        re.MULTILINE,
    )
    """Match upgradable entries from `apk list --upgradable` output.

    Each line has the format
    ``<pkgver> <arch> {<origin>} (<license>) [upgradable from: <pkgver>]``.
    """

    version_regexes = (r"apk-tools\s+(?P<version>[^\s,]+)",)
    """
    ```{code-block} shell-session

    $ apk --version
    apk-tools 2.14.10, compiled for x86_64.
    ```
    """

    @property
    def _has_query_applet(self) -> bool:
        """Whether this apk is known to answer the `query` applet.

        An undetectable version answers `False`, which only picks the `list`
        dialect of {meth}`installed`: a manager whose version never resolved
        fails {attr}`~meta_package_manager.manager.PackageManager.fresh` and so
        runs no operation on a real host.
        """
        if self.version is None:
            return False
        return self.version in VersionRange(self.query_requirement)

    @staticmethod
    def _parse_query_json(output: str) -> tuple[tuple[str, str], ...]:
        """Extract `(name, version)` pairs from a `query --format json` payload.

        An empty selection prints `[]`, and a refusal (an `apk-tools` 2 meeting
        the applet, a repository it cannot reach) prints no JSON at all. Both
        yield nothing rather than raising, so a caller reports an empty set the
        way every other parser here does.
        """
        try:
            entries = json.loads(output)
        except ValueError:
            logging.debug("apk query returned no JSON payload.")
            return ()
        if not isinstance(entries, list):
            logging.debug("apk query returned JSON that is not a list of packages.")
            return ()
        return tuple(
            (entry["name"], entry["version"])
            for entry in entries
            if isinstance(entry, dict) and entry.get("name") and entry.get("version")
        )

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        `apk-tools` 3 answers the `query` applet, whose `json` payload names and
        versions each package outright, so nothing has to be recovered from a
        line's shape. The pattern is mandatory, an empty selection matching
        nothing rather than everything.

        ```{code-block} shell-session

        $ apk --no-progress query --installed --fields name,version --format json '*'
        [
          {
            "name": "alpine-base",
            "version": "3.24.1-r0"
          }, {
            "name": "apk-tools",
            "version": "3.0.8-r0"
          }, {
            "name": "busybox",
            "version": "1.37.0-r31"
          }
        ]
        ```

        `apk-tools` 2 has no `query`, and gets the `list` applet instead:

        ```{code-block} shell-session

        $ apk --no-progress list --installed
        acl-2.2.53-r0 x86_64 {acl} (LGPL-2.1-or-later AND GPL-2.0-or-later) [installed]
        alpine-baselayout-3.4.3-r1 x86_64 {alpine-baselayout} (GPL-2.0-only) [installed]
        apk-tools-2.14.0-r5 x86_64 {apk-tools} (GPL-2.0-only) [installed]
        busybox-1.36.1-r5 x86_64 {busybox} (GPL-2.0-only) [installed]
        python3-3.11.6-r0 x86_64 {python3} (PSF-2.0) [installed]
        ```

        Which dialect to *ask* for is decided by {attr}`_has_query_applet`, but
        both are parsed whatever the host, keyed on the payload being JSON. That
        is what lets each documented block above stand as a fixture, and it
        keeps the reading of an answer independent of the guess that produced
        it.
        """
        if self._has_query_applet:
            output = self.run_cli(
                "query",
                "--installed",
                "--fields",
                "name,version",
                "--format",
                "json",
                "*",
            )
        else:
            output = self.run_cli("list", "--installed")

        if output.lstrip().startswith("["):
            for package_id, version in self._parse_query_json(output):
                yield self.package(id=package_id, installed_version=version)
            return

        for match in self._INSTALLED_REGEXP.finditer(output):
            if split := self.split_name_version(match.group("pkgver")):
                package_id, version = split
                yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{caution}
        Reads from the local repository cache. Run {meth}`sync` first
        to refresh the index.
        ```

        ```{code-block} shell-session

        $ apk --no-progress list --upgradable
        acl-2.3.1-r0 x86_64 {acl} (LGPL-2.1-or-later) [upgradable from: acl-2.2.53-r0]
        python3-3.11.7-r0 x86_64 {python3} (PSF-2.0) [upgradable from: python3-3.11.6-r0]
        ```
        """
        output = self.run_cli("list", "--upgradable")

        for match in self._OUTDATED_REGEXP.finditer(output):
            new_split = self.split_name_version(match.group("pkgver"))
            old_split = self.split_name_version(match.group("from_pkgver"))
            if new_split and old_split:
                yield self.package(
                    id=new_split[0],
                    installed_version=old_split[1],
                    latest_version=new_split[1],
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        `apk search` matches package names with case-insensitive
        substring globbing. Exact matching is not supported and is
        handled by
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`.
        Extended search adds the `--description` flag so the query is
        also matched against package descriptions.
        ```

        `apk-tools` 2 prints the bare name and version:

        ```{code-block} shell-session

        $ apk --no-progress search --verbose firefox
        firefox-120.0-r0
        firefox-esr-115.5.0-r0
        firefox-langpack-de-120.0-r0
        ```

        ```{code-block} shell-session

        $ apk --no-progress search --verbose --description ntp
        chrony-4.4-r1
        ntp-4.2.8_p17-r0
        openntpd-6.8_p1-r1
        ```

        `apk-tools` 3 appends each package's description, so only the first
        whitespace-delimited token is the name and version:

        ```{code-block} shell-session

        $ apk --no-progress search --verbose curl
        curl-8.21.0-r0 - URL retrieval utility and library
        curl-dev-8.21.0-r0 - URL retrieval utility and library (development files)
        curl-doc-8.21.0-r0 - URL retrieval utility and library (documentation)
        ```
        """
        args = ["search", "--verbose"]
        if extended:
            args.append("--description")
        args.append(query)
        output = self.run_cli(*args)

        for line in output.splitlines():
            # The first token covers both dialects: the whole line on
            # apk-tools 2, the name-version ahead of the description on 3.
            token = line.split(maxsplit=1)[0] if line.strip() else ""
            if split := self.split_name_version(token):
                package_id, version = split
                yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo apk --no-progress add firefox
        ```
        """
        return self.run_cli("add", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ sudo apk --no-progress upgrade
        ```
        """
        return self.build_cli("upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        ```{code-block} shell-session

        $ sudo apk --no-progress upgrade firefox
        ```
        """
        return self.build_cli("upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo apk --no-progress del firefox
        ```
        """
        return self.run_cli("del", package_id, sudo=True)

    def sync(self) -> None:
        """Synchronize the local package index from remote repositories.

        ```{code-block} shell-session

        $ sudo apk --no-progress update
        ```
        """
        self.run_cli("update", sudo=True)

    def cleanup_cache(self) -> None:
        """Drop the local package cache.

        ```{code-block} shell-session

        $ sudo apk --no-progress cache clean
        ```
        """
        self.run_cli("cache", "clean", sudo=True)
