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
"""Allow the module to be run as a CLI:

```{code-block} shell-session

$ python -m meta_package_manager
```
"""

from __future__ import annotations

import codecs
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import TextIO


def _stream_speaks_utf8(stream: TextIO) -> bool:
    """Whether `stream` already encodes the full repertoire mpm prints."""
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        return codecs.lookup(encoding).name == "utf-8"
    except LookupError:
        return False


def force_unicode_output() -> None:
    """Make the standard streams carry the glyphs mpm prints, or degrade instead
    of raising.

    Windows resolves a *redirected* stream's encoding from the legacy code page,
    `cp1252` on a Western install, and that page has no `✓` (`U+2713`), no `✘`,
    and none of the box-drawing the table borders use. Every table-rendering
    subcommand therefore died with a `UnicodeEncodeError` the moment its output
    was piped or redirected, which is precisely how automation invokes a CLI.
    A POSIX host under a `C` locale reaches the same ASCII dead end.

    Reconfiguring is a no-op wherever the stream already speaks UTF-8, so this
    only fires on the legacy path. The `backslashreplace` fallback covers a
    stream that refuses reconfiguration outright: a `\u2713` in the output is
    ugly, but it is lossless and it is not a crash.

    ```{caution}
    CI cannot catch a regression here. Every workflow sets
    `PYTHONIOENCODING=utf8`, which hands the process UTF-8 streams before mpm
    runs, so the matrix exercises an environment no user has. The guard belongs
    in `tests/test_main.py`, which drives the streams directly.
    ```
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None or _stream_speaks_utf8(stream):
            continue
        try:
            reconfigure(encoding="UTF-8")
        except (OSError, ValueError, LookupError):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError, LookupError):
                # Nothing more to try: leave the stream as the platform made it.
                pass


def main():
    """Execute the CLI but force its name to not let Click defaults to:

    ```{code-block} shell-session
    $ python -m meta_package_manager --version
    python -m meta_package_manager, version 7.2.0
    ```

    Indirection via this `main()` method was [required to reconcile](https://github.com/python-poetry/poetry/issues/5981):

        - plain inline package call: `python -m meta_package_manager`,
        - `pyproject.toml` entry point: `mpm = 'meta_package_manager.__main__:main`,
        - Nuitka's main module invocation requirement:
          `python -m nuitka (...) meta_package_manager/__main__.py`

    That way we can deduce all three cases from the entry point.
    """
    # Register config-defined managers before importing the Click group, so the
    # dynamic --<id> selectors enumerate them as first-class flags alongside the
    # built-ins. Best-effort and local-only; the authoritative registration happens
    # during config loading (config.register_config_managers_from_context).
    # Before anything prints: a legacy-encoded stream cannot carry the table
    # glyphs, and the failure is a traceback rather than a mangled character.
    force_unicode_output()

    from meta_package_manager.config import register_eager_config_managers
    from meta_package_manager.pool import pool

    register_eager_config_managers(pool)

    from meta_package_manager.cli import mpm

    mpm(prog_name=mpm.name)


if __name__ == "__main__":
    main()
