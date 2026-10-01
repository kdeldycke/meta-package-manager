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

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Guix(PackageManager):
    """GNU Guix, GNU's functional package manager.

    ```{note}
    All operations target the current user's default profile. Declarative
    system configuration (Guix System `config.scm`) is not covered.
    ```

    Guix is a rolling release with no upstream semver to pin against: the `guix`
    of a fresh install reports its release, and once `guix pull` ran, the commit it
    was built from. No `requirement` floor is enforced, since any working `guix`
    will do.

    :::{caution}
    `sync` runs `guix pull`, which outlasts the 500 second ceiling `mpm` puts on a
    state-changing command. A first pull authenticates the commit history of the
    channel, then builds Guix itself when no substitute is available yet: on an
    `aarch64` virtual machine, it took 28 minutes. Raise the ceiling for this
    manager alone, in the configuration file:

    ```toml
    [mpm.overrides.guix]
    timeout = 3600
    ```
    :::

    ```{note}
    `guix pull` builds a cache of the package set, so `search` answers in about a
    second. A `guix` run from a development checkout has no such cache and
    evaluates every package definition instead: there a search can outlast the
    120 second ceiling of a read-only command, which kills it with no results.
    ```
    """

    name = "GNU Guix"

    homepage_url = "https://guix.gnu.org"
    documentation_url = (
        "https://guix.gnu.org/manual/en/html_node/Invoking-guix-package.html"
    )
    repository_url = "https://codeberg.org/guix/guix"
    wikipedia_url = "https://en.wikipedia.org/wiki/GNU_Guix"
    logo = "gnu"

    keywords = ("gnu guix",)

    platforms = LINUX_LIKE

    # Guix is a rolling-release distribution: the only "version" it
    # exposes for `guix pull`-managed installs and in-tree dev wrappers
    # (`./pre-inst-env guix`, `./scripts/guix`) is a git commit hash.
    # No upstream tag/semver is guaranteed to be reachable, so capturing
    # whatever `guix --version` reports and *not* enforcing a
    # `requirement` specifier is the only honest option: any working
    # `guix` is fine.
    version_regexes = (
        # Release, or `git describe` output of an in-tree checkout:
        #   `guix (GNU Guix) 1.5.0`
        #   `guix (GNU Guix) 1.4.0-7-gabc1234`
        r"guix \(GNU Guix\) (?P<version>\d[\w.\-+]*)",
        # The full commit hash of a pulled Guix, or the short one of an
        # in-tree checkout with no tag nearby. A hash opening on a digit
        # already matched above:
        #   `guix (GNU Guix) 5ef098e1eef807cffba753b1fa335fab07ce4a79`
        # Restrict to a 7–40 hex run so corrupted output isn't accepted
        # as a "version".
        r"guix \(GNU Guix\) (?P<version>[0-9a-f]{7,40})\b",
    )
    """
    ```{code-block} shell-session

    $ guix --version
    guix (GNU Guix) 1.5.0
    Copyright (C) 2025 the Guix authors
    License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
    This is free software: you are free to change and redistribute it.
    There is NO WARRANTY, to the extent permitted by law.
    ```
    """

    _SEARCH_FIELD_REGEXP = re.compile(
        r"^(?P<field>\w[\w-]*):(?:\s+(?P<value>.*))?$",
    )
    """Match a recutils field line (`name: value`), whose value may be empty."""

    _SEARCH_OUTPUT_REGEXP = re.compile(r"^\+ (?P<output>[^\s:]+): ")
    """Match an output listed under the `outputs` field of a search record."""

    _OUTDATED_REGEXP = re.compile(
        r"^\s+(?P<package_id>\S+)\s+(?P<installed_version>\S+)\s+(?:→|->)\s+"
        r"(?P<latest_version>\S+)$",
    )
    """Match an upgrade row of the transaction `guix upgrade --dry-run` reports.

    Guix pads the name column, names an output other than `out` as `name:output`,
    and prints `->` in place of the arrow when `<stderr>` cannot encode it. A row
    whose version did not change reads `(dependencies or package changed)`, and is
    left out: no newer version is available.
    """

    _REGEXP_SPECIALS = re.compile(r"([.^$*+?()\[\]{}|\\])")
    """Characters a POSIX extended regular expression reads as operators."""

    def _name_regexp(self, name: str) -> str:
        """A regular expression matching the package name `name`, and no other."""
        return "^" + self._REGEXP_SPECIALS.sub(r"\\\1", name) + "$"

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Columns are tab-separated: name, version, output and store path. Guix pads
        the first three with spaces, which are stripped. An output other than `out`
        is an entry of its own, reported as `name:output`: the specification that
        `guix install` and `guix remove` take back.

        ```{code-block} shell-session

        $ guix package --list-installed
        hello          	2.12.2	out	/gnu/store/8qjzxdk26p8c5nyj98s3321vbkmv9za0-hello-2.12.2
        lua            	5.1.5 	out	/gnu/store/sq2sj9gj8bqzgv493249xd8gzhhw1f0x-lua-5.1.5
        glib           	2.83.3	out	/gnu/store/h95r1yvlbrlqap6l8fsdzp7lpxair7sv-glib-2.83.3
        glib           	2.83.3	bin	/gnu/store/06w4p65r8hli2qnsdsnp0l8r1zghz5qr-glib-2.83.3-bin
        glib-networking	2.78.1	out	/gnu/store/n4nicicydz8d24m2qi3ddwlcxlr534qn-glib-networking-2.78.1
        ```
        """
        output = self.run_cli("package", "--list-installed")

        for line in output.splitlines():
            fields = [field.strip() for field in line.split("\t")]
            if len(fields) < 3 or not fields[0]:
                continue
            name, version, package_output = fields[:3]
            yield self.package(
                id=name if package_output == "out" else f"{name}:{package_output}",
                installed_version=version,
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `guix upgrade --dry-run` lists every package it would upgrade, and leaves
        the profile as it is.

        ```{important}
        The report is written to `<stderr>` while `<stdout>` stays empty, so it is
        read from the recorded run.
        ```

        ```{code-block} shell-session

        $ guix upgrade --dry-run
        ```

        ```{code-block} console

        The following packages would be upgraded:
           glib            2.83.3 → 2.86.0
           glib-networking 2.78.1 → 2.80.1
           glib:bin        2.83.3 → 2.86.0
           hello           2.12.2 → 2.12.3
           lua             5.1.5 → 5.5.0

        22.6 MB would be downloaded
        ```
        """
        self.run_cli("upgrade", "--dry-run")

        last = self._last_run
        if last is None:
            return
        _code, _stdout, stderr = last
        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, stderr)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended or exact matching. So we return
        the best subset of results and let
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search`
        refine them.
        ```

        Guix keeps some packages in several versions under one name, like `lua`
        from `5.1.5` to `5.4.8`. A name is reported once, at its newest version:
        the one `guix install` picks.

        A query naming an output, like `glib:bin`, reports that output of the
        package of that exact name. That is the form `installed` reports, and
        `mpm install` searches for a package before it installs it.

        Results are printed in recutils format with records separated by blank
        lines.

        ```{code-block} shell-session

        $ guix search cowsay
        name: cowsay
        version: 3.8.4
        outputs:
        + out: everything
        systems: x86_64-linux mips64el-linux aarch64-linux powerpc64le-linux
        + i686-linux armhf-linux powerpc-linux
        dependencies: perl@5.36.0
        location: gnu/packages/games.scm:1431:2
        homepage: https://web.archive.org/web/20071026043648/http://www.nog.net:80/~tony/warez/cowsay.shtml
        license: GPL 3+
        synopsis: Speaking cow text filter
        description: Cowsay is basically a text filter.  Send some text into it, and
        + you get a cow saying your text.  If you think a talking cow isn't enough, cows
        + can think too: all you have to do is run `cowthink'.  If you're tired of cows,
        + a variety of other ASCII-art messengers are available.
        relevance: 32

        name: python-snakesay
        version: 0.10.4
        outputs:
        + out: everything
        systems: x86_64-linux mips64el-linux aarch64-linux powerpc64le-linux
        + i686-linux armhf-linux powerpc-linux
        dependencies: python-pytest@8.4.1 python-setuptools@80.9.0
        location: gnu/packages/python-xyz.scm:2293:2
        homepage: https://github.com/pythonanywhere/snakesay
        license: Expat
        synopsis: Like `cowsay' but with Python flavor
        description: This package provides a simple ASCII art pictures generator of a
        + Snake with a message.
        relevance: 3
        ```
        """
        name, _, wanted_output = query.partition(":")
        listing = self.run_cli(
            "search", self._name_regexp(name) if wanted_output else query
        )

        newest: dict[str, Package] = {}
        for record in re.split(r"\n\n+", listing.strip()):
            fields: dict[str, str] = {}
            outputs: list[str] = []
            field = None
            for line in record.splitlines():
                match = self._SEARCH_FIELD_REGEXP.match(line)
                if match:
                    field = match.group("field")
                    # Guix ends some values with spaces, like the synopsis.
                    fields[field] = (match.group("value") or "").strip()
                elif field == "outputs":
                    output_match = self._SEARCH_OUTPUT_REGEXP.match(line)
                    if output_match:
                        outputs.append(output_match.group("output"))

            package_id = fields.get("name")
            if not package_id:
                continue
            if wanted_output:
                # The regular expression also matches synopses and descriptions.
                if package_id != name or wanted_output not in outputs:
                    continue
                package_id = f"{name}:{wanted_output}"
            version = fields.get("version") or None
            held = newest.get(package_id)
            if (
                held is None
                or held.latest_version is None
                or (version and parse_version(version) > held.latest_version)
            ):
                newest[package_id] = self.package(
                    id=package_id,
                    description=fields.get("synopsis") or None,
                    latest_version=version,
                )

        yield from newest.values()

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ guix install hello
        ```
        """
        return self.run_cli("install", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ guix upgrade
        ```
        """
        return self.build_cli("upgrade")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        `guix upgrade` reads its argument as a regular expression, and upgrades
        every installed package whose name it matches: `guix upgrade glib` also
        upgrades `glib-networking`. So the name is escaped and anchored, to match
        itself alone. Entries match by name, so the `:output` suffix is dropped,
        and every installed output of the package is upgraded.

        ```{code-block} shell-session

        $ guix upgrade ^lua$
        ```
        """
        return self.build_cli(
            "upgrade", self._name_regexp(package_id.partition(":")[0])
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ guix remove hello
        ```
        """
        return self.run_cli("remove", package_id)

    def sync(self) -> None:
        """Fetch the latest Guix channel revisions.

        ```{code-block} shell-session

        $ guix pull
        ```
        """
        self.run_cli("pull")

    def cleanup_cache(self) -> None:
        """Collect garbage in the store.

        ```{code-block} shell-session

        $ guix gc
        ```
        """
        self.run_cli("gc")
