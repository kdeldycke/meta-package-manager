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
from typing import ClassVar

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class ZeroInstall(PackageManager):
    """Zero Install is a decentralised, cross-platform installation system.

    There is no central registry. A program is identified by the URL of its
    feed, an XML document its own publisher hosts and signs with their own GPG
    key, so a package id here is a feed URI rather than a short name. Short
    names collide freely across publishers: one search for `python` returns a
    `Python` feed from `apps.0install.net`, another from `0install.de` and a
    third from `dispcalgui.hoech.net`.

    A second identifier sits beside the URI. An *application* is a pet name the
    user invents and binds to a feed, which is what `destroy` and `update`
    address. The two identifier spaces are what shape the operation set below.

    ```{caution}
    No `installed`: `0install list` looks like an inventory and is not. It
    prints the URI of every feed in the local cache, which is the set of feeds
    ever fetched rather than the set of programs installed. Upstream says so in
    the command's own source, `src/cli/list_ifaces.ml`, which calls
    `Feed_cache.list_all_feeds` under the comment *"Actually, we list all the
    cached feeds. Close enough."*

    Driving it proves how wide the gap is. On a host where exactly one
    application was added, `0install list` returned thirteen URIs: the feeds
    the solver merely consulted to resolve dependencies, and `xz`, whose
    selection had failed outright with *"No usable implementations"* and which
    downloaded not one byte. Reporting those as installed would be false.
    The listing also never prints a pet name, so nothing it emits can be
    handed back to `destroy`.
    ```

    ```{caution}
    No `install`: `0install add` takes *two* mandatory arguments, the pet name
    to create and the feed URI to bind it to, and refuses a lone URI. mpm's
    install carries a single package id, which cannot supply both, and
    inventing a pet name for the user would name their application for them.
    `sheldon` declines the operation for the same reason.
    ```

    ```{note}
    No `outdated`: nothing reports staleness without acting on it. `update`
    does print when a newer version exists, but it is the upgrade itself and
    needs an application named on the command line.
    ```

    ```{note}
    No `upgrade` of either shape. `0install update` requires an application or
    a URI and the tool ships no bulk form, so there is no `upgrade --all` to
    build. The single-package form is out for a second reason: mpm resolves
    which manager sources a package by querying its inventory, and this manager
    has none to query, so the operation could never be dispatched here.
    ```

    ```{note}
    No `sync`: refreshing is the `--refresh` flag of the commands that already
    resolve a feed, never a command of its own.
    ```

    ```{note}
    No version floor is declared. Every subcommand this class drives predates
    the oldest release upstream's `CHANGES.md` documents, so no floor could be
    verified rather than guessed. The class was driven against `2.18`.
    ```

    Documentation: [0install](https://0install.net).
    """

    name = "Zero Install"

    homepage_url = "https://0install.net"

    platforms = ALL_PLATFORMS
    """The OCaml implementation builds for Windows alongside every Unix, and
    ships the manifest and resource files to prove it under `src/windows`.
    """

    cli_names = ("0install",)
    """The binary leads with a digit, where the manager id cannot.

    Every id doubles as a `--<id>` selector, and Click derives an option's
    Python identifier from that flag, which leaves `--0install` named by the
    empty string. So the id follows the project's own name, Zero Install, and
    only the binary keeps its digit.
    """

    pre_args = ("--console",)
    """Keeps every call on the terminal.

    0install switches to a graphical policy editor whenever it needs the
    network and `DISPLAY` is set, so a search run from a desktop session would
    otherwise open a window and wait for a human.
    """

    version_regexes = (r"0install\s+\(zero-install\)\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ 0install --console --version
    0install (zero-install) 2.18
    Copyright (C) 2019 Thomas Leonard
    This program comes with ABSOLUTELY NO WARRANTY,
    to the extent permitted by law. You may redistribute copies of this program
    under the terms of the GNU Lesser General Public License.
    For more information about these matters, see the file named COPYING.
    Compiled with D-Bus support: false
    HTTP client library: libcurl (C)
    ```
    """

    _SEARCH_REGEXP: ClassVar = re.compile(
        r"^(?P<package_id>\S+)\n {2}(?P<name>\S+) - (?P<description>.*) \[\d+%\]$",
        re.MULTILINE,
    )
    """Matches one two-line search record.

    A record is the feed URI on its own line, then an indented line carrying
    the short name, a description and the mirror's relevance score. Two lines
    per record is what rules out a bundled definition for this manager.

    The URI is the package id, being the only unique one: short names collide
    across publishers, and the same `Python` name is served by three separate
    feeds. The short name is kept as the package name, which is the half a
    user recognises and searches on.
    """

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        The query goes to the mirror server, which indexes feeds it has been
        told about. Results carry no version, the mirror indexing feeds rather
        than the implementations inside them.

        ```{caution}
        Search does not support extended or exact matching.
        ```

        ```{code-block} shell-session

        $ 0install --console search hello
        http://gfxmonk.net/dist/0install/template.xml
          template - A command-line jinja2 template script [100%]

        http://gfxmonk.net/dist/0install/python-pyquery.xml
          python-pyquery - A jquery-like library for python [45%]

        http://gfxmonk.net/dist/0install/python-argh.xml
          python-argh - An unobtrusive argparse wrapper with natural syntax [38%]

        http://gfxmonk.net/dist/0install/should.js.xml
          should.js - should.js [8%]

        http://gfxmonk.net/dist/0install/python-colorama.xml
          python-colorama - Cross-platform colored terminal text. [7%]
        ```
        """
        output = self.run_cli("search", query)

        for match in self._SEARCH_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                name=match.group("name"),
                description=match.group("description"),
            )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        `destroy` takes the pet name alone, the one `add` created, and deletes
        the application directory with any launcher script it placed on the
        user's path. A feed URI is refused with `No such application`, so the
        URIs that `search` yields are not what this operation consumes.

        ```{code-block} shell-session

        $ 0install --console destroy zeroinstall
        ```
        """
        return self.run_cli("destroy", package_id)

    def cleanup_cache(self) -> None:
        """Optimise the implementation cache.

        Hard-links files shared by several implementations in the store, so a
        program kept at more than one version stops paying for each copy.

        ```{code-block} shell-session

        $ 0install --console store optimise
        Optimising /Users/kde/.cache/0install.net/implementations
        [0 / 1] Reading manifests...Original size  : 2.1 MB (excluding the 27.9 KB of manifests)
        Already saved  : 0 bytes
        Optimised size : 2.1 MB
        Space freed up : 40 bytes (0.00%)
        Optimisation complete.
        ```
        """
        self.run_cli("store", "optimise")
