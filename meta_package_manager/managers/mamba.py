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

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Mamba(PackageManager):
    """Conda-compatible package manager, reimplemented in C++.

    Reaches the same channels [`conda`](conda.md) does, resolving with libsolv
    behind a command line of its own rather than delegating to conda. It is
    wrapped on the same grounds as [`nala`](nala.md) over `apt`: same archives,
    separate implementation. Since `2.0` it shares no code with conda at all,
    the Python executable of the `1.x` line having been replaced by a
    dynamically linked build of micromamba.

    ```{important}
    Every operation targets mamba's *currently active* environment, which is
    `base` when none is activated. `mpm` neither activates nor switches
    environments: it inspects and mutates whatever mamba resolves from the
    inherited `CONDA_PREFIX` / `CONDA_DEFAULT_ENV`, exactly as a bare `mamba`
    call in the same shell would, and exactly as the conda wrapper does.
    Per-environment targeting is not supported yet.
    ```

    ```{caution}
    Sharing that prefix with conda is why the two are serialized against each
    other. mamba takes a real lock on the environment and on every package
    cache directory for the length of a transaction, and conda honors none of
    them: its own locking covers the repodata cache alone. Running them at once
    corrupts rather than blocks, which upstream has closed as not planned
    ([conda/conda#13037](https://github.com/conda/conda/issues/13037)).
    ```

    ```{note}
    No `sync`. Nothing in the command set refreshes the index on its own, the
    closest being `clean --index-cache`, which only forces a refetch on the
    next operation. The conda wrapper implements none either, so this is parity
    rather than a gap.
    ```

    ```{warning}
    `mamba upgrade` does not exist: unlike conda, mamba never aliased it, and
    calling it exits non-zero on an unexpected argument. Upgrades go through
    `update`.
    ```

    Documentation: [mamba user guide](https://mamba.readthedocs.io/en/latest/user_guide/mamba.html).
    """

    name = "Mamba"

    homepage_url = "https://mamba.readthedocs.io"
    logo = "anaconda"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=2.0.0"
    """The release that made mamba a standalone C++ program.

    Chosen over the newer `2.9.0`, where the inventory settled on one shape, so
    the floor does not exclude every release a user is realistically running:
    `2.9.0` is days old. {meth}`installed` reads both shapes instead.
    """

    version_regexes = (r"^(?P<version>\d+\.\d+\.\d+\S*)$",)
    r"""Search the bare version mamba reports.

    ```{code-block} shell-session

    $ mamba --version
    2.9.0
    ```

    Anchored at both ends because the output is the version and nothing else:
    mamba prints no program name to key on, unlike conda's `conda 24.5.0`. The
    patterns are applied in multiline mode, so the anchors bind to the line.
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ mamba list --json
        {
            "log_history": [],
            "packages": [
                {
                    "base_url": "https://conda.anaconda.org/conda-forge",
                    "build_number": 2,
                    "build_string": "h23cfdf5_2",
                    "channel": "conda-forge",
                    "dist_name": "libiconv-1.18-h23cfdf5_2",
                    "md5": "4d5a7445f0b25b6a3ddbb56e790f5251",
                    "name": "libiconv",
                    "platform": "osx-arm64",
                    "url": "https://conda.anaconda.org/conda-forge/osx-arm64/libiconv-1.18-h23cfdf5_2.conda",
                    "version": "1.18"
                }
            ]
        }
        ```

        ```{caution}
        Two payload shapes are accepted, and reading the wrong one is silent.
        `2.9.0` wrapped this array in an envelope carrying a `log_history`
        sibling, where every release before it printed the array bare, the way
        conda still does. Neither shape raises on the other's reader: it simply
        finds no list and reports an empty inventory, so the array is located
        by shape rather than by a fixed path.

        That same envelope is why success is read from the exit code and the
        presence of `packages`, never from the output parsing. Pointed at a
        prefix that does not exist, `2.9.0` exits non-zero with an empty
        `stderr` and tens of kilobytes of trace on `stdout`, as JSON that
        parses perfectly and holds no packages.
        ```
        """
        output = self.run_cli("list", "--json", must_succeed=True)

        data = self.parse_json(output)
        packages = data.get("packages") if isinstance(data, dict) else data
        if not isinstance(packages, list):
            return
        for pkg in packages:
            if isinstance(pkg, dict) and pkg.get("name"):
                yield self.package(
                    id=pkg["name"],
                    installed_version=pkg.get("version"),
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        mamba inherits conda's lack of a dedicated outdated command, and its
        dry-run reports the same `actions` mapping, so the upgrade the solver
        *would* perform is simulated and its `UNLINK` (current) and `LINK`
        (candidate) sets are diffed by name. A package in both is an in-place
        upgrade; one in only `LINK` is a freshly pulled dependency and one in
        only `UNLINK` is a removal, so neither is reported.

        ```{code-block} shell-session

        $ mamba update --all --dry-run --json
        {
            "actions": {
                "LINK": [
                    {
                        "build": "h23cfdf5_2",
                        "fn": "libiconv-1.18-h23cfdf5_2.conda",
                        "name": "libiconv",
                        "version": "1.18"
                    }
                ],
                "PREFIX": "/opt/conda",
                "UNLINK": [
                    {
                        "build": "h23cfdf5_1",
                        "fn": "libiconv-1.17-h23cfdf5_1.conda",
                        "name": "libiconv",
                        "version": "1.17"
                    }
                ]
            },
            "dry_run": true,
            "log_history": [],
            "prefix": "/opt/conda",
            "success": true
        }
        ```

        When the environment is already current, the `actions` key is omitted
        exactly as conda omits it:

        ```{code-block} shell-session

        $ mamba update --all --dry-run --json
        {
            "dry_run": true,
            "log_history": [],
            "message": "All requested packages already installed",
            "prefix": "/opt/conda",
            "success": true
        }
        ```

        ```{note}
        `repoquery` was assessed for this and cannot answer it: it reads
        channels and installed metadata but never solves, so it cannot say what
        a transaction would do. Entries here also carry libmamba's wider field
        set instead of conda's, and no `FETCH` key, neither of which is read.
        ```
        """
        output = self.run_cli(
            "update", "--all", "--dry-run", "--json", must_succeed=True
        )

        data = self.parse_json(output)
        actions = data.get("actions") if data else None
        if not actions:
            return

        installed = {pkg["name"]: pkg["version"] for pkg in actions.get("UNLINK", ())}
        for pkg in actions.get("LINK", ()):
            if pkg["name"] in installed:
                yield self.package(
                    id=pkg["name"],
                    installed_version=installed[pkg["name"]],
                    latest_version=pkg["version"],
                )

    @search_capabilities(extended_support=False, exact_support=True)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not support extended matching, mamba exposing no package
        description to match against. Exact matching is native: a bare query
        resolves against the package name alone, where wrapping it in `*`
        widens it to a substring match.
        ```

        ```{code-block} shell-session

        $ mamba search "*zstd*" --json
        {
            "log_history": [],
            "query": {
                "query": "*zstd*",
                "type": "search"
            },
            "result": {
                "msg": "",
                "pkgs": [
                    {
                        "build": "py313h7208f8c_0",
                        "name": "backports.zstd",
                        "version": "1.6.0"
                    }
                ],
                "status": "OK"
            }
        }
        ```

        ```{caution}
        Results are a flat list under `result.pkgs`, not conda's mapping of
        name to builds, so they are grouped here by name. The newest build of
        each group is picked by comparing versions rather than by position:
        mamba sorts descending where conda sorts ascending, and that order was
        a string comparison before `2.6.0`, which misplaces `1.10` against
        `1.9`. Comparing parsed versions is right whatever the release does.

        A query matching nothing exits zero with an empty `pkgs`, unlike
        conda's non-zero `PackagesNotFoundError` payload.
        ```
        """
        output = self.run_cli("search", query if exact else f"*{query}*", "--json")

        data = self.parse_json(output)
        result = data.get("result") if isinstance(data, dict) else None
        packages = result.get("pkgs") if isinstance(result, dict) else None
        if not isinstance(packages, list):
            return

        groups: dict[str, list[dict]] = {}
        for pkg in packages:
            if isinstance(pkg, dict) and pkg.get("name") and pkg.get("version"):
                groups.setdefault(pkg["name"], []).append(pkg)

        for package_id, builds in groups.items():
            newest = max(builds, key=lambda build: parse_version(build["version"]))
            yield self.package(id=package_id, latest_version=newest["version"])

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, optionally pinned to a version.

        mamba accepts a `MatchSpec`, so the version is appended with `=`.

        ```{code-block} shell-session

        $ mamba install --yes zstd
        ```
        """
        if version:
            package_id = f"{package_id}={version}"
        return self.run_cli("install", "--yes", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ mamba update --all --yes
        ```
        """
        return self.build_cli("update", "--all", "--yes")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        ```{code-block} shell-session

        $ mamba update --yes zstd
        ```
        """
        if version:
            package_id = f"{package_id}={version}"
        return self.build_cli("update", "--yes", package_id)

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{code-block} shell-session

        $ mamba remove --yes zstd
        ```
        """
        return self.run_cli("remove", "--yes", package_id)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        ```{code-block} shell-session

        $ mamba clean --all --yes
        ```
        """
        self.run_cli("clean", "--all", "--yes")


class Micromamba(Mamba):
    """mamba's statically linked build, shipped as a single self-contained binary.

    The same program as [`mamba`](mamba.md), built the other way: upstream's
    build declares *"mamba is a dynamic build of micromamba"* and compiles both
    executables from one source list. Every operation, parser and forced
    argument is therefore inherited unchanged.

    ```{note}
    The two are separate managers rather than one manager naming both binaries,
    because they resolve *different* root prefixes: `mamba` takes the conda
    installation it ships inside, while `micromamba` takes `~/micromamba` or
    its XDG data directory. `mpm` resolves a manager to the first of its CLI
    names found while walking the search path, so a host carrying both would
    silently report whichever came first on `PATH` and hide the other's
    packages entirely.
    ```

    ```{note}
    Their command sets differ by exactly one entry: micromamba adds
    `self-update`, which the dynamic build rejects. It maps to no `mpm`
    operation, so nothing here uses it.
    ```
    """

    id = "micromamba"

    name = "Micromamba"

    homepage_url = "https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html"

    cli_names = ("micromamba",)
