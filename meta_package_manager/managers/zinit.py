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

import os
import re
import shlex
from pathlib import Path
from typing import ClassVar

from click_extra.execution import args_cleanup
from extra_platforms import LINUX_LIKE, MACOS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


_XDG_DATA_HOME = os.environ.get(
    "XDG_DATA_HOME",
    str(Path.home() / ".local" / "share"),
)
"""Base directory Zinit's default install root derives from."""

_ZINIT_HOME = os.environ.get("ZINIT_HOME", str(Path(_XDG_DATA_HOME) / "zinit"))
"""Resolve Zinit's install root from the environment variable its own
installation snippet sets, or from the XDG default it falls back to."""

_SOURCE_CANDIDATES = (
    Path(_ZINIT_HOME) / "zinit.git" / "zinit.zsh",
    Path.home() / ".zinit" / "bin" / "zinit.zsh",
)
"""Where `zinit.zsh` sits: the XDG location the current installer uses, then
the legacy one."""


def zinit_source_path() -> Path:
    """Locate the `zinit.zsh` file every invocation sources.

    Falls back to the current installer's location when none of the candidates
    exists, so the built command stays well-formed and simply fails to source,
    which is what makes the version probe double as Zinit's presence check.
    """
    for candidate in _SOURCE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _SOURCE_CANDIDATES[0]


