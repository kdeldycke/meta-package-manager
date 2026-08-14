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

from extra_platforms import ALL_PLATFORMS
from packageurl import PackageURL

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


MASON_ROOT = 'vim.fn.stdpath("data") .. "/mason"'
"""Lua expression resolving mason's install root.

One directory per machine, holding `bin`, `packages`, `registries` and the rest.
It is where a `--clean` process, loading none of the user's configuration, has to
look: unlike the plugin's own checkout this path does not move with whichever
plugin manager installed mason.
"""

PLUGIN_CANDIDATES = (
    '"/lazy/mason.nvim"',
    '"/site/pack/*/*/mason.nvim"',
)
"""Globs, relative to Neovim's data path, where mason's own checkout may sit.

mason.nvim is a plugin like any other, so its location is decided by whatever
installed it rather than by mason: lazy.nvim clones it under `lazy`, while the
built-in package mechanism and the managers built on it use `site/pack`. Both
are probed because a `--clean` process loads no configuration and therefore has
nothing else to go on.
"""


def lua_command(body: str) -> str:
    """Wrap a Lua `body` into the `-c` argument handed to Neovim.

    The trailing `os.exit(0)` is the success path: it terminates Neovim before
    the failure gate in {attr}`Mason.post_args` can run.
    """
    return f"lua {body} os.exit(0)"


