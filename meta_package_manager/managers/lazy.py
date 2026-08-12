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

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


LAZY_ROOT = 'vim.fn.stdpath("data") .. "/lazy/lazy.nvim"'
"""Lua expression resolving lazy.nvim's own checkout.

lazy.nvim manages itself, and its bootstrap snippet clones it under the
`lazy` directory of Neovim's data path. That is where a `--clean` process,
which loads none of the user's configuration, has to look to find it.
"""

LOCKFILE = 'vim.fn.stdpath("config") .. "/lazy-lock.json"'
"""Lua expression resolving the lock file lazy.nvim writes after every
install or update, which is the inventory mpm reads."""


def lua_command(body: str) -> str:
    """Wrap a Lua `body` into the `-c` argument handed to Neovim.

    The trailing `os.exit(0)` is the success path: it terminates Neovim before
    the failure gate in {attr}`Lazy.post_args` can run.
    """
    return f"lua {body} os.exit(0)"


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
                f'local f = io.open({LOCKFILE}) if f then io.write(f:read("a")) end',
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
