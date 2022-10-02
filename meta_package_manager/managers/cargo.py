# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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
from typing import Iterator

from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class Cargo(PackageManager):

    name = "Rust's cargo"

    homepage_url = "https://doc.rust-lang.org/cargo/"

    platforms = frozenset({MACOS, LINUX, WINDOWS})

    requirement = "1.0.0"

    pre_args = (
        "--color",
        "never",  # Suppress colored output.
        "--quiet",  # Do not print cargo log messages.
    )

    version_regex = r"cargo\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► cargo --version
        cargo 1.59.0
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► cargo --color never --quiet install --list
            bore-cli v0.4.0:
                bore
            ripgrep v13.0.0:
                rg
        """
        output = self.run_cli("install", "--list")

        regexp = re.compile(r"^(?P<package_id>\S+)\s+v(?P<package_version>\S+):$")

        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, package_version = match.groups()
                yield self.package(id=package_id, installed_version=package_version)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them.

        .. danger:
            `Cargo limits search to 100 results <https://doc.rust-lang.org/cargo/commands/cargo-search.html#search-options>`_,
            and because CLI output is refiltered as mentioned above, the final results can't be guaranteed.

        .. code-block:: shell-session

            ► cargo --color never --quiet search --limit 100 python
            python = "0.0.0"                  # Python.
            pyo3-asyncio = "0.16.0"           # PyO3 utilities for Python's Asyncio library
            pyo3-asyncio-macros = "0.16.0"    # Proc Macro Attributes for PyO3 Asyncio
            pyo3 = "0.16.4"                   # Bindings to Python interpreter
            pyenv-python = "0.4.0"            # A pyenv shim for python that's much faster than pyenv.
            python-launcher = "1.0.0"         # The Python launcher for Unix
            py-spy = "0.3.11"                 # Sampling profiler for Python programs
            python_mixin = "0.0.0"            # Use Python to generate your Rust, right in your Rus…
            pyflow = "0.3.1"                  # A modern Python installation and dependency manager
            pypackage = "0.0.3"               # A modern Python dependency manager
            ... and 1664 crates more (use --limit N to see more)
        """
        output = self.run_cli("search", "--limit", "100", query)

        regexp = re.compile(
            r"^(?P<package_id>\S+)\s+=\s+\"(?P<version>\S+)\"\s+#\s+(?P<description>.+)$",
            re.MULTILINE,
        )

        for package_id, version, description in regexp.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► cargo --color never install bore-cli
              Updating crates.io index
            Downloaded bore-cli v0.4.0
            Downloaded 1 crate (20.9 KB) in 0.26s
            Installing bore-cli v0.4.0
            Downloaded serde_derive v1.0.137
            Downloaded unicode-xid v0.2.3
            Downloaded clap_lex v0.2.0
            (...)
            Compiling bore-cli v0.4.0
              Finished release [optimized] target(s) in 1m 06s
             Replacing /home/mawoka/.cargo/bin/bore
              Replaced package `bore-cli v0.2.3` with `bore-cli v0.4.0` (executable `bore`)
        """
        res = self.run_cli("install", package_id)
        return res

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► cargo --color never uninstall bore-cli
                Removing /Users/me/.cargo/bin/bore
        """
        return self.run_cli("uninstall", package_id)
