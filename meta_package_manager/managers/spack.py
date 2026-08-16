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

from ..capabilities import search_capabilities
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Spack(PackageManager):
    """Spack, the package manager built for supercomputers and HPC clusters.

    A package is a *spec*: a package name carrying a version, a compiler, a
    target architecture and a set of build options, each combination installed
    into a prefix of its own. mpm keys a package on its id alone, so the spec is
    reduced to the name every verb accepts back.

    ```{note}
    Holding several builds of one package at once is Spack's whole purpose, so
    the inventory repeats a name as many times as the host has builds of it.
    That reduction to one entry per id is what makes this a class rather than a
    bundled definition, the same case `luarocks` and `vagrant` answer.

    Reducing on the version alone is a deliberate loss: two builds of the *same*
    version differing only in compiler or build options collapse into one entry,
    which mpm has no way to tell apart and no verb to address separately.
    ```

    ```{caution}
    `--no-env` is load-bearing, and silently so. Spack scopes every command to
    the active environment, which the user activates with `spack env activate`
    or by exporting `SPACK_ENV`, and an environment is a *project*, not the
    machine. With one active, `spack find` reports that environment's contents:
    a host holding four installed packages reports none at all, an empty answer
    indistinguishable from an empty machine. Worse, an `SPACK_ENV` left pointing
    at a deleted environment makes the command fail outright with `Error: no
    environment in ...`.

    The flag is a global one, placed before the subcommand, which is why it is
    declared as {attr}`pre_args` rather than repeated per operation. Note that
    `-E` is *not* a portable shorthand for it: `spack gc` binds its own `-E` to
    `--except-any-environment`, so the long form is the only spelling that means
    the same thing everywhere. The version probe skips {attr}`pre_args` entirely
    and so runs bare.

    `haxelib` forces `--global` and `luarocks` `--no-project` against the same
    hazard.
    ```

    ```{note}
    The inventory is a projection rather than the default display. `spack find`
    normally groups its output under `-- darwin-tahoe-m1 / %c=apple-clang@21.0.0`
    banners whose text depends on the host's architecture and compilers, while
    `--format` prints the requested fields alone. `gcloud` reaches for the same
    escape.
    ```

    ```{note}
    Every spec Spack's database holds is reported, which is broader than what
    Spack built. Packages pulled in as build dependencies appear, matching the
    `raco` reading that an inventory hiding what was installed on the user's
    behalf is the wrong answer, and so do *externals*: the system compiler
    Spack registers on first use is listed as `apple-clang`, since Spack tracks
    it as installed and its own garbage collector removes it. No flag separates
    them out.
    ```

    ```{warning}
    Spack has no `outdated` and no upgrade verb, and neither is faked. Installing
    a package that is already present *adds* a second build rather than replacing
    the first, which is the point of the tool, so wiring `upgrade` to `install`
    would leave the old build in place while reporting success. Reclaiming the
    superseded build is what `cleanup --orphans` does.
    ```

    ```{warning}
    A read bootstraps the host on first use. Since Spack 1.0 the package recipes
    live in [spack/spack-packages](https://github.com/spack/spack-packages)
    rather than in Spack itself, and upstream states Spack "clones the package
    repository automatically when you first run", so an inventory or a search on
    a fresh install fetches some twenty thousand objects into `~/.spack` before
    answering. `ollama` starting a daemon from a listing is the same shape,
    smaller.
    ```

    Documentation: [Spack documentation](https://spack.readthedocs.io).
    """

    name = "Spack"

    homepage_url = "https://spack.io"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=1.0.0"
    """The release that moved the package recipes into a repository of their own,
    giving them a lifecycle Spack can refresh and `spack repo update` something
    to update.
    """

    pre_args = ("--no-env",)
    """Ignore whichever environment the user has activated, so every operation
    answers for the machine rather than for a project.
    """

    _INSTALLED_REGEXP = re.compile(r"^(?P<package_id>[^@\s]+)@(?P<version>\S+)$")
    """One installed spec, as projected by `--format`: the package name, an `@`
    and the version.

    The projection is deliberately written without a space, which keeps the whole
    format string a single shell word. mpm discloses the command it runs so the
    user can replay it by hand, and it does not quote arguments, so `{name}
    {version}` would disclose a line that no longer runs when pasted back into a
    shell. `{name}@{version}` needs no quoting and is Spack's own spec syntax
    besides. Anchoring at both ends rejects the progress and error lines Spack
    writes around a listing.
    """

    def _newest_per_name(
        self,
        rows: Iterator[tuple[str, str]],
    ) -> Iterator[Package]:
        """Reduce specs to one package per name, keeping the highest version.

        Spack lists every build the host holds, so a package installed at two
        versions, or at one version with two sets of build options, comes back
        once per build.
        """
        best: dict[str, str] = {}
        for package_id, version in rows:
            current = best.get(package_id)
            if current is None or parse_version(version) > parse_version(current):
                best[package_id] = version
        for package_id, version in best.items():
            yield self.package(id=package_id, installed_version=version)

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ spack --no-env find --format {name}@{version}
        apple-clang@21.0.0
        compiler-wrapper@1.1.0
        gmake@4.4.1
        zlib@1.3.1
        zlib@1.3.2
        ```
        """
        output = self.run_cli("find", "--format", "{name}@{version}")
        yield from self._newest_per_name(
            (match.group("package_id"), match.group("version"))
            for match in map(self._INSTALLED_REGEXP.match, output.splitlines())
            if match
        )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Spack matches a query as a substring of the package name, and
        `--search-description` widens that to the recipes' descriptions, which is
        the extended search. There is no way to narrow it to an exact name, so
        mpm filters exact matches itself.

        ```{code-block} shell-session

        $ spack --no-env list --format version_json zlib-ng
        [
          {"name": "zlib-ng",
           "latest_version": "2.3.3",
           "versions": ["2.3.3", "2.3.2", "2.2.5", "2.2.4", "2.2.3", "2.2.2", "2.2.1", "2.1.7", "2.1.6", "2.1.5", "2.1.4", "2.0.7", "2.0.0"],
           "homepage": "https://github.com/zlib-ng/zlib-ng",
           "file": "https://github.com/spack/spack-packages/blob/develop/repos/spack_repo/builtin/packages/zlib_ng/package.py",
           "maintainers": ["haampie"],
           "dependencies": {"build": ["gnuconfig", "cxx", "gmake", "ninja", "c", "cmake"], "link": [], "run": [], "test": []}}
        ]
        ```
        """
        args = ["list", "--format", "version_json"]
        if extended:
            args.append("--search-description")
        args.append(query)
        output = self.run_cli(*args)
        yield from self.parse_json_items(
            output,
            fields={"package_id": "name", "latest_version": "latest_version"},
        )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        A version is pinned by appending it to the name after an `@`, which is
        Spack's own spec syntax rather than a separate argument.

        ```{code-block} shell-session

        $ spack --no-env install zlib@1.3.1
        [ ] 3iyb7mz zlib@1.3.1 staging (0s)
        [ ] 3iyb7mz zlib@1.3.1 edit (0s)
        [ ] 3iyb7mz zlib@1.3.1 build (1s)
        [ ] 3iyb7mz zlib@1.3.1 install (2s)
        [+] 3iyb7mz zlib@1.3.1 /opt/homebrew/Cellar/spack/1.2.2/opt/spack/darwin-m1/zlib-1.3.1-3iyb7mzv7ij3w2o43t4nb2pq25az6pt7 (2s)
        ```
        """
        spec = package_id if version is None else f"{package_id}@{version}"
        return self.run_cli("install", spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `--all` is load-bearing rather than a convenience. Naming a package that
        the host holds more than one build of is refused outright, with `Error:
        zlib matches multiple packages`, so without the flag a removal fails on
        exactly the hosts Spack exists to serve.

        ```{code-block} shell-session

        $ spack --no-env uninstall --yes-to-all --all zlib
        ==> Successfully uninstalled zlib@1.3.1+optimize+pic+shared build_system=makefile platform=darwin os=tahoe target=m1/3iyb7mz
        ==> Successfully uninstalled zlib@1.3.2+optimize+pic+shared build_system=makefile platform=darwin os=tahoe target=m1/7ib3y53
        ```
        """
        return self.run_cli("uninstall", "--yes-to-all", "--all", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        Pulls the package repository Spack clones on first use, which is where
        every recipe now lives.

        ```{code-block} shell-session

        $ spack --no-env repo update
        ==> builtin: Already up to date.
        ```
        """
        self.run_cli("repo", "update")

    def cleanup_orphan(self) -> None:
        """Remove every spec nothing depends on any more.

        Reclaims the build dependencies an install pulled in, and the builds a
        later install superseded. Explicitly installed packages are kept.

        ```{code-block} shell-session

        $ spack --no-env gc --yes-to-all
        ==> Successfully uninstalled gmake@4.4.1~guile build_system=generic platform=darwin os=tahoe target=m1/x7otsag
        ==> Successfully uninstalled apple-clang@21.0.0 build_system=bundle platform=darwin os=tahoe target=aarch64/ti7wjie
        ==> Successfully uninstalled compiler-wrapper@1.1.0 build_system=generic platform=darwin os=tahoe target=m1/2eppidz
        ```
        """
        self.run_cli("gc", "--yes-to-all")

    def cleanup_cache(self) -> None:
        """Scrub the build stages, downloads and caches.

        Bootstrap software is deliberately left alone: `--bootstrap` would remove
        the concretizer Spack needs before it can resolve anything, so the next
        operation would have to fetch it again.

        ```{code-block} shell-session

        $ spack --no-env clean --downloads --misc-cache --python-cache --stage
        ==> Removing all temporary build stages
        ==> Removing cached downloads
        ==> Removing cached information on repositories
        ==> Removing python cache files
        ```
        """
        self.run_cli(
            "clean", "--downloads", "--misc-cache", "--python-cache", "--stage"
        )
