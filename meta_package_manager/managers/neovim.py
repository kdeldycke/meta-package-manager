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

"""Managers driven by a headless Neovim process.

None of the three is a standalone binary: each is Lua living inside the editor, so
`nvim` is the CLI mpm executes for all of them and every operation travels as a
`-c 'lua …'` payload. That shared shape is what groups them here, not a shared
backend: {class}`Lazy` and {class}`Vim_Pack` clone plugins straight from upstream
Git into their own trees, while {class}`Mason` installs ordinary developer tools
through whichever ecosystem ships them.

Keying three managers on the same `nvim` binary is legitimate but needs care, so
each one's version probe answers only for its own component and stays silent on a
host that merely has an editor.
"""

from __future__ import annotations

import json

from extra_platforms import ALL_PLATFORMS
from packageurl import PackageURL

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


LAZY_LOCKFILE = 'vim.fn.stdpath("config") .. "/lazy-lock.json"'
"""Lua expression resolving the lock file lazy.nvim writes after every
install or update, which is the inventory mpm reads."""

LAZY_ROOT = 'vim.fn.stdpath("data") .. "/lazy/lazy.nvim"'
"""Lua expression resolving lazy.nvim's own checkout.

lazy.nvim manages itself, and its bootstrap snippet clones it under the
`lazy` directory of Neovim's data path. That is where a `--clean` process,
which loads none of the user's configuration, has to look to find it.
"""

MASON_CANDIDATES = (
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

MASON_ROOT = 'vim.fn.stdpath("data") .. "/mason"'
"""Lua expression resolving mason's install root.

One directory per machine, holding `bin`, `packages`, `registries` and the rest.
It is where a `--clean` process, loading none of the user's configuration, has to
look: unlike the plugin's own checkout this path does not move with whichever
plugin manager installed mason.
"""

VIM_PACK_PLUGINS = "vim.pack.get(nil, {info = false})"
"""Lua expression listing every plugin `vim.pack` manages.

`info` is turned off on purpose: the extra payload it gathers (the Git branches
and tags available for each plugin) costs one Git invocation per plugin and
holds nothing mpm reports.
"""


def lua_command(body: str) -> str:
    """Wrap a Lua `body` into the `-c` argument handed to Neovim.

    The trailing `os.exit(0)` is the success path: it terminates Neovim before the
    failure gate each manager declares in its own `post_args` can run.
    """
    return f"lua {body} os.exit(0)"


def lua_string(value: str) -> str:
    """Render `value` as a Lua string literal.

    JSON string syntax is a subset of Lua's, so {func}`json.dumps` quotes and
    escapes any plugin URL into a valid Lua literal. `ensure_ascii` is turned
    off because Lua has no `\\uXXXX` escape: a non-ASCII source must stay
    verbatim UTF-8.
    """
    return json.dumps(value, ensure_ascii=False)


def vim_pack_resolve(package_id: str, action: str) -> str:
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
        + VIM_PACK_PLUGINS
        + ") do if p.spec.src == "
        + lua_string(package_id)
        + " then "
        + action
        + " end end",
    )


