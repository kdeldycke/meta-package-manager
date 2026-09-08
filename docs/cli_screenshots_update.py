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

"""Capture the `mpm` invocations the readme illustrates, as SVG terminal windows.

Each capture is a real run on the machine this script is launched from, drawn by
`click-extra screenshot` into `docs/assets/`. The readme references the results by
raw GitHub URL, which is why they are SVG rather than HTML: a readme rendered on
GitHub or PyPI strips inline markup, so a picture is the only rendering those two
surfaces will show.

```{caution}
Run by hand, on a machine carrying a representative set of package managers, and
never from CI or a docs build. A capture pictures whatever the host has installed,
so a runner would draw a near-empty table and rewrite every asset on every push.
That is the same rule `docs/brand_update.py` and `docs/logos_update.py` follow, for
the same reason: the committed artifact keeps the build hermetic.
```

```{note}
The payload is deliberately *not* held still, unlike the SwiftBar and GNOME Shell
captures that `docs/bar_screenshots_update.py` drives from a fixture. Those picture
a menu whose layout is the subject, so the packages in it are noise to be pinned.
Here the inventory **is** the subject: a reader wants to see what a real machine
answers, and inventing a plausible package to hold it still would put fabricated
metadata in the one project whose whole domain is package metadata.
```

```{todo}
Capture on a Linux host as well, so the readme is not illustrated by macOS alone.
It needs a machine with a comparable manager set, which the hosted runners are not.
```
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
"""Repository root, from which every captured `mpm` invocation is run."""

ASSETS_DIR = PROJECT_ROOT / "docs" / "assets"
"""Directory the captures are written to, beside the brand artwork."""

PRESET = "macos"
"""Terminal chrome every capture is drawn as.

One preset for the whole set, so the readme reads as one machine rather than a
gallery of window managers. It replaced the hand-drawn chrome the retired PNGs
carried, which is what the pictures were imitating anyway.
"""

COLUMNS = 100
"""Width every captured command wraps its output to.

Wide enough for the manager table's CLI-path column, narrow enough that the image
stays legible beside the readme's prose at a third of the page width.
"""

CAPTURES = (
    (
        "mpm-managers-cli",
        ("managers",),
        "Package managers detected on the system",
        (),
    ),
    (
        "mpm-outdated-cli",
        ("outdated",),
        "Packages an upgrade is available for",
        # A full inventory runs to a hundred rows, which floated beside the readme's
        # prose is a thin unreadable strip. Keep the head of the table, then its
        # closing border and the count line, joined by the renderer's own [...] rule.
        # That count line is printed on stderr, so the capture has to fold it in.
        ("--merge-stderr", "--head", "16", "--tail", "2"),
    ),
)
"""The captures, as `(stem, mpm arguments, window caption, extra options)` tuples.

The stems are the file names the readme links, so renaming one breaks the readme
and the two must move together.
"""


def capture(
    stem: str,
    args: tuple[str, ...],
    title: str,
    extra: tuple[str, ...],
    mpm: str,
) -> Path:
    """Run one `mpm` invocation and draw its output into `docs/assets/{stem}.svg`.

    Returns the path written.

    :param stem: file name of the capture, without its extension.
    :param args: arguments handed to `mpm`.
    :param title: caption drawn in the window's title bar.
    :param extra: further options for the `screenshot` command itself.
    :param mpm: the `mpm` executable to run.
    """
    target = ASSETS_DIR / f"{stem}.svg"
    subprocess.run(
        (
            sys.executable,
            "-m",
            "click_extra",
            "screenshot",
            "--output",
            str(target),
            "--columns",
            str(COLUMNS),
            "--preset",
            PRESET,
            "--title",
            title,
            # The captured binary is reached by path, so that path would otherwise
            # be the command line drawn above the output. Draw what a reader types.
            "--prompt",
            " ".join(("mpm", *args)),
            # The renderer credits itself in the margin by default. The readme
            # embeds these small enough that the line is unreadable, and the
            # picture is this project's own CLI output, so nothing is owed.
            "--watermark",
            "",
            *extra,
            "--",
            mpm,
            *args,
        ),
        check=True,
        cwd=PROJECT_ROOT,
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mpm",
        default="mpm",
        help="The mpm executable to capture. Defaults to the one on PATH.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[stem for stem, _, _, _ in CAPTURES],
        help="Capture this file only. Repeat to name several.",
    )
    args = parser.parse_args()

    for stem, mpm_args, title, extra in CAPTURES:
        if args.only and stem not in args.only:
            continue
        target = capture(stem, mpm_args, title, extra, args.mpm)
        print(f"Wrote {target.relative_to(PROJECT_ROOT)}")