class Mason(PackageManager):
    """Installer of LSP servers, DAP adapters, linters and formatters for Neovim.

    ```{important}
    mason is not a plugin manager, which is what separates it from
    {class}`~meta_package_manager.managers.lazy.Lazy` and
    {class}`~meta_package_manager.managers.vim_pack.Vim_Pack`. Those install Lua
    that runs inside the editor; mason installs ordinary developer tools, the same
    `stylua` or `rust-analyzer` binaries another host might get from Homebrew.
    ```

    ```{note}
    Wrapping it is what makes those tools visible at all. mason redirects every
    backend it shells out to into the package's own directory: a local `npm
    install` rather than a global one, a `venv` per package, `cargo install --root
    .`, `GOBIN` and `GEM_HOME` pointed inside. So a `pyright` installed by mason
    appears in no other manager's inventory, and without this wrapper `mpm` would
    not see it.
    ```

    ```{caution}
    Reads and writes drive Neovim differently, and deliberately.

    The inventory is read by a `--clean` process straight off mason's own install
    tree, costing no plugin loading and immune to whatever the user's
    configuration does. Mutations cannot work that way: `MasonInstall` and its
    siblings are user commands that exist only once mason is loaded, so those run
    without `--clean` and let the configuration supply them. That is mason's own
    documented recipe for unattended use.
    ```

    ```{note}
    Every mutating command blocks in headless mode rather than returning while
    work continues in the background: mason branches on `#vim.api.nvim_list_uis()
    == 0` and runs the transaction synchronously, refusing an unknown package name
    up front instead of failing silently.
    ```

    ```{warning}
    The install root is assumed to be mason's default. A configuration moving
    `install_root_dir` elsewhere leaves the inventory empty, since finding the
    override would mean loading the very plugin the read path avoids.
    ```

    Documentation: [mason.nvim](https://github.com/mason-org/mason.nvim).
    """

    name = "Neovim mason-nvim"

    homepage_url = "https://github.com/mason-org/mason.nvim"
    logo = "neovim"

    platforms = ALL_PLATFORMS

    requirement = ">=2.0.0"
    """The release that reshaped mason's API into the one described here.

    `2.0.0` removed the modules backing custom Lua packages, replaced the registry
    events, and raised the Neovim floor to `0.10.0`. It is also the release the
    project moved to its own organization under, so it is the oldest version worth
    describing.

    ```{caution}
    This floors *mason*, never the receipts it wrote. A host on a current mason
    still carries receipts from `1.x` for anything installed back then, which is
    why {meth}`installed` reads both of their shapes.
    ```
    """

    cli_names = ("nvim",)

    pre_args = ("--headless",)

    post_args = ("-c", "cquit")
    """Failure gate. Every Lua body exits on its own through {func}`lua_command`,
    and every mutation closes on `qall`, so reaching this means the command never
    got that far and the run is an error.
    """

    version_cli_options = (
        "--clean",
        "--headless",
        "-c",
        lua_command(
            'local d = vim.fn.stdpath("data") '
            f"local c = vim.fn.glob(d .. {PLUGIN_CANDIDATES[0]}, true, true) "
            f"vim.list_extend(c, vim.fn.glob(d .. {PLUGIN_CANDIDATES[1]}, true, true)) "
            "for _, p in ipairs(c) do vim.opt.rtp:prepend(p) "
            'local ok, m = pcall(require, "mason.version") '
            'if ok then io.write("mason " .. m.VERSION) break end end',
        ),
    )
    """Self-contained probe: version detection skips {attr}`Mason.pre_args` and
    {attr}`Mason.post_args`, so this carries its own `--headless` and exits on its
    own.

    Each candidate checkout is put on the runtime path only long enough to try
    loading mason from it, so a Neovim without mason prints nothing and exits
    successfully rather than raising. That silence is what leaves the manager
    unavailable on a host that merely has an editor, which matters here because
    `lazy` and `vim-pack` legitimately key on the same `nvim` binary.
    """

    version_regexes = (r"mason v?(?P<version>\S+)",)
    r"""Search the version right after the `mason` string.

    ```{code-block} shell-session

    $ nvim --clean --headless \
    > -c 'lua local d = vim.fn.stdpath("data") local c = vim.fn.glob(d .. "/lazy/mason.nvim", true, true) vim.list_extend(c, vim.fn.glob(d .. "/site/pack/*/*/mason.nvim", true, true)) for _, p in ipairs(c) do vim.opt.rtp:prepend(p) local ok, m = pcall(require, "mason.version") if ok then io.write("mason " .. m.VERSION) break end end os.exit(0)'
    mason v2.3.1
    ```

    The `v` is optional in the pattern because it belongs to mason's own string
    rather than to the version: it is a tag name reported verbatim.
    """

    @property
    def installed(self) -> Iterator[Package]:
        r"""Fetch installed packages.

        mason writes a receipt beside every package it installs, and those
        receipts are the inventory: a `--clean` process reads them straight off
        the tree, so nothing has to be loaded and the user's configuration cannot
        perturb the result.

        A receipt carries no version field. It records the package's source as a
        purl, and the version is the purl's own version component, which is what
        mason itself reads back.

        ```{caution}
        The source sits under `source` in a `2.0` receipt and under
        `primary_source` in every earlier one, exactly as mason's own reader
        branches. Both are accepted here: the receipt's schema version is fixed
        when the package is installed, so a current mason keeps serving `1.x`
        receipts for anything installed under it, and reading only one shape
        would silently drop those packages instead of failing.
        ```

        ```{code-block} shell-session

        $ nvim --headless --clean \
        > -c 'lua local root = vim.fn.stdpath("data") .. "/mason" .. "/packages" for _, dir in ipairs(vim.fn.glob(root .. "/*", true, true)) do local f = dir .. "/mason-receipt.json" if (vim.uv or vim.loop).fs_stat(f) then local ok, r = pcall(vim.json.decode, table.concat(vim.fn.readfile(f), "\n")) if ok and r and r.name then local s = r.source or r.primary_source io.write(r.name .. "\t" .. ((s and s.id) or "") .. "\n") end end end os.exit(0)' \
        > -c 'cquit'
        stylua	pkg:github/johnnymorganz/stylua@v2.5.2
        ```
        """
        output = self.run_cli(
            "--clean",
            "-c",
            lua_command(
                f"local root = {MASON_ROOT} "
                '.. "/packages" '
                'for _, dir in ipairs(vim.fn.glob(root .. "/*", true, true)) do '
                'local f = dir .. "/mason-receipt.json" '
                "if (vim.uv or vim.loop).fs_stat(f) then "
                "local ok, r = pcall(vim.json.decode, "
                'table.concat(vim.fn.readfile(f), "\\n")) '
                "if ok and r and r.name then "
                "local s = r.source or r.primary_source "
                'io.write(r.name .. "\\t" .. ((s and s.id) or "") .. "\\n") '
                "end end end",
            ),
        )
        for line in output.splitlines():
            package_id, _, purl = line.partition("\t")
            if not package_id.strip():
                continue
            version = None
            if purl.strip():
                try:
                    version = PackageURL.from_string(purl.strip()).version
                except ValueError:
                    version = None
            yield self.package(id=package_id.strip(), installed_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        Runs without `--clean` so the user's configuration supplies the
        `MasonInstall` command, which mason documents as the way to drive it
        unattended.

        ```{code-block} shell-session

        $ nvim --headless -c 'MasonInstall stylua' -c 'qall' -c 'cquit'
        ```
        """
        return self.run_cli("-c", f"MasonInstall {package_id}", "-c", "qall")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        mason has no upgrade verb of its own: installing a package that is
        already present fetches whatever the registry currently offers, which is
        the upgrade.

        ```{code-block} shell-session

        $ nvim --headless -c 'MasonInstall stylua' -c 'qall' -c 'cquit'
        ```
        """
        return self.build_cli("-c", f"MasonInstall {package_id}", "-c", "qall")

    def remove(self, package_id: str) -> str:
        """Removes a package.

        ```{code-block} shell-session

        $ nvim --headless -c 'MasonUninstall stylua' -c 'qall' -c 'cquit'
        ```
        """
        return self.run_cli("-c", f"MasonUninstall {package_id}", "-c", "qall")

    def sync(self) -> None:
        """Sync package metadata.

        `MasonUpdate` refreshes the registry index and upgrades nothing, which is
        exactly this operation. Its own description says so, and its body calls
        the registry update alone.

        ```{code-block} shell-session

        $ nvim --headless -c 'MasonUpdate' -c 'qall' -c 'cquit'
        ```
        """
        self.run_cli("-c", "MasonUpdate", "-c", "qall")
