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

from extra_platforms import ALL_PLATFORMS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


PLUGIN_LIST = "vim.pack.get(nil, {info = false})"
"""Lua expression listing every plugin `vim.pack` manages.

`info` is turned off on purpose: the extra payload it gathers (the Git branches
and tags available for each plugin) costs one Git invocation per plugin and
holds nothing mpm reports.
"""


def lua_string(value: str) -> str:
    """Render `value` as a Lua string literal.

    JSON string syntax is a subset of Lua's, so {func}`json.dumps` quotes and
    escapes any plugin URL into a valid Lua literal. `ensure_ascii` is turned
    off because Lua has no `\\uXXXX` escape: a non-ASCII source must stay
    verbatim UTF-8.
    """
    return json.dumps(value, ensure_ascii=False)


def lua_command(body: str) -> str:
    """Wrap a Lua `body` into the `-c` argument handed to Neovim.

    The trailing `os.exit(0)` is the success path: it terminates Neovim before
    the failure gate in {attr}`Vim_Pack.post_args` can run.
    """
    return f"lua {body} os.exit(0)"


def lua_resolve(package_id: str, action: str) -> str:
    """Lua resolving a `src` URL to its plugin name, then running `action`.

    `vim.pack.del()` and `vim.pack.update()` both address plugins by the short
    name Neovim derives from the source URL, while mpm keys packages on the URL
    itself. The mapping is looked up in `vim.pack.get()` output rather than
    recomputed here, so a plugin whose spec overrides its `name` still
    resolves. A URL that matches nothing leaves the loop a no-op, which keeps
    removing an absent plugin idempotent.
    """
    return lua_command(
        "for _, p in ipairs("
        + PLUGIN_LIST
        + ") do if p.spec.src == "
        + lua_string(package_id)
        + " then "
        + action
        + " end end",
    )


