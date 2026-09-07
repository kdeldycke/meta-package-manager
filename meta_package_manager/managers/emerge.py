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


class Emerge(PackageManager):
    """Portage's `emerge`, Gentoo's source-based package manager.

    Documentation: [`emerge(1)` man page](https://dev.gentoo.org/~zmedico/portage/doc/man/emerge.1.html).

    Command equivalences with other managers are listed in
    [Pacman/Rosetta](https://wiki.archlinux.org/title/Pacman/Rosetta).

    The outdated listing and the whole-system upgrade operate against the
    `@world` set. The progress spinner and ANSI coloring are disabled on every
    call, leaving output the regexes can parse.

    ```{note}
    Two operations lean on companion Portage tools rather than `emerge`
    itself: `installed` reads the package list through `qlist` and
    `cleanup` trims distfiles through `eclean`. Neither is resolved
    through {attr}`cli_path
    <meta_package_manager.execution.CLIExecutor.cli_path>` the way the
    reference `emerge` binary is; both are expected on the `PATH`.
    ```

    ```{warning}
    `cleanup` forces a full `@world` upgrade before running
    `--depclean`: Portage refuses to remove packages until every
    dependency is resolved, so depcleaning a partially-upgraded system
    could drop still-needed packages.
    ```
    """

    name = "Gentoo emerge"

    homepage_url = "https://wiki.gentoo.org/wiki/Portage#emerge"
    logo = "gentoo"

    keywords = ("gentoo", "portage")

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True

    requirement = ">=3.0.0"

    pre_args = ("--quiet", "--color", "n", "--nospinner")

    _PARSED_PRE_ARGS = tuple(arg for arg in pre_args if arg != "--quiet")
    """{attr}`pre_args` without `--quiet`, for the operations whose output a
    regex reads instead of a person.

    `--quiet` does not only drop noise, it changes the shape of what emerge
    prints. `--search` collapses each hit to a bare `*  category/name` line,
    losing the `Latest version available:` and `Description:` fields
    {attr}`_SEARCH_REGEXP` needs. `--update --columns` drops the
    `[ebuild   U  ]` state prefix and leaves the latest version unbracketed,
    which are the two things {attr}`_OUTDATED_REGEXP` anchors on. Either regex
    then matches nothing, and the operation reports an empty set on a system
    that has results.
    """

    _INSTALLED_REGEXP = re.compile(
        r"""
        (?P<package_id>        # Named group must not split (?P< across lines.
            \S+                # Non-whitespace string...
            (?!-r)             # ...if not directly followed by the "-r" string.
        )
        -                      # A dash.
        (?P<installed_version> # Named group must not split (?P< across lines.
            [^\s-]+            # Any non-whitespace/non-dash string.
            (?:-r\d+)?         # Optional revision suffix led by a -, non-grouped.
        )
        """,
        re.VERBOSE,
    )
    _OUTDATED_REGEXP = re.compile(
        r"""
        \[.+\]                               # Update state.
        \                                    # A space.
        (?P<package_id>\S+)                  # Non-whitespace string.
        \s+                                  # Any spacing.
        (?:\[                                # Non-matching group
                                             #   starting with a '['.
            (?P<latest_version>[^\s\/:]+)    # Any non-spaced string
                                             #   until a ':' or '/' is met.
            \S*                              # Left-over parts of the version,
                                             #   after a ':' or '/'.
        \])?                                 # Optional group ending with a ']'.
        \s+                                  # Any spacing.
        (?:\[                                # Non-matching group
                                             #   starting with a '['.
            (?P<installed_version>[^\s\/:]+) # Any non-spaced string
                                             #   until a ':' or '/' is met.
            \S*                              # Left-over parts of the version,
                                             #   after a ':' or '/'.
        \])?                                 # Optional group ending with a ']'.
        """,
        re.VERBOSE,
    )
    _ORPHANS_REGEXP = re.compile(
        r"^All selected packages:\s+(?P<atoms>.+)$",
        re.MULTILINE,
    )
    """Match `--depclean --pretend`'s one-line summary of the packages it would
    unmerge, each an `=<category/name>-<version>` atom split downstream through
    {meth}`~meta_package_manager.manager.PackageManager.split_name_version`."""
    _SEARCH_REGEXP = re.compile(
        r"""
        ^\*\s+(?P<package_id>\S+)\n
        \s+Latest\ version\ available:\s+(?P<latest_version>\S+)\n
        (?:\s+.+\n)+?
        \s+Description:\s+(?P<description>.+)\n
        """,
        re.MULTILINE | re.VERBOSE,
    )

    version_regexes = (r"Portage\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ emerge --version
    Portage 3.0.81.3 (python 3.14.7-final-0, default/linux/arm64/23.0, gcc-15, glibc-2.43-r2, 6.18.48-gentoo-dist-bin aarch64)
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{warning}
        This suppose the `qlist` binary is available and present on the system. We
        do not search for it or try to resolves its canonical path with
        {attr}`cli_path
        <meta_package_manager.execution.CLIExecutor.cli_path>`, as we do for the
        reference `emerge` binary.
        ```

        ```{code-block} shell-session

        $ qlist --installed --verbose --nocolor
        app-admin/sudo-1.9.17_p2
        app-alternatives/awk-4
        app-arch/unzip-6.0_p29-r2
        app-misc/pax-utils-1.3.10
        app-misc/tmux-3.5a
        app-shells/bash-5.3_p15
        dev-perl/Locale-gettext-1.70.0_p20181130
        dev-perl/SGMLSpm-1.1-r2
        ```
        """
        qlist_path = self.sibling_cli("qlist")

        output = self.run_cli(
            "--installed",
            "--verbose",
            "--nocolor",
            override_cli_path=qlist_path,
            auto_pre_args=False,
        )

        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Runs without `--quiet`, which would drop the `[ebuild   U  ]` state
        prefix and unbracket the latest version. See {attr}`_PARSED_PRE_ARGS`.

        ```{code-block} shell-session

        $ emerge --color n --nospinner --update --deep --pretend --columns @world
        [ebuild     U  ] sys-process/htop                                      [3.5.3]                      [3.5.1]
        [binary    gU  ] app-editors/nano                                      [9.2-1]                      [9.1]
        ```
        """
        output = self.run_cli(
            "--update",
            "--deep",
            "--pretend",
            "--columns",
            "@world",
            override_pre_args=self._PARSED_PRE_ARGS,
        )

        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    @property
    def orphans(self) -> Iterator[Package]:
        """Fetch packages installed as dependencies that nothing requires anymore.

        `--pretend` turns `--depclean` into a read-only report of the packages
        it would unmerge, summarized on its `All selected packages:` line as
        `=<category/name>-<version>` atoms. Runs without root, and without the
        pre-depclean world upgrade {meth}`cleanup_orphan` performs before a real
        sweep.

        ```{code-block} shell-session

        $ emerge --quiet --color n --nospinner --depclean --pretend
        app-misc/tmux: 3.5a none none
        dev-libs/libevent: 2.1.13 none none

        All selected packages: =app-misc/tmux-3.5a =dev-libs/libevent-2.1.13
        Packages installed:   327
        Packages in world:    8
        Packages in system:   50
        Required packages:    325
        Number to remove:     2
        ```
        """
        output = self.run_cli("--depclean", "--pretend")

        match = self._ORPHANS_REGEXP.search(output)
        if not match:
            return
        for atom in match.group("atoms").split():
            if split := self.split_name_version(atom.lstrip("=")):
                package_id, version = split
                yield self.package(id=package_id, installed_version=version)

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Runs without `--quiet`, which would collapse each hit to a bare
        `*  category/name` line and strip the two fields
        {attr}`_SEARCH_REGEXP` reads. See {attr}`_PARSED_PRE_ARGS`.

        ```{code-block} shell-session

        $ emerge --color n --nospinner --search %^(htop|tmux)$
        [ Results for search key : %^(htop|tmux)$ ]
        Searching...

        *  app-misc/tmux
              Latest version available: 3.5a
              Latest version installed: 3.5a
              Size of files: 699 KiB
              Homepage:      https://tmux.github.io/
              Description:   Terminal multiplexer
              License:       ISC

        *  sys-process/htop
              Latest version available: 3.5.3
              Latest version installed: 3.5.1
              Size of files: 465 KiB
              Homepage:      https://htop.dev/ https://github.com/htop-dev/htop
              Description:   Interactive process viewer
              License:       GPL-2+

        [ Applications found : 2 ]
        ```

        ```{code-block} shell-session

        $ emerge --color n --nospinner --search sed
        ```

        ```{code-block} shell-session

        $ emerge --color n --nospinner --searchdesc sed
        ```

        ```{code-block} shell-session

        $ emerge --color n --nospinner --searchdesc %^sed$
        ```
        """
        search_param = "--search"
        if extended:
            search_param = "--searchdesc"

        if exact:
            query = f"%^{query}$"

        output = self.run_cli(
            search_param, query, override_pre_args=self._PARSED_PRE_ARGS
        )

        for package_id, version, description in self._SEARCH_REGEXP.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner dev-vcs/git
        ```
        """
        return self.run_cli(package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner --update --newuse --deep @world
        ```
        """
        return self.build_cli(
            "--update",
            "--newuse",
            "--deep",
            "@world",
            sudo=True,
        )

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner --update dev-vcs/git
        ```
        """
        return self.build_cli(
            "--update",
            package_id,
            sudo=True,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner --unmerge dev-vcs/git
        ```
        """
        return self.run_cli("--unmerge", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner --sync
        ```
        """
        self.run_cli("--sync", sudo=True)

    def cleanup_orphan(self) -> None:
        """Remove every package not required by the world set anymore.

        An update is forced before depcleaning, as [pointed to by the emerge documentation](https://wiki.gentoo.org/wiki/Gentoo_Cheat_Sheet):

        > As a safety measure, depclean will not remove any packages unless *all*
        > required dependencies have been resolved. As a consequence, it is often
        > necessary to run `emerge --update --newuse --deep @world` prior to depclean.

        ```{code-block} shell-session

        $ sudo emerge --quiet --color n --nospinner --update --newuse --deep @world
        $ sudo emerge --quiet --color n --nospinner --depclean
        ```
        """
        # Forces an upgrade first, as recommended by emerge documentation.
        self.upgrade()

        self.run_cli("--depclean", sudo=True)

    def cleanup_cache(self) -> None:
        """Trim the source distfiles through `eclean`.

        ```{warning}
        This suppose the `eclean` binary is available and present on the system.
        We do not search for it or try to resolves its canonical path with
        {attr}`cli_path
        <meta_package_manager.execution.CLIExecutor.cli_path>`, as we do for the
        reference `emerge` binary.
        ```

        ```{code-block} shell-session

        $ sudo eclean distfiles
        ```
        """
        eclean_path = self.which("eclean")
        if eclean_path:
            self.run_cli(
                "distfiles",
                override_cli_path=eclean_path,
                auto_pre_args=False,
                sudo=True,
            )
