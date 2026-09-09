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
"""Default width a captured command wraps its output to.

Wide enough for the manager table's CLI-path column, narrow enough that the image
stays legible in the readme's prose. A capture whose output needs another width
states its own in `extra`, which then replaces this one rather than joining it.
"""

OPT_IN_CAPTURES = frozenset({"mpm-upgrade-cli"})
"""Captures a wholesale run skips, because their command changes the machine.

`mpm upgrade --all` upgrades every package every manager holds, so it cannot ride
along with the read-only captures: someone refreshing the readme's artwork is not
asking for that. Naming one in `--only` is the consent, and there is no flag that
runs the whole set including these.
"""

CAPTURES = (
    (
        "mpm-dump-cli",
        ("dump",),
        "Every installed package, written to one manifest",
        # A whole machine runs to hundreds of entries. Keep the header and the
        # first managers, which is what a reader needs to recognize the format.
        ("--head", "22"),
    ),
    (
        "mpm-installed-cli",
        ("installed",),
        "Every package installed on the system",
        # Truncated like the outdated capture below, and for the same reason. A
        # single package ID here is a plugin URL, which widens the table past any
        # width the visible rows would need. Three tail lines rather than two,
        # since the count line wraps at this width and would otherwise push the
        # table's closing border out of the capture.
        ("--columns", "160", "--merge-stderr", "--head", "16", "--tail", "3"),
    ),
    (
        "mpm-managers-cli",
        ("managers",),
        "Package managers detected on the system",
        # The widest CLI path is a macOS application bundle's, and the table wraps
        # rather than truncates when it cannot fit.
        ("--columns", "150"),
    ),
    (
        "mpm-managers-diagnostic-cli",
        ("--composer", "--volta", "--choco", "--yarn-berry", "managers"),
        "Why a package manager cannot be driven",
        # Selecting managers explicitly widens the table with the columns
        # spelling out what could not be resolved. State a width that holds them.
        ("--columns", "120"),
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
    (
        "mpm-upgrade-cli",
        ("upgrade", "--all"),
        "Every manager upgraded, in one command",
        # Recorded rather than captured: at the default verbosity this command draws
        # a spinner and a ✓ per manager, which is a sequence of screens instead of a
        # block of text. The timeout is a guard against a manager stopping on a
        # password prompt no one is there to answer, not an expected duration.
        ("--record", "--rows", "24", "--timeout", "2400"),
    ),
    (
        "mpm-version-cli",
        ("--version",),
        "The brand mark, and what this install is",
        # The screen is drawn only when it fits beside the mark, and the capture
        # pins a width of its own, so state one wide enough for the widest row.
        ("--columns", "72"),
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
            # A repeated --columns keeps its *first* value, so the default is
            # withheld when a capture states a width of its own. Emitting both
            # pinned every capture to COLUMNS, override or not.
            *(() if "--columns" in extra else ("--columns", str(COLUMNS))),
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
        if stem in OPT_IN_CAPTURES:
            if not args.only or stem not in args.only:
                continue
        elif args.only and stem not in args.only:
            continue
        target = capture(stem, mpm_args, title, extra, args.mpm)
        print(f"Wrote {target.relative_to(PROJECT_ROOT)}")
