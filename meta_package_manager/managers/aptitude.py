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

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


NO_VERSION = "<none>"
"""Placeholder `%v` and `%V` render for a version that does not exist.

An uninstalled package has no current version, and a virtual one has no
candidate. Both print this literal rather than an empty field, so it has to be
mapped back to `None` instead of reaching a package record as a version string.
"""

_ERE_METACHARACTERS = r"\.^$*+?()[]{}|"
"""Characters carrying a special meaning in the POSIX extended regular
expressions aptitude compiles its `~n` and `~d` terms into.

Debian package names are drawn from `[a-z0-9+.-]`, so `+` and `.` are the two
that actually bite: a query for `libsigc++-2.0-0v5` compiles to a regex whose
`++` matches nothing at all, and one for `s.d` quietly matches `sed`.
"""


def escape_pattern(query: str) -> str:
    """Render `query` as a regex matching itself and nothing else.

    Two layers read the string, and each needs a different treatment:

    - aptitude's *pattern parser* splits a term at whitespace, so a two-word
      query becomes an implicit `AND` of two terms and matches nothing. A
      backslash cannot rescue it (the split happens first, leaving a trailing
      backslash the regex compiler rejects), so whitespace is rewritten as the
      `[[:space:]]` class, which carries no space to split on.
    - the *regex compiler* underneath, whose metacharacters are backslashed.

    Quoting the term instead (`~n"..."`) also survives whitespace, but the quote
    parser eats backslashes before the regex ever sees them, so the two
    mechanisms cannot be combined: `~n"^s\\.d$"` still matches `sed`.
    """
    escaped = "".join(
        f"\\{char}" if char in _ERE_METACHARACTERS else char for char in query
    )
    return re.sub(r"\s+", "[[:space:]]", escaped)