class Zinit(PackageManager):
    """Zinit is a flexible and fast Zsh plugin manager.

    Zinit installs Zsh plugins, snippets and completions from GitHub and other
    forges, cloning each into `$ZINIT[PLUGINS_DIR]`. Packages are identified by
    the `user/repo` slug Zinit both reports and accepts, which is the id mpm
    keys them on. A plugin the user renamed through the `id-as` ice reports
    under that alias instead, and feeds back into every operation just the
    same.

    ```{caution}
    `zinit` is a shell function, not a standalone binary, so every invocation
    is wrapped in `zsh -c 'source <zinit.zsh> && zinit <args>'`. Zsh is
    therefore the manager's CLI, and Zinit's own presence is established by
    the version probe: a host with Zsh but no Zinit fails to source and
    reports no version, which leaves the manager unavailable.
    ```

    ```{caution}
    {meth}`Zinit.installed` is the one operation that cannot use that wrapper.
    Zinit tracks plugins in shell state populated by the `zinit load` calls of
    the user's `.zshrc`, so a freshly sourced non-interactive shell knows of
    none. That query therefore runs `zsh --interactive`, paying a full shell
    startup to inventory what the user's Zsh actually loads. Plugins deferred
    with the `wait` ice (Zinit's turbo mode) load asynchronously after the
    prompt would have been drawn, so a non-interactive run may miss them.
    ```

    ```{note}
    No `outdated`: Zinit's only "what would change" command is
    `zinit status --all`, which unconditionally runs `.zinit-self-update`
    first, pulling and recompiling Zinit itself. A query that mutates the
    manager is not a query, so mpm auto-skips the operation and
    `upgrade --all` still works.
    ```

    ```{note}
    No `search`: Zinit resolves plugins straight from forge URLs and indexes
    no registry to search.
    ```
    """

    homepage_url = "https://github.com/zdharma-continuum/zinit"
    logo = "zsh"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=3.10.0"
    """First release of the `zdharma-continuum` fork whose confirmation prompt,
    and thus the `--yes` flag {meth}`Zinit.remove` depends on, behaves."""

    cli_names = ("zsh",)
    """Zsh is the binary mpm actually executes.

    Zinit itself is a shell function defined by a `zinit.zsh` file that is
    sourced, never executed, so it cannot serve as the manager's CLI: mpm
    requires an executable, and that file ships non-executable. Keying the
    manager on Zsh instead makes the version probe the presence check, since
    sourcing an absent `zinit.zsh` yields no version and leaves the manager
    unavailable.
    """

    extra_env: ClassVar = {"SHELL_SESSIONS_DISABLE": "1"}
    """Keep macOS' Zsh session bookkeeping from writing a session file on every
    query."""

    version_cli_options = ("version",)

    version_regexes = (r"zinit\s+v(?P<version>\S+)",)
    """Zinit reports the `git describe` of its own checkout, so a clone sitting
    past a tag reports a `3.15.0-5-gb1946ac` flavored version.

    ```{code-block} shell-session

    $ zinit version
    zinit v3.15.0 (darwin25.4.0_arm64)
    ```
    """

    _INSTALLED_REGEXP = re.compile(r"^\s*\d+\s+[LU]\s+(?P<package_id>\S+)$")
    """A numbered listing row, whose `L`/`U` marker tells a loaded plugin from
    an unloaded one. Both are installed on disk, so neither is filtered out."""

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations in the Zsh shell Zinit needs.

        Three subcommands need a shell of their own shape, so the wrapper is
        chosen from the subcommand rather than being uniform.

        `plugins` reads the plugin registry out of shell state that the
        `zinit load` calls of the user's `.zshrc` populate, so it runs
        `zsh --interactive` and lets that file do the sourcing. Sourcing
        `zinit.zsh` again on top would reset the registry and report nothing.

        `load` is prefixed with the `cloneonly` ice, which stops Zinit right
        after the clone. Installing a plugin otherwise sources it, running
        third-party shell code inside the process mpm drives.

        `version` is guarded by a readability test that exits successfully
        when `zinit.zsh` is absent. Zsh is the default shell on macOS and near
        ubiquitous elsewhere, so an unguarded probe would turn every host that
        merely has Zsh into a manager reporting errors. A `zinit.zsh` that is
        present but broken still fails loudly.

        ```{note}
        The `**kwargs` accepted by the base class (`auto_pre_args`, `sudo`,
        etc.) are accepted but ignored because every invocation goes through
        the `zsh -c` wrapper and Zinit never requires elevated privileges.
        ```
        """
        clean_args = args_cleanup(*args)
        subcommand = clean_args[0] if clean_args else ""
        zinit_cmd = " ".join(shlex.quote(arg) for arg in clean_args)
        source_path = shlex.quote(str(zinit_source_path()))

        if subcommand == "plugins":
            return ("zsh", "--interactive", "-c", f"zinit {zinit_cmd}")

        if subcommand == "version":
            probe = (
                f"[[ -r {source_path} ]] || exit 0; "
                f"source {source_path} && zinit version"
            )
            return ("zsh", "-c", probe)

        prelude = f"source {source_path}"
        if subcommand == "load":
            prelude += " && zinit ice cloneonly"
        return ("zsh", "-c", f"{prelude} && zinit {zinit_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Zinit reports no version alongside a plugin, so packages are yielded
        bare: pinning a plugin to a revision is an ice modifier of the user's
        own `zinit load` call, not state Zinit surfaces in this listing.

        ```{code-block} shell-session

        $ zsh --interactive -c 'zinit plugins'
        ==> 3 Plugins

         1 L ~zinit/zinit.git

         2 L zdharma-continuum/fast-syntax-highlighting

         3 U zsh-users/zsh-completions


        Loaded: L | Unloaded: U
        ```
        """
        output = self.run_cli("plugins")
        yield from self.parse_regex_lines(self._INSTALLED_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        Zinit conflates installing a plugin with sourcing it, so
        {meth}`Zinit.build_cli` sets the `cloneonly` ice ahead of this call.

        ```{code-block} shell-session

        $ zinit load zdharma-continuum/null
        ```
        """
        return self.run_cli("load", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        ```{note}
        Zinit self-updates before updating anything else, so this also pulls
        and recompiles Zinit itself.
        ```

        ```{code-block} shell-session

        $ zinit update --all
        ```
        """
        return self.build_cli("update", "--all")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        ```{code-block} shell-session

        $ zinit update zdharma-continuum/null
        ```
        """
        return self.build_cli("update", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ zinit delete --yes zdharma-continuum/null
        ```
        """
        return self.run_cli("delete", "--yes", package_id)
