from click_extra.platform import LINUX
from ..base import PackageManager
from ..version import parse_version
import re
from .. import logger


class Cargo(PackageManager):
    platforms = frozenset({LINUX})
    name = "cargo"
    id = "cargo"

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. code-block:: shell-session

            ► cargo search python
            python = "0.0.0"                  # Python.
            pyo3-asyncio = "0.16.0"           # PyO3 utilities for Python's Asyncio library
            pyo3-asyncio-macros = "0.16.0"    # Proc Macro Attributes for PyO3 Asyncio
            pyo3 = "0.16.4"                   # Bindings to Python interpreter
            pyenv-python = "0.4.0"            # A pyenv shim for python that's much faster than pyenv.
            python-launcher = "1.0.0"         # The Python launcher for Unix
            py-spy = "0.3.11"                 # Sampling profiler for Python programs
            python_mixin = "0.0.0"            # Deprecated in favour of `external_mixin`. Use Python to generate your Rust, right in your Rus…
            pyflow = "0.3.1"                  # A modern Python installation and dependency manager
            pypackage = "0.0.3"               # A modern Python dependency manager
            ... and 1664 crates more (use --limit N to see more)

        """
        if extended:
            logger.warning(f"{self.id} does not implement extended search operation.")
        matches = {}
        search_args = []
        output = self.run_cli("search", query)
        regexp = re.compile(r"(?P<package_id>.*) = \"(?P<version>.*)\" *# (?P<dscription>.*)")
        for package_id, version, description in regexp.findall(output):
            matches[package_id] = {
                "id": package_id,
                "name": package_id,
                "latest_version": parse_version(version),
            }
        return matches

    def install(self, package_id):
        """Install one package.

                .. code-block:: shell-session

                    ► cargo install -q bore-cli
                        Updating crates.io index
                      Downloaded bore-cli v0.4.0
                      Downloaded 1 crate (20.9 KB) in 0.26s
                      Installing bore-cli v0.4.0
                      Downloaded serde_derive v1.0.137
                      Downloaded unicode-xid v0.2.3
                      Downloaded clap_lex v0.2.0
                      [snip]
                      Compiling bore-cli v0.4.0
                        Finished release [optimized] target(s) in 1m 06s
                       Replacing /home/mawoka/.cargo/bin/bore
                        Replaced package `bore-cli v0.2.3` with `bore-cli v0.4.0` (executable `bore`)
                """
        res = self.run_cli("install", "-q", package_id)
        return res