class Aptitude(PackageManager):
    """Front-end to Debian's `apt`, with a resolver and a query language of its own.

    Aptitude reaches the same archives `apt` does, over the same dpkg backend,
    and is wrapped on the same grounds as {class}`~meta_package_manager.managers.nala.Nala`:
    a distinct tool with a vocabulary of its own, rather than a translation
    layer over another CLI. It shares dpkg's lock with the rest of that family,
    so mpm runs it serially against them.

    ```{note}
    Every listing is a `search` over aptitude's own pattern language (`~i` for
    installed, `~U` for upgradable, `~i~g` for installed garbage) rendered
    through an explicit `--display-format`. That projection is what makes the
    output a flat `package,version` table instead of the padded columns the
    interactive interface draws.
    ```

    ```{caution}
    A query reaches aptitude as a *regular expression*, not as a literal
    substring, so it is escaped by {func}`escape_pattern` before being spliced
    into a `~n` or `~d` term. Skipping that step is not a near-miss but a silent
    empty result: `~n^libsigc++-2.0-0v5$` compiles to a regex matching no
    package at all.
    ```

    ```{note}
    `--disable-columns` is redundant on a pipe, aptitude having disabled
    columns on a redirection since `0.7.5`, and is passed anyway: that heuristic
    is a moving target (a later release narrowed it again for a caller setting a
    width explicitly), and the flag is what the manual's own example uses to ask
    for unformatted output.
    ```

    Documentation: [`aptitude(8)` man page](https://manpages.debian.org/unstable/aptitude/aptitude.8.en.html).
    """

    name = "aptitude"

    homepage_url = "https://salsa.debian.org/apt-team/aptitude"
    logo = "debian"

    platforms = UNIX_WITHOUT_MACOS

    default_sudo = True
    """Aptitude reports `are you root?` and exits rather than escalating on its
    own, so mpm supplies the privilege for the operations that mutate.
    """

    requirement = ">=0.4.11.4"
    """The release adding `--disable-columns`, announced in aptitude's own `NEWS`
    as a new `search` option. Every other option and pattern this class passes
    predates it, and every currently shipped distribution is far above it.
    """

    pre_args = ("--quiet", "--disable-columns")
    """`--quiet` drops the incremental progress indicators aptitude draws on a
    terminal; `--disable-columns` asks for unpadded, untruncated output.

    Source: [`aptitude(8)` options](https://manpages.debian.org/unstable/aptitude/aptitude.8.en.html).
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<package_id>[^,]+),(?P<installed_version>.+)$")
    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>[^,]+),(?P<installed_version>[^,]+),(?P<latest_version>.+)$"
    )
    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>[^,]+),(?P<latest_version>[^,]+),(?P<description>.*)$",
        # Unlike the two above, this one is walked over the whole output rather
        # than fed one line at a time by `parse_regex_lines`, so its anchors
        # need to bind to each line instead of to the string.
        re.MULTILINE,
    )
    """A comma joins the fields because neither a Debian package name
    (`[a-z0-9+.-]`) nor a version (`[0-9A-Za-z.+:~-]`) can contain one, while a
    space appears in every description and an epoch puts a colon in half the
    versions. It also keeps the disclosed `--display-format` free of spaces, so
    the command mpm prints can be pasted back into a shell unquoted.

    Only the description may hold a comma, so it is matched last and greedily.
    """

    version_regexes = (r"aptitude\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ aptitude --version
    aptitude 0.8.13
    Compiler: g++ 14.2.0
    Compiled against:
      apt version 7.0.0
      NCurses version 6.5
      libsigc++ version: 2.12.1
      Gtk+ support disabled.
      Qt support disabled.

    Current library versions:
      NCurses version: ncurses 6.5.20250216
      cwidget version: 0.5.18
      Apt version: 7.0.0
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~i --display-format %p,%v
        adduser,3.152
        apparmor,4.1.0-1
        apt,3.0.3
        apt-utils,3.0.3
        aptitude,0.8.13-7
        aptitude-common,0.8.13-7
        base-files,13.8+deb13u6
        base-passwd,3.6.7
        bash,5.2.37-2+b9
        bash-completion,1:2.16.0-7
        bsdutils,1:2.41-5
        busybox,1:1.37.0-6+b8
        bzip2,1.0.8-6
        ca-certificates,20250419
        ```
        """
        output = self.run_cli("search", "~i", "--display-format", "%p,%v")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `~U` matches an installed package having a newer candidate, so `%v` and
        `%V` are both populated and always differ.

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~U --display-format %p,%v,%V
        bsdutils,1:2.41-5,1:2.41.5-0+deb13u1
        eject,2.41-5,2.41.5-0+deb13u1
        fdisk,2.41-5,2.41.5-0+deb13u1
        libblkid1,2.41-5,2.41.5-0+deb13u1
        libexpat1,2.7.1-2,2.8.3-1~deb13u1
        libfdisk1,2.41-5,2.41.5-0+deb13u1
        liblastlog2-2,2.41-5,2.41.5-0+deb13u1
        libmount1,2.41-5,2.41.5-0+deb13u1
        libpython3.13-minimal,3.13.5-2+deb13u3,3.13.5-2+deb13u4
        libpython3.13-stdlib,3.13.5-2+deb13u3,3.13.5-2+deb13u4
        ```
        """
        output = self.run_cli("search", "~U", "--display-format", "%p,%v,%V")
        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    @property
    def orphans(self) -> Iterator[Package]:
        """Fetch packages installed as dependencies that nothing requires anymore.

        `~g` matches aptitude's garbage set, which also covers packages that are
        not installed at all, so it is intersected with `~i`. The result is the
        set `apt autoremove` would remove.

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~i~g --display-format %p,%v
        nyancat,1.5.2-0.3+b1
        ```
        """
        output = self.run_cli("search", "~i~g", "--display-format", "%p,%v")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        `~n` matches the name and `~d` the description, so an extended search is
        the union of the two and a plain one is the name term alone. An exact
        query anchors that term at both ends.

        A package with no candidate version renders `%V` as `<none>`: virtual
        packages match a name search and carry neither a version nor a
        description.

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~nabc --display-format %p,%V,%d
        abcde,2.9.3-1,A Better CD Encoder
        abcl,1.9.2-2,Common Lisp implementation in the Java Virtual Machine
        abcm2ps,8.14.17-2,Translates ABC music description files to PostScript
        abcmidi,20250216+ds-1,converter from ABC to MIDI format and back
        grabc,1.1+git20210125.b9e4316-2+b1,simple program to determine the color string in hex by clicking on a pixel
        libghc-directory-tree-dev-0.12.1-9dabc,<none>,
        libghc-directory-tree-prof-0.12.1-9dabc,<none>,
        node-lodash.kebabcase,<none>,
        node-types-lodash.kebabcase,<none>,
        python3-sabctools,8.2.3-2+b4,C implementations of functions for use within SABnzbd
        ```

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~n^sed$ --display-format %p,%V,%d
        sed,4.9-2+deb13u1,GNU stream editor for filtering/transforming text
        ```

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~nnyancat|~dnyancat --display-format %p,%V,%d
        nyancat,1.5.2-0.3+b1,Animated terminal Nyancat
        nyancat-server,1.5.2-0.3,Animated terminal Nyancat server configurations
        ```

        ```{code-block} shell-session

        $ aptitude --quiet --disable-columns search ~n^libsigc\\+\\+-2\\.0-0v5$ --display-format %p,%V,%d
        libsigc++-2.0-0v5,2.12.1-3,type-safe Signal Framework for C++ - runtime
        ```
        """
        pattern = escape_pattern(query)
        if exact:
            pattern = f"^{pattern}$"
        term = f"~n{pattern}"
        # Extended searches are always non-exact, so the description term can
        # never carry the anchors above.
        if extended and not exact:
            term = f"{term}|~d{pattern}"

        output = self.run_cli("search", term, "--display-format", "%p,%V,%d")

        for match in self._SEARCH_REGEXP.finditer(output):
            version = match.group("latest_version")
            yield self.package(
                id=match.group("package_id"),
                description=match.group("description"),
                latest_version=None if version == NO_VERSION else version,
            )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes install nyancat
        ```

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes install nyancat=1.5.2-0.3+b1
        ```
        """
        return self.run_cli(
            "--assume-yes",
            "install",
            f"{package_id}={version}" if version else package_id,
            sudo=True,
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        `safe-upgrade` never removes an installed package to resolve an upgrade,
        which is the conservatism `apt upgrade` has and `full-upgrade` drops.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes safe-upgrade
        ```
        """
        return self.build_cli("--assume-yes", "safe-upgrade", sudo=True)

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        Routed through `install`, which moves an already-installed package to
        the requested version, since naming a package on `safe-upgrade` still
        drags in every other member of its dependency cluster.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes install eject
        ```
        """
        return self.build_cli(
            "--assume-yes",
            "install",
            f"{package_id}={version}" if version else package_id,
            sudo=True,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes remove nyancat
        ```
        """
        return self.run_cli("--assume-yes", "remove", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns update
        ```
        """
        self.run_cli("update", sudo=True)

    def cleanup_orphan(self) -> None:
        """Remove every package installed as a dependency and no longer required.

        Aptitude has no `autoremove` verb: the garbage set is named as a pattern
        on `remove`, the same one {meth}`orphans` reports.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes remove ~i~g
        ```
        """
        self.run_cli("--assume-yes", "remove", "~i~g", sudo=True)

    def cleanup_cache(self) -> None:
        """Erase the downloaded package files.

        ```{code-block} shell-session

        $ sudo aptitude --quiet --disable-columns --assume-yes clean
        ```
        """
        self.run_cli("--assume-yes", "clean", sudo=True)
