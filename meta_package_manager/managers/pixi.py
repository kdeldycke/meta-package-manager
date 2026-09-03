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

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Pixi(PackageManager):
    """pixi installs conda packages, either into a project workspace or
    machine-wide as global tools.

    `mpm` is system-scoped, so this wrapper drives the `pixi global` scope
    alone and never touches a `pixi.toml` workspace. Global tools resolve from
    conda channels, `conda-forge` by default, and land in their own prefix
    under `$PIXI_HOME`.

    Documentation: [pixi global tools](https://pixi.sh/latest/global_tools/introduction/).

    ```{important}
    pixi isolates each global tool in its own *environment*, and `mpm` keys
    packages on the **environment** name, not on the conda package names inside
    it. The environment is the unit every mutating `pixi global` verb addresses:
    `uninstall` deletes one whole environment and `update` refreshes one whole
    environment, neither taking a package name. `pixi global install <pkg>`
    names the environment after the package, so for everything `mpm` installs
    the two are the same string and every operation round-trips.

    Keying on the inner `dependencies` instead was tried and is unsafe: it
    reports packages that `remove` cannot address one at a time, so removing
    one of them deletes the whole environment and silently takes its siblings
    with it.
    ```

    ```{caution}
    An environment holding more than the package it is named after, built with
    `pixi global install <pkg> --with <other>` or `pixi global add`, is
    therefore reported as the single package `<pkg>`. Its extra packages are
    invisible to `mpm`, and removing `<pkg>` destroys them along with the
    environment, which is exactly what a bare `pixi global uninstall <pkg>`
    does. `mpm` neither widens nor narrows that behavior.
    ```

    ```{note}
    An environment whose `dependencies` do not include the package it is named
    after reports no version. That is the same signal pixi's own listing gives:
    it prints `<name>: <version>` inline only while the environment resolves to
    its eponymous package, and drops the version once the contents diverge.
    ```

    ```{caution}
    No `search` operation is declared, though `pixi search` exists. Its
    `--json` mode cannot be capped: the flag `conflicts_with_all` the
    `--limit` and `--limit-packages` options that bound the human view, and
    outside a workspace pixi falls back to `Platform::all()` and queries every
    known conda subdir, roughly thirty of them, which is exactly how `mpm`
    runs it. Repodata carries no summary or description either, so the results
    would be name-only. Declaring nothing lets `mpm` skip the manager during a
    search rather than stall on it.

    Bounding it means passing `--platform`, which would put a host-to-conda-subdir
    mapping in `mpm` that pixi already owns, and an empty result set is an error
    rather than an empty document, so reviving `search` is a deliberate piece of
    work rather than a one-line addition.
    ```

    ```{caution}
    No `outdated` operation is declared: nothing in `pixi global` reports
    upgradable packages without performing the upgrade. `pixi global update`
    has no dry-run mode, and the request for a dedicated command
    ([prefix-dev/pixi#6279](https://github.com/prefix-dev/pixi/issues/6279))
    was closed pointing at the workspace-scoped `pixi update --dry-run`, which
    does not cover the global scope. `upgrade --all` is unaffected and maps to
    the native bare `pixi global update`.
    ```

    ```{note}
    No `sync` operation either, despite the name of `pixi global sync`: that
    command reconciles installed environments against the manifest, installing
    and removing to match it, rather than refreshing package metadata from the
    channels. Mapping `mpm sync` onto it would make a read-shaped command
    mutate the machine.
    ```
    """

    name = "pixi"

    homepage_url = "https://pixi.sh"

    # No `logo`: Simple Icons carries no pixi mark yet. Their request is open and
    # already cleared of trademark concerns (labelled `permission not needed`):
    # https://github.com/simple-icons/simple-icons/issues/13796
    # Do not reach for their `pixiv` mark, which is an unrelated brand.

    keywords = ("prefix.dev",)

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=0.65.0"
    """[`0.65.0`](https://github.com/prefix-dev/pixi/blob/main/CHANGELOG.md) is
    where `pixi global list` gained the `--json` flag this wrapper reads
    ([prefix-dev/pixi#5530](https://github.com/prefix-dev/pixi/pull/5530)), and
    it is the binding floor. Every other operation is far older: `install`
    dates to `0.0.4`, `list` to `0.3.0`, and `uninstall` / `update` to the
    `0.33.0` rewrite that rebuilt `pixi global` around its manifest. That same
    rewrite is why nothing below `0.33.0` would work anyway: `pixi global
    remove` meant *uninstall* back then, and now means removing one dependency
    from an environment.
    """

    pre_args = ("--color=never", "--no-progress")
    """Both are global options, accepted ahead of any subcommand.

    `pixi` colorizes its listings semantically and draws progress bars while
    solving. Each turns itself off when the matching stream is not a terminal,
    but `mpm` asks explicitly rather than relying on redirection. The version
    probe runs with `auto_pre_args=False` and so stays a bare `pixi --version`.
    """

    version_regexes = (r"^pixi\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ pixi --version
    pixi 0.48.0
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        The document is an array of *environments*, each carrying the explicit
        specs it was created from. Transitive dependencies are not listed, which
        is what makes this an inventory of tools rather than of everything on
        disk. Each environment yields exactly one package, keyed on the
        environment name, and its version is read from the dependency of the
        same name. A `version` is `null` for a package the manifest declares but
        that is not installed in the prefix, and the optional `platform` key is
        omitted unless the environment pins one.

        The block below is source-derived: its layout follows pixi's
        `serde_json::to_string_pretty` serialization of `GlobalEnvironmentJson`,
        and its values are those of the `ripgrep` entry in pixi's own
        [`pixi global list` reference output](https://pixi.sh/latest/reference/cli/pixi/global/list/).

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global list --json
        [
          {
            "name": "ripgrep",
            "dependencies": [
              {
                "name": "ripgrep",
                "version": "14.1.0"
              }
            ],
            "exposed": [
              {
                "exposed_name": "rg",
                "executable": "rg"
              }
            ]
          }
        ]
        ```
        """
        output = self.run_cli("global", "list", "--json", must_succeed=True)
        data = self.parse_json(output)
        if not data:
            return
        for environment in data:
            env_name = environment.get("name")
            if not env_name:
                continue
            version = None
            for dependency in environment.get("dependencies", ()):
                if dependency.get("name") == env_name:
                    version = dependency.get("version")
                    break
            yield self.package(id=env_name, installed_version=version)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        The positional argument is a conda `MatchSpec`, so a version is pinned
        by appending `==<version>` to the name rather than through a flag.

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global install hyperfine
        ```

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global install hyperfine==1.20.0
        ```
        """
        spec = f"{package_id}=={version}" if version else package_id
        return self.run_cli("global", "install", spec)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        Bare `pixi global update` updates every environment: there is no
        `--all` flag. It also prunes stale environments on the way through.

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global update
        ```
        """
        return self.build_cli("global", "update")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        `pixi global update` takes environment names and accepts no version at
        all, so a pinned upgrade is not expressible: `mpm` warns and upgrades to
        whatever the channels resolve to.

        Routing a pinned upgrade through `pixi global install <pkg>==<version>`
        instead was tried and rejected. That verb takes a package spec rather
        than an environment name, and creates the environment when it is
        missing, so pinning a package that lives inside a differently-named
        environment forks a second environment holding a second copy and
        reports success, leaving the original untouched.

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global update hyperfine
        ```
        """
        return self.build_cli("global", "update", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `pixi global uninstall` removes a whole environment, deleting its prefix
        outright, which is the counterpart of the `pixi global install` that
        created it and matches the unit {meth}`installed` reports. An
        environment carrying co-installed extras loses those too.

        The sibling `pixi global remove` is deliberately not used: it drops one
        dependency from an environment and leaves the environment behind, which
        would strand an entry `mpm` still reports as installed.

        ```{code-block} shell-session

        $ pixi --color=never --no-progress global uninstall hyperfine
        ```
        """
        return self.run_cli("global", "uninstall", package_id)

    def cleanup_cache(self) -> None:
        """Clear pixi's download caches.

        `--yes` is required: with no cache-type flag, `pixi clean cache` asks
        for confirmation on `<stdin>` and would otherwise block forever under
        `mpm`.

        ```{code-block} shell-session

        $ pixi --color=never --no-progress clean cache --yes
        ```
        """
        self.run_cli("clean", "cache", "--yes")