class Vim_Pack(PackageManager):
    """Neovim's built-in plugin manager.

    `vim.pack` is a Lua API shipped in Neovim's core since
    [0.12](https://neovim.io/doc/user/pack.html), not a standalone binary: each
    operation below is a Lua one-liner evaluated by a throw-away Neovim
    process. Plugins are Git clones under `stdpath('data')/site/pack/core/opt`,
    pinned by a `nvim-pack-lock.json` lock file in `stdpath('config')`.

    ```{note}
    Every invocation runs `--clean`, so the user's `init.lua` is never
    sourced. `vim.pack.get()` reads the lock file rather than the current
    session, so the inventory stays complete without paying for, nor being
    perturbed by, a full editor startup. `stdpath()` is XDG-derived and
    `--clean` does not move it, so both the lock file and the plugin
    directory still resolve.
    ```

    ```{caution}
    Neovim exits `0` even when a `-c` command raises, which would hide every
    failure from mpm. {attr}`Vim_Pack.post_args` therefore closes each invocation with
    `-c 'cquit'`: on success the Lua payload has already called
    `os.exit(0)`, and on error control falls through to that gate and Neovim
    exits `1`.
    ```

    ```{caution}
    Installing a plugin registers it in the lock file and clones it to disk,
    but mpm does not edit the user's `init.lua`. A plugin installed through
    mpm is therefore on disk but not loaded by the next editor start until a
    matching `vim.pack.add()` call is added to the configuration.
    ```

    ```{note}
    Packages are keyed on their `src` URL. `vim.pack` accepts no registry
    shorthand: {meth}`Vim_Pack.install` needs a URL while {meth}`Vim_Pack.remove` and
    {meth}`Vim_Pack.upgrade_one_cli` address plugins by the short name Neovim derives
    from it, so the URL is the only identifier mpm can feed back into every
    operation. Package ids therefore round-trip through install, remove,
    upgrade and backup/restore.
    ```

    ```{note}
    No `outdated`: `vim.pack` exposes no read-only "list upgradable" call.
    `vim.pack.update()` fetches and then either applies the new revisions or
    renders them into a confirmation buffer, neither of which mpm can consume
    as a query, so mpm auto-skips the operation and `upgrade --all` still
    works.
    ```
    """

    name = "Neovim vim-pack"
    """Spelled with a dash: manager names are restricted to letters, digits,
    spaces, apostrophes and dashes, so the `vim.pack` API name cannot be used
    verbatim."""

    homepage_url = "https://neovim.io/doc/user/pack.html"

    platforms = ALL_PLATFORMS

    requirement = ">=0.12.0"
    """`vim.pack` landed in Neovim 0.12."""

    cli_names = ("nvim",)

    pre_args = ("--clean", "--headless")

    post_args = ("-c", "cquit")
    """Failure gate, only reached when the Lua payload raised before reaching
    its own `os.exit(0)`."""

    version_regexes = (r"NVIM\s+v(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ nvim --version
    NVIM v0.12.4
    Build type: Release
    LuaJIT 2.1.1785763465
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        r"""Fetch installed packages.

        The `rev` reported for each plugin is the Git commit it is checked out
        at, which is the only revision `vim.pack` records: a plugin is pinned
        to a branch, tag or version range, and the lock file stores the commit
        that resolved to.

        ```{code-block} shell-session

        $ nvim --clean --headless \
        > -c 'lua io.write(vim.json.encode(vim.pack.get(nil, {info = false}))) os.exit(0)' \
        > -c 'cquit'
        [{"active":false,"rev":"0ce2d843d6f588bb0c8c7eec6449171615dc56d9","spec":{"name":"vim-sensible","src":"https://github.com/tpope/vim-sensible"},"path":"/home/kev/.local/share/nvim/site/pack/core/opt/vim-sensible"},{"active":false,"rev":"a2e1f2b2e2e5a4c1d0f9b8a7c6d5e4f3a2b1c0d9","spec":{"name":"plenary.nvim","src":"https://github.com/nvim-lua/plenary.nvim"},"path":"/home/kev/.local/share/nvim/site/pack/core/opt/plenary.nvim"}]
        ```
        """
        output = self.run_cli(
            "-c",
            lua_command(f"io.write(vim.json.encode({PLUGIN_LIST}))"),
        )
        for plugin in self.parse_json(output) or ():
            source = plugin.get("spec", {}).get("src")
            if not source:
                continue
            yield self.package(id=source, installed_version=plugin.get("rev"))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        r"""Install one package.

        Loading is turned off so the freshly cloned plugin's own code is not
        sourced into the throw-away process mpm drives.

        ```{code-block} shell-session

        $ nvim --clean --headless \
        > -c 'lua vim.pack.add({{src = "https://github.com/tpope/vim-sensible"}}, {confirm = false, load = false}) os.exit(0)' \
        > -c 'cquit'
        ```
        """
        return self.run_cli(
            "-c",
            lua_command(
                "vim.pack.add({{src = "
                + lua_string(package_id)
                + "}}, {confirm = false, load = false})",
            ),
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        r"""Generates the CLI to upgrade all packages.

        ```{code-block} shell-session

        $ nvim --clean --headless \
        > -c 'lua vim.pack.update(nil, {force = true}) os.exit(0)' \
        > -c 'cquit'
        ```
        """
        return self.build_cli(
            "-c",
            lua_command("vim.pack.update(nil, {force = true})"),
        )

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        r"""Generates the CLI to upgrade one package.

        ```{code-block} shell-session

        $ nvim --clean --headless \
        > -c 'lua for _, p in ipairs(vim.pack.get(nil, {info = false})) do if p.spec.src == "https://github.com/tpope/vim-sensible" then vim.pack.update({p.spec.name}, {force = true}) end end os.exit(0)' \
        > -c 'cquit'
        ```
        """
        return self.build_cli(
            "-c",
            lua_resolve(package_id, "vim.pack.update({p.spec.name}, {force = true})"),
        )

    def remove(self, package_id: str) -> str:
        r"""Remove one package.

        ```{code-block} shell-session

        $ nvim --clean --headless \
        > -c 'lua for _, p in ipairs(vim.pack.get(nil, {info = false})) do if p.spec.src == "https://github.com/tpope/vim-sensible" then vim.pack.del({p.spec.name}, {force = true}) end end os.exit(0)' \
        > -c 'cquit'
        ```
        """
        return self.run_cli(
            "-c",
            lua_resolve(package_id, "vim.pack.del({p.spec.name}, {force = true})"),
        )
