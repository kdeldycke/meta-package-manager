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

    Guix is a rolling release with no upstream semver to pin against:
    `guix --version` reports a release tag, a `git describe` string, or the
    bare commit hash of an in-tree checkout. No `requirement` floor is
    enforced, since any working `guix` will do.

    ```{warning}
    `search` evaluates every package definition to match the query, so its
    cost scales with the size of the package set, not the result count: tens
    of seconds on a freshly pulled Guix, longer still from an in-tree
    development checkout. The call is bounded by `mpm --timeout` (120s by
    default), past which it is killed with no results returned, so a slow
    search can look like a hang.
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
        # Stable release or `git describe` output:
        #   `guix (GNU Guix) 1.4.0`
        #   `guix (GNU Guix) 1.4.0-7-gabc1234`
        r"guix \(GNU Guix\) (?P<version>\d[\w.\-+]*)",
        # Bare git-hash output from an in-tree dev wrapper whose
        # `git describe` had no nearby tag:
        #   `guix (GNU Guix) abc1234`
        # Restrict to a 7–40 hex run so corrupted output isn't accepted
        # as a "version".
        r"guix \(GNU Guix\) (?P<version>[0-9a-f]{7,40})\b",
    )
    """
    ```{code-block} shell-session

    $ guix --version
    guix (GNU Guix) 1.4.0
    ```
    """

    _SEARCH_FIELD_REGEXP = re.compile(
        r"^(?P<field>\w[\w-]*):\s+(?P<value>.+)$",
    )
    """Match a single recutils field line (`name: value`)."""

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

        Output is tab-separated: name, version, output, store path.

        ```{code-block} shell-session

        $ guix package --list-installed
        hello	2.10	out	/gnu/store/k74skdjjb9c9zqjv9nmgd6zi92wpf3q0-hello-2.10
        python	3.10.7	out	/gnu/store/2n3g8n7d5xkp6h4qz1v8m0rjc9wf5aby-python-3.10.7
        ```
        """
        output = self.run_cli("package", "--list-installed")

        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                yield self.package(
                    id=parts[0],
                    installed_version=parts[1],
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

        ```{caution}
        `guix search` loads and evaluates every package definition to
        match the query against each package's name, synopsis, and
        description, so it is inherently slow: its cost scales with the
        size of the package set, not the number of results. A single
        search runs for tens of seconds on a freshly pulled Guix, and far
        longer from an in-tree dev checkout that recompiles modules on the
        fly. The call is bounded by `mpm --timeout`; when that is
        unset, `search` uses the 120s read-only default, past which the
        process is killed and no results are returned, so a slow search can
        look like a hang.
        ```

        Results are printed in recutils format with records separated by blank
        lines.

        ```{code-block} shell-session

        $ guix search hello
        name: hello
        version: 2.10
        outputs: out
        systems: x86_64-linux i686-linux
        dependencies: glibc@2.35 ...
        location: gnu/packages/base.scm:86:2
        homepage: https://www.gnu.org/software/hello/
        license: GPL 3+
        synopsis: Hello, GNU world: an example GNU package
        description: GNU Hello prints the message "Hello, world!"
        + and then exits.  It serves as an example of standard
        + GNU coding practices.
        relevance: 10
        ```
        """
        output = self.run_cli("search", query)

        for record in re.split(r"\n\n+", output.strip()):
            fields: dict[str, str] = {}
            for line in record.splitlines():
                match = self._SEARCH_FIELD_REGEXP.match(line)
                if match:
                    fields[match.group("field")] = match.group("value")
                # Continuation lines (`+ ...`) are ignored; we only need the
                # first line of multi-line fields like description.

            name = fields.get("name")
            if name:
                yield self.package(
                    id=name,
                    description=fields.get("synopsis"),
                    latest_version=fields.get("version"),
                )

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
