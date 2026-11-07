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

from extra_platforms import UNIX_WITHOUT_MACOS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Pmerge(PackageManager):
    """pkgcore's `pmerge`, an alternative package manager for Gentoo.

    pkgcore reads the same ebuild repositories as Portage and records into the
    same database of installed packages. On a host that carries both, this
    manager and [`emerge`](emerge.md) list the same packages, and each one sees
    what the other installed.

    The queries run through `pquery`, the inventory and search tool of pkgcore,
    and the maintenance through `pmaint` and `pclean`. All four ship together.

    :::{caution}
    Installs and upgrades compile from source, so their duration comes from the
    package rather than from the network. A small program finishes well inside
    the 500 second ceiling `mpm` puts on a state-changing command, where a
    compiler or a browser does not. Raise the ceiling for this manager alone, in
    the configuration file:

    ```toml
    [mpm.overrides.pmerge]
    timeout = 14400
    ```
    :::
    """

    name = "pkgcore pmerge"

    documentation_url = "https://pkgcore.github.io/pkgcore/man/pmerge.html"
    repository_url = "https://github.com/pkgcore/pkgcore"
    logo = "gentoo"

    keywords = ("pkgcore",)

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True
    privileged_operations = frozenset(
        {"cleanup", "install", "remove", "sync", "upgrade", "upgrade_all"},
    )

    # `pquery --format`, which every query below prints its rows with, first
    # shipped in pkgcore 0.12.29.
    requirement = ">=0.12.29"

    # A base option of all four pkgcore tools, so it reaches the siblings too.
    pre_args = ("--color", "no")

    version_regexes = (r"pkgcore\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ pmerge --version
    pkgcore 0.12.48
    ```
    """

    _INSTALLED_FORMAT = "{category}/{package}={fullver}"
    """`pquery` row of the inventory, free of spaces so the disclosed command
    replays as printed."""

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>[^=\s]+)=(?P<installed_version>\S+)$",
    )

    _SLOTTED_FORMAT = "{category}/{package}:{slot}={fullver}"
    """`pquery` row carrying the slot, the key `outdated` joins its two listings
    on: `pquery --upgrade` compares each installed package with the best version
    of its own slot."""

    _SLOTTED_REGEXP = re.compile(
        r"^(?P<package_id>[^:\s]+):(?P<slot>[^=\s]+)=(?P<version>\S+)$",
        re.MULTILINE,
    )

    _SEARCH_FORMAT = "{category}/{package}={fullver}={description}"

    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>[^=\s]+)=(?P<latest_version>[^=\s]+)"
        r"=(?P<description>.*)$",
        re.MULTILINE,
    )

    _ORPHANS_REGEXP = re.compile(
        r"^Remove installed pkg: (?P<cpv>[^:\s]+)::",
        re.MULTILINE,
    )
    """`--pretend --clean` prints each package it would remove as `Remove`
    followed by the package object, whose `category/name-version` is split
    downstream through
    {meth}`~meta_package_manager.manager.PackageManager.split_name_version`."""

    _REGEX_METACHARACTERS = re.compile(r"([\\.^$*+?{}\[\]|()])")
    """Characters `pquery --description` reads as regular expression syntax.

    Narrower than {func}`re.escape`, which also escapes `-` and spaces: a
    regular expression reads both literally outside a character class, and the
    disclosed command stays as the user typed it."""

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        A package installed in several slots is listed once per slot.

        ```{code-block} shell-session

        $ pquery --color no --installed --format {category}/{package}={fullver}
        app-text/build-docbook-catalog=2.4
        app-text/docbook-xml-dtd=4.1.2-r7
        app-text/docbook-xml-dtd=4.2-r3
        app-text/docbook-xml-dtd=4.5-r2
        app-text/docbook-xsl-ns-stylesheets=1.79.1
        app-text/docbook-xsl-stylesheets=1.79.1-r4
        app-text/manpager=1
        ```
        """
        output = self.run_cli(
            "--installed",
            "--format",
            self._INSTALLED_FORMAT,
            override_cli_path=self.sibling_cli("pquery", same_dir=True),
            must_succeed=True,
        )
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `pquery --upgrade` prints the best version of each slot that has a newer
        one than the version installed in it, but not the installed version. The
        inventory supplies it, joined on the package and its slot.

        ```{code-block} shell-session

        $ pquery --color no --installed --format {category}/{package}:{slot}={fullver}
        app-arch/libarchive:0=3.8.10
        app-arch/tar:0=1.35-r1
        app-arch/unzip:0=6.0_p31
        app-arch/xz-utils:0=5.8.3
        app-arch/zstd:0=1.5.7-r1
        app-crypt/gnupg:0=2.5.24-r2
        app-crypt/gpgme:1=2.2.0
        app-crypt/libb2:0=0.98.1-r3
        app-crypt/libmd:0=1.2.0
        ```

        ```{code-block} shell-session

        $ pquery --color no --upgrade --format {category}/{package}:{slot}={fullver}
        app-arch/libarchive:0=3.8.11
        app-arch/xz-utils:0=5.8.4
        app-crypt/libmd:0=1.3.0
        ```
        """
        pquery_path = self.sibling_cli("pquery", same_dir=True)
        installed = {
            (match["package_id"], match["slot"]): match["version"]
            for match in self._SLOTTED_REGEXP.finditer(
                self.run_cli(
                    "--installed",
                    "--format",
                    self._SLOTTED_FORMAT,
                    override_cli_path=pquery_path,
                    auto_extra_args=False,
                    must_succeed=True,
                )
            )
        }
        output = self.run_cli(
            "--upgrade",
            "--format",
            self._SLOTTED_FORMAT,
            override_cli_path=pquery_path,
            auto_extra_args=True,
            must_succeed=True,
        )
        for match in self._SLOTTED_REGEXP.finditer(output):
            yield self.package(
                id=match["package_id"],
                installed_version=installed.get((match["package_id"], match["slot"])),
                latest_version=match["version"],
            )

    @property
    def orphans(self) -> Iterator[Package]:
        """Fetch packages that neither the `@world` nor the `@system` set needs.

        `--pretend` turns the `--clean` sweep into a read-only report. With an
        empty `@world`, as on a fresh stage3, everything outside `@system` and
        its dependencies is reported.

        ```{code-block} shell-session

        $ pmerge --color no --pretend --clean
         * Packages to be removed:
        Remove installed pkg: app-alternatives/lex-0-r1::vdb, source repo 'gentoo'
        Remove installed pkg: app-alternatives/ninja-1::vdb, source repo 'gentoo'
        Remove installed pkg: app-alternatives/yacc-1-r2::vdb, source repo 'gentoo'
        Remove installed pkg: app-arch/unzip-6.0_p31::vdb, source repo 'gentoo'
        ```
        """
        output = self.run_cli("--pretend", "--clean", must_succeed=True)
        for match in self._ORPHANS_REGEXP.finditer(output):
            if split := self.split_name_version(match["cpv"]):
                package_id, version = split
                yield self.package(id=package_id, installed_version=version)

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        A query matches package names, and is a glob around the query unless the
        search is exact. An extended search adds a second call, matching the
        query against descriptions: it reads the metadata of the whole
        repository, and is the slow part.

        ```{code-block} shell-session

        $ pquery --color no --max --format {category}/{package}={fullver}={description} nyancat
        games-misc/nyancat=1.5.2=Nyancat in your terminal, rendered through ANSI escape sequences
        ```

        ```{code-block} shell-session

        $ pquery --color no --max --format {category}/{package}={fullver}={description} *cowsay*
        games-misc/cowsay=3.7.0=Configurable talking ASCII cow (and other characters)
        games-misc/xcowsay=1.6=Displays a cute cow and message on your desktop
        ```

        ```{code-block} shell-session

        $ pquery --color no --max --format {category}/{package}={fullver}={description} --description 'ANSI escape'
        app-misc/color=1.2-r3=Easily add ANSI colouring to shell scripts
        app-text/aha=0.5.1=Converts ANSI escape sequences of a unix terminal to HTML code
        app-vim/ansiesc=12=vim plugin: ansi escape sequences concealed, but highlighted as specified
        dev-java/jansi=2.4.1=A java library for generating and interpreting ANSI escape sequences
        dev-libs/libuv=1.52.1=Cross-platform asynchronous I/O
        dev-perl/Term-ANSIScreen=1.500.0-r2=Terminal control using ANSI escape sequences
        dev-python/colorama=0.4.6=ANSI escape character sequences for colored terminal text & cursor positioning
        dev-ruby/term-ansicolor=1.11.3-r1=Small Ruby library that colors strings using ANSI escape sequences
        games-misc/nyancat=1.5.2=Nyancat in your terminal, rendered through ANSI escape sequences
        ```
        """  # noqa: E501
        pquery_path = self.sibling_cli("pquery", same_dir=True)
        targets: list[tuple[str, ...]] = [(query if exact else f"*{query}*",)]
        if extended:
            targets.append((
                "--description",
                self._REGEX_METACHARACTERS.sub(r"\\\1", query),
            ))
        seen = set()
        for target in targets:
            output = self.run_cli(
                "--max",
                "--format",
                self._SEARCH_FORMAT,
                *target,
                override_cli_path=pquery_path,
                auto_extra_args=True,
                must_succeed=True,
            )
            for match in self._SEARCH_REGEXP.finditer(output):
                if match["package_id"] in seen:
                    continue
                seen.add(match["package_id"])
                yield self.package(
                    id=match["package_id"],
                    description=match["description"],
                    latest_version=match["latest_version"],
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, and record it in the `@world` set.

        ```{code-block} shell-session

        $ sudo pmerge --color no games-misc/nyancat
        ```
        """
        return self.run_cli(package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        The `@system` set rides along with `@world`: `pmerge` refuses an empty
        target list, and a fresh stage3 records nothing in `@world`.

        ```{code-block} shell-session

        $ sudo pmerge --color no --upgrade --deep --newuse @world @system
        ```
        """
        return self.build_cli(
            "--upgrade",
            "--deep",
            "--newuse",
            "@world",
            "@system",
            sudo=True,
        )

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        `--upgrade` leaves a package that is already current alone, and does not
        add it to the `@world` set.

        ```{code-block} shell-session

        $ sudo pmerge --color no --upgrade app-crypt/libmd
        ```
        """
        return self.build_cli("--upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package, and drop it from the `@world` set.

        ```{code-block} shell-session

        $ sudo pmerge --color no --unmerge games-misc/nyancat
        ```
        """
        return self.run_cli("--unmerge", package_id, sudo=True)

    def sync(self) -> None:
        """Sync every configured repository.

        ```{code-block} shell-session

        $ sudo pmaint --color no sync
        *** syncing gentoo
        *** synced gentoo
        ```
        """
        self.run_cli(
            "sync",
            override_cli_path=self.sibling_cli("pmaint", same_dir=True),
            sudo=True,
        )

    def cleanup_orphan(self) -> None:
        """Remove every package outside the `@world` and `@system` sets.

        ```{code-block} shell-session

        $ sudo pmerge --color no --clean
        ```
        """
        self.run_cli("--clean", sudo=True)

    def cleanup_cache(self) -> None:
        """Remove the source distfiles no installed package uses.

        ```{code-block} shell-session

        $ sudo pclean --color no dist --installed
        ```
        """
        self.run_cli(
            "dist",
            "--installed",
            override_cli_path=self.sibling_cli("pclean", same_dir=True),
            sudo=True,
        )