class Lazy(PackageManager):
    """lazy.nvim is a modern plugin manager for Neovim.

    lazy.nvim is a Lua plugin, not a standalone binary: each operation below is
    a Lua one-liner evaluated by a throw-away Neovim process. Plugins are Git
    clones under `stdpath('data')/lazy`, pinned by a `lazy-lock.json` lock file
    in `stdpath('config')` that records the exact commit of each one.

    ```{caution}
    Neovim is the binary mpm executes, and mpm already wraps Neovim's built-in
    {class}`Vim_Pack`, which legitimately keys on the same `nvim`. The two are
    told apart by the version probe: it reports a version only when
    lazy.nvim's own checkout is found and its `version` constant reads back,
    so a host running Neovim without lazy.nvim leaves this manager
    unavailable instead of shadowing every editor on every machine.
    ```

    ```{note}
    This manager is deliberately limited to inventorying and updating, the two
    operations lazy.nvim can carry out with nobody at the keyboard. That is
    already more than the coarse, whole-category upgrade a tool like
    `topgrade` performs for the same plugins, since the inventory comes with
    it.
    ```

    ```{caution}
    No `install` and no `remove`: lazy.nvim materializes exactly the plugin
    set declared in the user's own Lua configuration. `:Lazy install` clones
    what that configuration already names and `:Lazy clean` drops what it no
    longer names, so neither takes a plugin of mpm's choosing. Installing one
    would mean mpm editing the user's `init.lua`, which is configuration mpm
    does not own. The two operations are therefore not implemented rather
    than faked, and mpm auto-skips them.
    ```

    ```{note}
    No `outdated`: `:Lazy check` does fetch each remote without touching a
    working tree, but the pending revisions it computes are only readable
    through a plugin's private `_.updates` field, which lazy.nvim documents no
    contract for. mpm auto-skips the operation and `upgrade --all` still
    works.
    ```

    Documentation: [lazy.folke.io](https://lazy.folke.io).
    """

    name = "Neovim lazy-nvim"
    """Spelled with a dash: manager names are restricted to letters, digits,
    spaces, apostrophes and dashes, so the `lazy.nvim` project name cannot be
    used verbatim."""

    homepage_url = "https://lazy.folke.io"
    logo = "neovim"

    platforms = ALL_PLATFORMS

    requirement = ">=11.0.0"
    """Current major series of lazy.nvim.

    Both pieces this implementation depends on are older than that: the
    `version` constant the probe reads and the `wait`/`show` manager options
    the upgrade passes are present as far back as `10.0.0`. The floor is held
    at the current major anyway, which is the series the implementation was
    exercised against.
    """

    cli_names = ("nvim",)

    pre_args = ("--headless",)

    post_args = ("-c", "cquit")
    """Failure gate, only reached when the Lua payload raised before reaching
    its own `os.exit(0)`."""

    version_cli_options = (
        "--clean",
        "--headless",
        "-c",
        lua_command(
            f"local p = {LAZY_ROOT} "
            "if (vim.uv or vim.loop).fs_stat(p) then vim.opt.rtp:prepend(p) "
            'io.write("lazy.nvim " .. require("lazy.core.config").version) end',
        ),
    )
    """Self-contained probe: version detection skips
    {attr}`Lazy.pre_args` and {attr}`Lazy.post_args`, so this carries its own
    `--headless` and exits on its own.

    The checkout is tested before being put on the runtime path, so a Neovim
    without lazy.nvim prints nothing and exits successfully rather than
    raising. That silence is what leaves the manager unavailable on a host
    that merely has an editor installed.
    """

    version_regexes = (r"lazy\.nvim (?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ nvim --clean --headless \
    > -c 'lua local p = vim.fn.stdpath("data") .. "/lazy/lazy.nvim" if (vim.uv or vim.loop).fs_stat(p) then vim.opt.rtp:prepend(p) io.write("lazy.nvim " .. require("lazy.core.config").version) end os.exit(0)'
    lazy.nvim 11.17.5
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        r"""Fetch installed packages.

        The lock file is read straight off disk by a `--clean` process, so the
        inventory costs no plugin loading and cannot be perturbed by the
        user's configuration. `stdpath()` is XDG-derived and `--clean` does not
        move it, so the file still resolves.

        Packages are keyed on the short name lazy.nvim derives from each
        plugin's source, which is what the lock file records. The `commit` is
        the Git revision the plugin is checked out at, the only revision
        lazy.nvim tracks: a plugin follows a branch unless its spec pins a
        version.

        ```{note}
        lazy.nvim manages itself, so it appears in its own inventory.
        ```

        ```{code-block} shell-session

        $ nvim --headless --clean \
        > -c 'lua local f = io.open(vim.fn.stdpath("config") .. "/lazy-lock.json") if f then io.write(f:read("a")) end os.exit(0)' \
        > -c 'cquit'
        {
          "lazy.nvim": { "branch": "main", "commit": "306a05526ada86a7b30af95c5cc81ffba93fef97" },
          "vim-sensible": { "branch": "master", "commit": "0ce2d843d6f588bb0c8c7eec6449171615dc56d9" },
          "z": { "branch": "master", "commit": "d37a763a6a30e1b32766fecc3b8ffd6127f8a0fd" }
        }
        ```
        """
        output = self.run_cli(
            "--clean",
            "-c",
            lua_command(
                f"local f = io.open({LAZY_LOCKFILE}) "
                'if f then io.write(f:read("a")) end',
            ),
        )
        for package_id, pin in (self.parse_json(output) or {}).items():
            if not isinstance(pin, dict):
                continue
            yield self.package(id=package_id, installed_version=pin.get("commit"))

    def upgrade_all_cli(self) -> tuple[str, ...]:
        r"""Generates the CLI to upgrade all packages.

        This is the one operation that lets the user's configuration load:
        lazy.nvim only exists once `init.lua` has bootstrapped it, so `--clean`
        is deliberately absent here. `wait` blocks until every Git task has
        finished, which is what makes the run usable unattended, and `show`
        keeps the interactive floating window from being drawn.

        ```{code-block} shell-session

        $ nvim --headless \
        > -c 'lua require("lazy").update({wait = true, show = false}) os.exit(0)' \
        > -c 'cquit'
        ```
        """
        return self.build_cli(
            "-c",
            lua_command('require("lazy").update({wait = true, show = false})'),
        )


class Mason(PackageManager):
    """Installer of LSP servers, DAP adapters, linters and formatters for Neovim.

    ```{important}
    mason is not a plugin manager, which is what separates it from
    {class}`Lazy` and {class}`Vim_Pack`. Those install Lua
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
            f"local c = vim.fn.glob(d .. {MASON_CANDIDATES[0]}, true, true) "
            f"vim.list_extend(c, vim.fn.glob(d .. {MASON_CANDIDATES[1]}, true, true)) "
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
    logo = "neovim"

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
            lua_command(f"io.write(vim.json.encode({VIM_PACK_PLUGINS}))"),
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
            vim_pack_resolve(
                package_id,
                "vim.pack.update({p.spec.name}, {force = true})",
            ),
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
            vim_pack_resolve(
                package_id,
                "vim.pack.del({p.spec.name}, {force = true})",
            ),
        )
